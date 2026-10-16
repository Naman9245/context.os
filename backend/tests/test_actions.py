"""Starting programs through the desktop session (a pretend systemd - nothing opens)."""

import subprocess

import pytest

from contextos.agent import actions, tools
from contextos.agent.apps import find_app


class FakeSystemd:
    def __init__(self, *, run_ok=True, states=(("active", "success"),), log=""):
        self.run_ok = run_ok
        self.states = list(states)
        self.log = log
        self.calls: list[list[str]] = []
        self.popen: list[list[str]] = []

    def run(self, argv, **kw):
        self.calls.append(argv)
        out, code = "", 0
        if argv[0] == "systemd-run":
            code = 0 if self.run_ok else 1
        elif argv[:3] == ["systemctl", "--user", "show"]:
            state, result = self.states.pop(0) if len(self.states) > 1 else self.states[0]
            out = f"ActiveState={state}\nResult={result}\n"
        elif argv[0] == "journalctl":
            out = self.log
        return subprocess.CompletedProcess(argv, code, out, "no user session" if code else "")

    def Popen(self, argv, **kw):  # noqa: N802 - mirrors subprocess.Popen
        self.popen.append(argv)

    def ran(self, program: str) -> list[list[str]]:
        return [c for c in self.calls if c[0] == program]


@pytest.fixture
def systemd(monkeypatch):
    def install(**kw) -> FakeSystemd:
        fake = FakeSystemd(**kw)
        monkeypatch.setattr(actions.sys, "platform", "linux")
        monkeypatch.setattr(actions.shutil, "which", lambda name: f"/usr/bin/{name}")
        monkeypatch.setattr(actions.subprocess, "run", fake.run)
        monkeypatch.setattr(actions.subprocess, "Popen", fake.Popen)
        monkeypatch.setattr(actions.time, "sleep", lambda s: None)
        monkeypatch.setattr(actions, "SETTLE_SECONDS", 0.05)
        return fake
    return install


def test_apps_are_started_by_the_desktop_session(systemd):
    fake = systemd()
    actions._spawn(["/snap/bin/code"])
    (cmd,) = fake.ran("systemd-run")
    assert cmd[:3] == ["systemd-run", "--user", "--quiet"]
    assert "ExitType=cgroup" in cmd
    assert cmd[-2:] == ["--", "/snap/bin/code"]
    assert fake.popen == []  # not a child of ContextOS


def test_an_app_that_dies_at_once_is_reported(systemd):
    fake = systemd(states=[("failed", "exit-code")],
                   log="Started contextos-code.service\n"
                       "snap-confine is packaged without necessary permissions\n"
                       "contextos-code.service: Main process exited, code=exited")
    with pytest.raises(actions.LaunchFailed, match="snap-confine"):
        actions._spawn(["/snap/bin/code"])
    assert any(c[2] == "reset-failed" for c in fake.ran("systemctl"))


def test_handing_off_to_an_already_open_app_is_success(systemd):
    fake = systemd(states=[("inactive", "success")])
    actions._spawn(["xdg-open", "https://www.youtube.com"])
    assert len(fake.ran("systemctl")) == 1  # done at the first look


def test_without_a_user_session_it_starts_the_program_itself(systemd):
    fake = systemd(run_ok=False)
    actions._spawn(["discord"])
    assert fake.popen == [["discord"]]


def test_without_systemd_it_starts_the_program_itself(systemd, monkeypatch):
    fake = systemd()
    monkeypatch.setattr(actions.shutil, "which", lambda name: None)
    actions._spawn(["discord"])
    assert fake.popen == [["discord"]] and fake.calls == []


def test_khushi_admits_when_an_app_did_not_open(monkeypatch):
    def broken(app):
        raise actions.LaunchFailed("snap-confine is packaged without necessary permissions")

    monkeypatch.setattr(actions, "launch_app", broken)
    from datetime import datetime

    reply = tools.Tools(None, None, datetime.now()).open("vs code")  # type: ignore[arg-type]
    assert reply.text.startswith("I tried to open VS Code, but it closed straight away")
    assert reply.actions == [{"label": "Couldn't open VS Code", "ok": False}]


def test_vs_code_names(monkeypatch):
    for said in ("vs code", "vscode", "visual studio code", "code editor"):
        assert find_app(said).key == "vscode"
