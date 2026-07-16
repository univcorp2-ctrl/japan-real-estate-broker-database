from pathlib import Path

import scripts.run_daily as runner


def test_daily_runner_uses_project_root() -> None:
    assert (runner.ROOT / "pyproject.toml").exists()
    assert runner.LOG_FILE == runner.ROOT / "logs" / "daily-run.log"


def test_logging_directory_is_created(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(runner, "LOG_DIR", tmp_path / "logs")
    monkeypatch.setattr(runner, "LOG_FILE", tmp_path / "logs" / "daily-run.log")
    runner.configure_logging()
    assert runner.LOG_DIR.exists()
