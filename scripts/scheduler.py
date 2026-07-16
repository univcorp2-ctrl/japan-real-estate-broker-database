from __future__ import annotations

import argparse
import html
import os
import platform
import shlex
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUNNER = ROOT / "scripts" / "run_daily.py"
LOG_DIR = ROOT / "logs"

MAC_LABEL = "com.univcorp.realestatebroker.daily"
LINUX_NAME = "real-estate-broker-database"
WINDOWS_TASK = "RealEstateBrokerDatabaseDaily"


def parse_time(value: str) -> tuple[int, int]:
    try:
        hour_text, minute_text = value.split(":", 1)
        hour = int(hour_text)
        minute = int(minute_text)
    except (TypeError, ValueError) as exc:
        raise argparse.ArgumentTypeError("時刻は HH:MM 形式で指定してください") from exc
    if not 0 <= hour <= 23 or not 0 <= minute <= 59:
        raise argparse.ArgumentTypeError("時刻は 00:00〜23:59 の範囲で指定してください")
    return hour, minute


def run_command(command: list[str], *, dry_run: bool, check: bool = True) -> subprocess.CompletedProcess[str] | None:
    print("$", shlex.join(command))
    if dry_run:
        return None
    return subprocess.run(command, check=check, text=True)


def render_launchd_plist(python: Path, runner: Path, root: Path, hour: int, minute: int) -> str:
    stdout = root / "logs" / "launchd.out.log"
    stderr = root / "logs" / "launchd.err.log"
    values = {
        "python": html.escape(str(python)),
        "runner": html.escape(str(runner)),
        "root": html.escape(str(root)),
        "stdout": html.escape(str(stdout)),
        "stderr": html.escape(str(stderr)),
    }
    return f'''<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>{MAC_LABEL}</string>
  <key>ProgramArguments</key>
  <array>
    <string>{values["python"]}</string>
    <string>{values["runner"]}</string>
  </array>
  <key>WorkingDirectory</key><string>{values["root"]}</string>
  <key>StartCalendarInterval</key>
  <dict>
    <key>Hour</key><integer>{hour}</integer>
    <key>Minute</key><integer>{minute}</integer>
  </dict>
  <key>RunAtLoad</key><false/>
  <key>StandardOutPath</key><string>{values["stdout"]}</string>
  <key>StandardErrorPath</key><string>{values["stderr"]}</string>
</dict>
</plist>
'''


def _systemd_quote(value: Path) -> str:
    return '"' + str(value).replace("\\", "\\\\").replace('"', '\\"') + '"'


def render_systemd_service(python: Path, runner: Path, root: Path) -> str:
    return f"""[Unit]
Description=Refresh real-estate broker database
After=network-online.target
Wants=network-online.target

[Service]
Type=oneshot
WorkingDirectory={_systemd_quote(root)}
ExecStart={_systemd_quote(python)} {_systemd_quote(runner)}

[Install]
WantedBy=default.target
"""


def render_systemd_timer(hour: int, minute: int) -> str:
    return f"""[Unit]
Description=Run real-estate broker database refresh every day

[Timer]
OnCalendar=*-*-* {hour:02d}:{minute:02d}:00
Persistent=true
Unit={LINUX_NAME}.service

[Install]
WantedBy=timers.target
"""


def windows_create_command(python: Path, runner: Path, hour: int, minute: int) -> list[str]:
    task_command = f'"{python}" "{runner}"'
    return [
        "schtasks",
        "/Create",
        "/TN",
        WINDOWS_TASK,
        "/TR",
        task_command,
        "/SC",
        "DAILY",
        "/ST",
        f"{hour:02d}:{minute:02d}",
        "/F",
    ]


def install_macos(python: Path, hour: int, minute: int, dry_run: bool) -> None:
    plist = Path.home() / "Library" / "LaunchAgents" / f"{MAC_LABEL}.plist"
    content = render_launchd_plist(python, RUNNER, ROOT, hour, minute)
    print(f"write: {plist}")
    if not dry_run:
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        plist.parent.mkdir(parents=True, exist_ok=True)
        plist.write_text(content, encoding="utf-8")
    domain = f"gui/{os.getuid()}"
    run_command(["launchctl", "bootout", domain, str(plist)], dry_run=dry_run, check=False)
    run_command(["launchctl", "bootstrap", domain, str(plist)], dry_run=dry_run)
    run_command(["launchctl", "enable", f"{domain}/{MAC_LABEL}"], dry_run=dry_run)


def install_linux(python: Path, hour: int, minute: int, dry_run: bool) -> None:
    user_dir = Path.home() / ".config" / "systemd" / "user"
    service = user_dir / f"{LINUX_NAME}.service"
    timer = user_dir / f"{LINUX_NAME}.timer"
    print(f"write: {service}")
    print(f"write: {timer}")
    if not dry_run:
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        user_dir.mkdir(parents=True, exist_ok=True)
        service.write_text(render_systemd_service(python, RUNNER, ROOT), encoding="utf-8")
        timer.write_text(render_systemd_timer(hour, minute), encoding="utf-8")
    run_command(["systemctl", "--user", "daemon-reload"], dry_run=dry_run)
    run_command(["systemctl", "--user", "enable", "--now", f"{LINUX_NAME}.timer"], dry_run=dry_run)


def install_windows(python: Path, hour: int, minute: int, dry_run: bool) -> None:
    if not dry_run:
        LOG_DIR.mkdir(parents=True, exist_ok=True)
    run_command(windows_create_command(python, RUNNER, hour, minute), dry_run=dry_run)


def install(hour: int, minute: int, dry_run: bool) -> None:
    if not RUNNER.exists():
        raise FileNotFoundError(f"日次実行スクリプトが見つかりません: {RUNNER}")
    python = Path(sys.executable).resolve()
    system = platform.system()
    if system == "Darwin":
        install_macos(python, hour, minute, dry_run)
    elif system == "Linux":
        install_linux(python, hour, minute, dry_run)
    elif system == "Windows":
        install_windows(python, hour, minute, dry_run)
    else:
        raise RuntimeError(f"未対応OSです: {system}")
    print(f"設定完了: 毎日 {hour:02d}:{minute:02d} に実行します。")


def status(dry_run: bool) -> None:
    system = platform.system()
    if system == "Darwin":
        domain = f"gui/{os.getuid()}"
        run_command(["launchctl", "print", f"{domain}/{MAC_LABEL}"], dry_run=dry_run, check=False)
    elif system == "Linux":
        run_command(
            ["systemctl", "--user", "status", f"{LINUX_NAME}.timer", "--no-pager"],
            dry_run=dry_run,
            check=False,
        )
    elif system == "Windows":
        run_command(["schtasks", "/Query", "/TN", WINDOWS_TASK, "/V", "/FO", "LIST"], dry_run=dry_run, check=False)
    else:
        raise RuntimeError(f"未対応OSです: {system}")


def uninstall(dry_run: bool) -> None:
    system = platform.system()
    if system == "Darwin":
        plist = Path.home() / "Library" / "LaunchAgents" / f"{MAC_LABEL}.plist"
        domain = f"gui/{os.getuid()}"
        run_command(["launchctl", "bootout", domain, str(plist)], dry_run=dry_run, check=False)
        print(f"remove: {plist}")
        if not dry_run:
            plist.unlink(missing_ok=True)
    elif system == "Linux":
        user_dir = Path.home() / ".config" / "systemd" / "user"
        service = user_dir / f"{LINUX_NAME}.service"
        timer = user_dir / f"{LINUX_NAME}.timer"
        run_command(["systemctl", "--user", "disable", "--now", f"{LINUX_NAME}.timer"], dry_run=dry_run, check=False)
        print(f"remove: {service}")
        print(f"remove: {timer}")
        if not dry_run:
            service.unlink(missing_ok=True)
            timer.unlink(missing_ok=True)
        run_command(["systemctl", "--user", "daemon-reload"], dry_run=dry_run)
    elif system == "Windows":
        run_command(["schtasks", "/Delete", "/TN", WINDOWS_TASK, "/F"], dry_run=dry_run, check=False)
    else:
        raise RuntimeError(f"未対応OSです: {system}")
    print("スケジューラー設定を解除しました。")


def run_now(dry_run: bool) -> None:
    run_command([sys.executable, str(RUNNER)], dry_run=dry_run)


def main() -> int:
    parser = argparse.ArgumentParser(description="不動産業者データベースの日次実行スケジューラー")
    parser.add_argument("command", choices=["install", "status", "uninstall", "run-now"])
    parser.add_argument("--time", default="09:00", help="毎日の実行時刻 HH:MM（既定: 09:00）")
    parser.add_argument("--dry-run", action="store_true", help="変更せず実行内容だけ表示")
    args = parser.parse_args()

    try:
        hour, minute = parse_time(args.time)
        if args.command == "install":
            install(hour, minute, args.dry_run)
        elif args.command == "status":
            status(args.dry_run)
        elif args.command == "uninstall":
            uninstall(args.dry_run)
        else:
            run_now(args.dry_run)
    except (FileNotFoundError, RuntimeError, subprocess.CalledProcessError) as exc:
        print(f"エラー: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
