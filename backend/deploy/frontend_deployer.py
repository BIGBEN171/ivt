"""Build and atomically publish static frontend releases as unprivileged ubuntu.

Installed controller is root-owned; GitHub pushes cannot replace the controller.
Only built dist files are published. Source, dependencies and photo data stay private.
"""
import argparse
import fcntl
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import subprocess
import tarfile
import tempfile
import urllib.request

API = 'https://api.github.com/repos/BIGBEN171/ivt'
ROOT = Path('/var/www/clarity-frontend')
CURRENT = ROOT / 'current'
STATE = Path('/home/ubuntu/.local/state/clarity-frontend')


def fetch_json(url):
    request = urllib.request.Request(url, headers={'User-Agent': 'clarity-frontend-deploy/1'})
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.load(response)


def head():
    sha = fetch_json(API + '/branches/main')['commit']['sha']
    if not re.fullmatch('[0-9a-f]{40}', sha):
        raise ValueError('Invalid commit ID')
    return sha


def passed(sha):
    # Only a successful main push for this exact SHA authorizes deployment.
    runs = fetch_json(API + '/actions/workflows/frontend-ci.yml/runs?branch=main&event=push&head_sha=' + sha)['workflow_runs']
    matching = [r for r in runs if r['head_sha'] == sha and r['event'] == 'push' and r['head_branch'] == 'main']
    latest = max(matching, key=lambda r: r['id']) if matching else None
    return bool(latest and latest['status'] == 'completed' and latest['conclusion'] == 'success')


def extract(source, work):
    # Extract an explicit frontend allowlist; reject traversal and symbolic links.
    allowed = {'src', 'public', 'tests', 'package.json', 'package-lock.json', 'index.html', 'vite.config.js', 'vite.config.mjs'}
    for member in source.getmembers():
        parts = PurePosixPath(member.name).parts
        if len(parts) < 2 or parts[1] not in allowed:
            continue
        if '..' in parts or member.issym() or member.islnk():
            raise ValueError('Unsafe source archive member')
        if not member.isfile():
            continue
        dest = work.joinpath(*parts[1:])
        dest.parent.mkdir(parents=True, exist_ok=True)
        with source.extractfile(member) as src, dest.open('wb') as dst:
            shutil.copyfileobj(src, dst)


def build(sha):
    release = ROOT / 'releases' / sha
    if release.is_dir():
        return release
    if shutil.disk_usage(ROOT).free < 2 * 1024**3:
        raise RuntimeError('At least 2 GiB of free disk space is required')
    with tempfile.TemporaryDirectory(prefix='build-', dir=STATE) as folder:
        work = Path(folder)
        archive = work / 'source.tgz'
        with urllib.request.urlopen('https://codeload.github.com/BIGBEN171/ivt/tar.gz/' + sha, timeout=60) as src, archive.open('wb') as dst:
            shutil.copyfileobj(src, dst)
        with tarfile.open(archive) as source:
            extract(source, work)
        # All npm scripts run as ubuntu, with the lockfile enforced by npm ci.
        for args in (['ci', '--no-audit', '--no-fund'], ['test'], ['run', 'build', '--', '--base=/releases/' + sha + '/']):
            subprocess.run(['/usr/bin/npm', *args], cwd=work, check=True, timeout=600)
        dist = work / 'dist'
        if not (dist / 'index.html').is_file():
            raise RuntimeError('Build produced no index.html')
        for path in dist.rglob('*'):
            if path.is_symlink():
                raise ValueError('Build output contains a symbolic link')
        (dist / 'version.json').write_text(json.dumps({'commit': sha}) + '\n')
        # Publish only complete builds. Keep the staging directory on the same disk.
        staged = Path(tempfile.mkdtemp(prefix='.staging-', dir=ROOT))
        try:
            shutil.copytree(dist, staged, dirs_exist_ok=True)
            for path in staged.rglob('*'):
                path.chmod(0o755 if path.is_dir() else 0o644)
            staged.chmod(0o755)
            staged.rename(release)
        finally:
            if staged.exists():
                shutil.rmtree(staged)
    return release


def switch(target):
    # Atomic symlink replacement lets Nginx serve complete releases without reloads.
    temporary = ROOT / '.current-next'
    temporary.unlink(missing_ok=True)
    temporary.symlink_to(target, target_is_directory=True)
    temporary.replace(CURRENT)


def smoke(sha):
    # Verify the local Nginx endpoint while still checking the public IP certificate.
    raw = subprocess.check_output(['/usr/bin/curl', '--noproxy', '*', '--fail', '--silent', '--show-error', '--max-time', '20', '--resolve', '62.234.95.210:8082:127.0.0.1', 'https://62.234.95.210:8082/version.json'], timeout=25)
    if json.loads(raw)['commit'] != sha:
        raise RuntimeError('Nginx is not serving the selected release')


def poll(bootstrap=False):
    sha = head()
    if CURRENT.exists() and CURRENT.resolve().name == sha:
        smoke(sha)
        print('NO_CHANGE', sha, flush=True)
        return
    if not passed(sha):
        print('WAITING_FOR_FRONTEND_CI', sha, flush=True)
        return
    candidate = build(sha)
    if head() != sha or not passed(sha):
        print('CANDIDATE_SUPERSEDED', sha, flush=True)
        return
    previous = CURRENT.resolve() if CURRENT.exists() else None
    if bootstrap and previous is not None:
        raise RuntimeError('Bootstrap is only allowed before the first static release')
    switch(candidate)
    try:
        # Initial bootstrap precedes the one-time switch from proxy to static Nginx.
        if not bootstrap:
            smoke(sha)
    except Exception:
        if previous is not None:
            switch(previous)
        raise
    print('FRONTEND_DEPLOY_OK', sha, flush=True)


if __name__ == '__main__':
    if os.geteuid() == 0:
        raise RuntimeError('Run this controller as ubuntu, never root')
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bootstrap', action='store_true')
    args = parser.parse_args()
    STATE.mkdir(parents=True, exist_ok=True, mode=0o700)
    with (STATE / 'deploy.lock').open('w') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        poll(args.bootstrap)
