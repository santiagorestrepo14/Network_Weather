"""Per-user Windows logon startup. No service or administrator rights required."""

from __future__ import annotations

from pathlib import Path

RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
VALUE_NAME = "NetworkWeather"


def startup_command(executable: str, *, frozen: bool) -> str:
    """Build the command Windows will run at logon for this installation."""
    path = Path(executable)
    if not frozen and path.name.lower() == "python.exe":
        pythonw = path.with_name("pythonw.exe")
        if pythonw.is_file():
            path = pythonw
    command = f'"{path}"'
    if not frozen:
        command += " -m network_weather.desktop_launcher"
    if len(command) > 260:
        raise ValueError("Windows startup command exceeds 260 characters")
    return command


def read_startup_command() -> str | None:
    import winreg

    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_READ) as key:
            value, _kind = winreg.QueryValueEx(key, VALUE_NAME)
    except FileNotFoundError:
        return None
    return value if isinstance(value, str) else None


def set_startup_enabled(enabled: bool, command: str | None = None) -> None:
    import winreg

    if enabled:
        if not command or len(command) > 260:
            raise ValueError("A startup command of at most 260 characters is required")
        with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, RUN_KEY, 0,
                                winreg.KEY_SET_VALUE) as key:
            winreg.SetValueEx(key, VALUE_NAME, 0, winreg.REG_SZ, command)
    else:
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0,
                                winreg.KEY_SET_VALUE) as key:
                winreg.DeleteValue(key, VALUE_NAME)
        except FileNotFoundError:
            pass
