"""Pull-based deployment controller for the existing Tencent Ubuntu server.

Installed copy: /usr/local/lib/clarity-deploy/deployer.py (root-owned).
The timer runs the controller as root solely to switch a root-owned symlink and
restart one fixed service. Downloaded code, pip and pytest run as ubuntu, never root.
Repository updates DO NOT automatically replace this privileged controller/unit.
"""

import argparse
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time
import urllib.request

REPO = "BIGBEN171/ivt"
API = f"https://api.github.com/repos/{REPO}"
RELEASES = Path("/home/ubuntu/clarity-releases")
CURRENT = Path("/opt/clarity-capture-current")
LEGACY = Path("/home/ubuntu/clarity-capture")
STATE_DIR = Path("/var/lib/clarity-deploy")
STATE_FILE = STATE_DIR / "state.json"
CONTROLLER = Path("/usr/local/lib/clarity-deploy/deployer.py")
SERVICE = "clarity-capture.service"


def checked_sha(value):
    """Only full hexadecimal commit IDs may appear in URLs or release paths."""
    if not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{40}", value):
        raise ValueError("Invalid commit SHA")
    return value


def request_json(url):
    # Public repository: no GitHub token or server credential is needed.
    request = urllib.request.Request(url, headers={
        "Accept": "application/vnd.github+json", "User-Agent": "clarity-deploy/1",
        "X-GitHub-Api-Version": "2022-11-28",
    })
    with urllib.request.urlopen(request, timeout=25) as response:
        return json.load(response)


def main_head():
    return checked_sha(request_json(f"{API}/branches/main")["commit"]["sha"])


def ci_passed(sha):
    """Require the latest main push run of the exact backend workflow to succeed.

    A previous green run must not override a newer queued/failed rerun. PR runs,
    runs for another commit, and skipped/cancelled runs cannot authorize deployment.
    """
    runs = request_json(
        f"{API}/actions/workflows/backend-ci.yml/runs"
        f"?head_sha={sha}&branch=main&event=push&per_page=10"
    )["workflow_runs"]
    matching = [r for r in runs if r["head_sha"] == sha
                and r["head_branch"] == "main" and r["event"] == "push"]
    if not matching:
        return False
    latest = max(matching, key=lambda r: r["id"])
    return latest["status"] == "completed" and latest["conclusion"] == "success"


def write_state(state):
    # Replace the journal atomically so a process crash cannot leave partial JSON.
    temporary = STATE_FILE.with_suffix(".tmp")
    temporary.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")
    temporary.replace(STATE_FILE)


def switch_to(path):
    """Change only the fixed application symlink; never move/delete photo data."""
    path = Path(path).resolve(strict=True)
    if path != LEGACY and not (path.parent == RELEASES and re.fullmatch(r"[0-9a-f]{40}", path.name)):
        raise ValueError("Unexpected release location")
    temporary = CURRENT.with_name(CURRENT.name + ".next")
    temporary.unlink(missing_ok=True)
    temporary.symlink_to(path, target_is_directory=True)
    temporary.replace(CURRENT)


def restart():
    # Fixed argv: repository content cannot select a different system service.
    subprocess.run(["/usr/bin/systemctl", "restart", SERVICE], check=True, timeout=40)


def healthy():
    # A short restart interruption is expected. Do not declare success on TCP alone.
    for _ in range(20):
        try:
            with urllib.request.urlopen("http://127.0.0.1:8010/api/v1/health", timeout=2) as response:
                if response.status == 200 and json.load(response).get("status") == "ok":
                    return True
        except (OSError, ValueError):
            pass
        time.sleep(1)
    return False


def restore_pending(state):
    """Recover an interrupted/failed switch using the pre-switch journal."""
    pending = state["pending"]
    switch_to(pending["previous"])
    restart()
    if not healthy():
        # Keep pending so the next invocation retries recovery, not a new deploy.
        raise RuntimeError("Rollback health check failed; inspect the service journal")
    state["last_failed"] = pending["sha"]
    del state["pending"]
    write_state(state)
    print("ROLLBACK_OK", pending["sha"], flush=True)


def activate(sha, state):
    """Journal the old path before changing it, then promote or roll back."""
    state["pending"] = {"sha": sha, "previous": str(CURRENT.resolve(strict=True))}
    write_state(state)
    try:
        switch_to(RELEASES / sha)
        restart()
        if not healthy():
            raise RuntimeError("Candidate health check failed")
    except Exception:
        restore_pending(state)
        raise
    state["deployed"] = sha
    state.pop("last_failed", None)
    state.pop("pending", None)
    write_state(state)
    print("DEPLOY_OK", sha, flush=True)


def prepare(sha):
    """Build an immutable-path candidate as ubuntu while the old API keeps running."""
    if os.geteuid() == 0:
        raise RuntimeError("Preparation must not execute as root")
    sha = checked_sha(sha)
    release = RELEASES / sha
    if (release / ".ready").exists():
        return
    if release.exists():
        # An incomplete prior build is private to this commit and can be retried.
        # Never delete an active release, even if its readiness marker is missing.
        if CURRENT.resolve() == release.resolve():
            raise RuntimeError("Refusing to rebuild the active release")
        shutil.rmtree(release)
    if shutil.disk_usage(RELEASES).free < 2 * 1024**3:
        raise RuntimeError("At least 2 GiB free space is required for a new release")
    release.mkdir(mode=0o700)
    with tempfile.TemporaryDirectory(prefix="clarity-download-") as temporary:
        archive = Path(temporary) / "source.tar.gz"
        request = urllib.request.Request(
            f"https://codeload.github.com/{REPO}/tar.gz/{sha}",
            headers={"User-Agent": "clarity-deploy/1"},
        )
        with urllib.request.urlopen(request, timeout=60) as response, archive.open("wb") as output:
            shutil.copyfileobj(response, output)
        # Extract regular backend files only. Never accept archive paths, links,
        # device nodes, virtual environments or uploaded data outside this subtree.
        with tarfile.open(archive) as source:
            for member in source.getmembers():
                parts = Path(member.name).parts
                if len(parts) < 3 or parts[1] != "backend" or not member.isfile():
                    continue
                relative = Path(*parts[1:])
                if ".." in relative.parts or any(p in {".venv", "data", "__pycache__"} for p in relative.parts):
                    raise ValueError("Unsafe backend archive path")
                destination = release / relative
                destination.parent.mkdir(parents=True, exist_ok=True)
                with source.extractfile(member) as incoming, destination.open("wb") as outgoing:
                    shutil.copyfileobj(incoming, outgoing)
    # Create the venv at its final location: moving a venv breaks its script paths.
    subprocess.run([sys.executable, "-m", "venv", str(release / ".venv")], check=True, timeout=120)
    python = str(release / ".venv/bin/python")
    for args in (["-m", "pip", "install", "--disable-pip-version-check", "-r", "backend/requirements.txt"],
                 ["-m", "pytest", "backend/tests", "-q"]):
        subprocess.run([python, *args], cwd=release, check=True, timeout=600)
    (release / "DEPLOYED_COMMIT").write_text(sha + "\n")
    (release / ".ready").write_text("Server tests passed\n")


def poll():
    """One bounded poll; network/CI/build failures leave the current API untouched."""
    state = json.loads(STATE_FILE.read_text())
    if "pending" in state:
        restore_pending(state)
        return
    sha = main_head()
    if sha == state.get("deployed") or sha == state.get("last_failed"):
        print("NO_CHANGE", sha, flush=True)
        return
    if not ci_passed(sha):
        print("WAITING_FOR_CI", sha, flush=True)
        return
    subprocess.run([
        "/usr/sbin/runuser", "-u", "ubuntu", "--", "/usr/bin/python3",
        str(CONTROLLER), "--prepare", sha,
    ], check=True, timeout=1500)
    # A newer push during the build invalidates this candidate; inspect it next poll.
    if main_head() != sha or not ci_passed(sha):
        print("CANDIDATE_SUPERSEDED_OR_CI_CHANGED", sha, flush=True)
        return
    activate(sha, state)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prepare", metavar="SHA")
    args = parser.parse_args()
    if args.prepare:
        prepare(args.prepare)
        return
    if os.geteuid() != 0:
        raise RuntimeError("The controller must be run by its systemd service")
    # systemd already serializes this unit. The lock also protects manual runs.
    import fcntl
    with (STATE_DIR / "deploy.lock").open("w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        poll()


if __name__ == "__main__":
    main()
