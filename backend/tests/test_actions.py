"""Starting programs through the desktop session (a pretend systemd - nothing opens)."""

import subprocess
import sys

import pytest

from contextos.agent import actions, apps, tools
from contextos.agent.apps import find_app, installed_command


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


# -- finding apps on Windows -----------------------------------------------------------


class FakeRegistry:
    """A pretend winreg holding App Paths entries, keyed by (hive, exe)."""

    HKEY_CURRENT_USER, HKEY_LOCAL_MACHINE = "HKCU", "HKLM"

    def __init__(self, app_paths: dict[tuple[str, str], str]):
        self.app_paths = app_paths

    def QueryValue(self, hive, key):  # noqa: N802 - mirrors winreg.QueryValue
        exe = key.rsplit("\\", 1)[-1]
        if (hive, exe) not in self.app_paths:
            raise FileNotFoundError(key)
        return self.app_paths[hive, exe]


@pytest.fixture
def windows(monkeypatch):
    """A pretend Windows PC: these programs on PATH, these App Paths entries."""
    def install(on_path=(), app_paths=None):
        monkeypatch.setattr(apps.shutil, "which",
                            lambda cmd: rf"C:\Windows\{cmd}" if cmd in on_path else None)
        monkeypatch.setitem(sys.modules, "winreg", FakeRegistry(app_paths or {}))
    return install


def test_windows_apps_are_found_by_their_exe_names(windows):
    windows(on_path={"explorer.exe", "calc.exe", "wt.exe"})
    assert installed_command(find_app("explorer")) == r"C:\Windows\explorer.exe"
    assert installed_command(find_app("calculator")) == r"C:\Windows\calc.exe"
    assert installed_command(find_app("windows terminal")) == r"C:\Windows\wt.exe"


def test_chrome_and_firefox_are_found_through_app_paths(windows, tmp_path):
    chrome, firefox = tmp_path / "chrome.exe", tmp_path / "firefox.exe"
    chrome.touch()
    firefox.touch()
    windows(app_paths={("HKLM", "chrome.exe"): str(chrome),
                       ("HKCU", "firefox.exe"): f'"{firefox}"'})  # some installers quote it
    assert installed_command(find_app("chrome")) == str(chrome)
    assert installed_command(find_app("firefox")) == str(firefox)


def test_stale_and_store_app_paths_are_not_used(windows, tmp_path):
    store_copy = tmp_path / "WindowsApps" / "wt.exe"
    store_copy.parent.mkdir()
    store_copy.touch()
    windows(app_paths={("HKLM", "chrome.exe"): str(tmp_path / "uninstalled" / "chrome.exe"),
                       ("HKCU", "wt.exe"): str(store_copy)})
    assert installed_command(find_app("chrome")) is None    # left behind by an uninstall
    assert installed_command(find_app("terminal")) is None  # only its PATH alias can start it


def test_other_systems_have_no_registry(windows, monkeypatch):
    windows()
    monkeypatch.setitem(sys.modules, "winreg", None)  # `import winreg` fails, as on Linux
    assert installed_command(find_app("chrome")) is None
