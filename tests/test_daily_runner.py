import sys

from real_estate_db import daily_runner as runner


def test_daily_runner_uses_project_root() -> None:
    assert (runner.ROOT / "pyproject.toml").exists()
    assert runner.LOG_FILE == runner.ROOT / "logs" / "daily-run.log"


def test_main_runs_build_then_tests(monkeypatch) -> None:
    commands: list[list[str]] = []
    monkeypatch.setattr(runner, "configure_logging", lambda: None)
    monkeypatch.setattr(runner, "run", commands.append)

    assert runner.main() == 0
    assert commands == [
        [sys.executable, "-m", "real_estate_db.build_excel"],
        [sys.executable, "-m", "pytest", "-q"],
    ]
