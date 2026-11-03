"""Deployment policy tests; no real systemd, GitHub requests or server paths used."""

import json
from unittest.mock import Mock

import pytest

from backend.deploy import deployer as deploy

SHA = "a" * 40
OLD = "b" * 40


def test_newer_failed_run_blocks_older_success(monkeypatch):
    def run(number, status, conclusion):
        return {"id": number, "head_sha": SHA, "head_branch": "main", "event": "push",
                "status": status, "conclusion": conclusion}
    monkeypatch.setattr(deploy, "request_json", lambda _: {"workflow_runs": [
        run(1, "completed", "success"), run(2, "completed", "failure")
    ]})
    assert not deploy.ci_passed(SHA)


@pytest.mark.parametrize("status,conclusion,expected", [
    ("completed", "success", True), ("completed", "skipped", False),
    ("in_progress", None, False), ("completed", "cancelled", False),
])
def test_only_success_authorizes_deploy(monkeypatch, status, conclusion, expected):
    monkeypatch.setattr(deploy, "request_json", lambda _: {"workflow_runs": [{
        "id": 1, "head_sha": SHA, "head_branch": "main", "event": "push",
        "status": status, "conclusion": conclusion,
    }]})
    assert deploy.ci_passed(SHA) is expected


def test_health_failure_rolls_back_and_remembers_failed_commit(monkeypatch, tmp_path):
    # Model a candidate starting unsuccessfully followed by a healthy old version.
    monkeypatch.setattr(deploy, "CURRENT", tmp_path)
    switch = Mock()
    monkeypatch.setattr(deploy, "switch_to", switch)
    monkeypatch.setattr(deploy, "restart", Mock())
    monkeypatch.setattr(deploy, "healthy", Mock(side_effect=[False, True]))
    monkeypatch.setattr(deploy, "write_state", Mock())
    state = {"deployed": OLD}
    with pytest.raises(RuntimeError, match="Candidate health"):
        deploy.activate(SHA, state)
    assert switch.call_args_list[-1].args == (str(tmp_path.resolve()),)
    assert state == {"deployed": OLD, "last_failed": SHA}


def test_failed_rollback_keeps_recovery_journal(monkeypatch):
    monkeypatch.setattr(deploy, "switch_to", Mock())
    monkeypatch.setattr(deploy, "restart", Mock())
    monkeypatch.setattr(deploy, "healthy", lambda: False)
    state = {"pending": {"sha": SHA, "previous": str(deploy.LEGACY)}}
    with pytest.raises(RuntimeError, match="Rollback health"):
        deploy.restore_pending(state)
    assert "pending" in state


def test_pending_ci_never_starts_build(monkeypatch, tmp_path):
    state = tmp_path / "state.json"
    state.write_text(json.dumps({"deployed": OLD}))
    monkeypatch.setattr(deploy, "STATE_FILE", state)
    monkeypatch.setattr(deploy, "main_head", lambda: SHA)
    monkeypatch.setattr(deploy, "ci_passed", lambda _: False)
    build = Mock()
    monkeypatch.setattr(deploy.subprocess, "run", build)
    deploy.poll()
    build.assert_not_called()


def test_superseded_commit_never_activates(monkeypatch, tmp_path):
    state = tmp_path / "state.json"
    state.write_text(json.dumps({"deployed": OLD}))
    monkeypatch.setattr(deploy, "STATE_FILE", state)
    monkeypatch.setattr(deploy, "main_head", Mock(side_effect=[SHA, "c" * 40]))
    monkeypatch.setattr(deploy, "ci_passed", lambda _: True)
    monkeypatch.setattr(deploy.subprocess, "run", Mock())
    activate = Mock()
    monkeypatch.setattr(deploy, "activate", activate)
    deploy.poll()
    activate.assert_not_called()


def test_invalid_sha_cannot_become_a_path():
    with pytest.raises(ValueError):
        deploy.checked_sha("../../another-service")
