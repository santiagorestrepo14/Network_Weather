import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from network_weather.windows_startup import (
    read_startup_command,
    set_startup_enabled,
    startup_command,
)


def test_startup_command_uses_pythonw_when_available(tmp_path):
    python = tmp_path / "python.exe"
    pythonw = tmp_path / "pythonw.exe"
    python.write_bytes(b"")
    pythonw.write_bytes(b"")
    assert startup_command(str(python), frozen=False) == (
        f'"{pythonw}" -m network_weather.desktop')
    assert startup_command(str(python), frozen=True) == f'"{python}"'


def test_startup_command_rejects_windows_run_length_limit():
    with pytest.raises(ValueError, match="260"):
        startup_command(str(Path("C:/") / ("a" * 255) / "NetworkWeather.exe"), frozen=True)


def test_registry_toggle_uses_only_per_user_run_entry(monkeypatch):
    values = {}

    class Key:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            pass

    def open_key(root, path, _reserved, access):
        assert root == "HKCU"
        assert path == r"Software\Microsoft\Windows\CurrentVersion\Run"
        assert access in ("READ", "WRITE")
        return Key()

    def query(_key, name):
        if name not in values:
            raise FileNotFoundError
        return values[name], "REG_SZ"

    def delete(_key, name):
        if name not in values:
            raise FileNotFoundError
        del values[name]

    fake = SimpleNamespace(
        HKEY_CURRENT_USER="HKCU", KEY_READ="READ", KEY_SET_VALUE="WRITE",
        REG_SZ="REG_SZ", OpenKey=open_key, CreateKeyEx=open_key,
        QueryValueEx=query,
        SetValueEx=lambda _key, name, _reserved, kind, value: values.update({name: value}),
        DeleteValue=delete,
    )
    monkeypatch.setitem(sys.modules, "winreg", fake)
    assert read_startup_command() is None
    command = '"C:\\Program Files\\NetworkWeather\\NetworkWeather.exe"'
    set_startup_enabled(True, command)
    assert read_startup_command() == command
    set_startup_enabled(False)
    assert read_startup_command() is None
