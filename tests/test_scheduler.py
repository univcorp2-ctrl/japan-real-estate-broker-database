import argparse
from pathlib import Path

import pytest

from scripts import scheduler


def test_parse_time() -> None:
    assert scheduler.parse_time("09:05") == (9, 5)
    assert scheduler.parse_time("23:59") == (23, 59)


@pytest.mark.parametrize("value", ["9", "24:00", "10:60", "aa:bb"])
def test_parse_time_rejects_invalid_values(value: str) -> None:
    with pytest.raises(argparse.ArgumentTypeError):
        scheduler.parse_time(value)


def test_launchd_plist_contains_schedule_and_paths(tmp_path: Path) -> None:
    content = scheduler.render_launchd_plist(
        Path("/tmp/venv/bin/python"),
        Path("/tmp/project/scripts/run_daily.py"),
        tmp_path,
        9,
        15,
    )
    assert scheduler.MAC_LABEL in content
    assert "<integer>9</integer>" in content
    assert "<integer>15</integer>" in content
    assert "/tmp/project/scripts/run_daily.py" in content


def test_systemd_timer_is_persistent() -> None:
    content = scheduler.render_systemd_timer(7, 30)
    assert "OnCalendar=*-*-* 07:30:00" in content
    assert "Persistent=true" in content


def test_systemd_service_uses_python_and_runner(tmp_path: Path) -> None:
    content = scheduler.render_systemd_service(
        Path("/opt/app/.venv/bin/python"),
        Path("/opt/app/scripts/run_daily.py"),
        tmp_path,
    )
    assert 'ExecStart="/opt/app/.venv/bin/python" "/opt/app/scripts/run_daily.py"' in content
    assert f'WorkingDirectory="{tmp_path}"' in content


def test_windows_command_contains_daily_time() -> None:
    command = scheduler.windows_create_command(
        Path(r"C:\project\.venv\Scripts\python.exe"),
        Path(r"C:\project\scripts\run_daily.py"),
        9,
        0,
    )
    assert command[:4] == ["schtasks", "/Create", "/TN", scheduler.WINDOWS_TASK]
    assert "/SC" in command
    assert "DAILY" in command
    assert command[-3:] == ["09:00", "/F"][-3:]
