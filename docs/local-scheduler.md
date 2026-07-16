# ローカル日次スケジューラー

このプロジェクトには、利用中のOSを自動判定して毎日データベースを更新するスケジューラー設定機能があります。

- macOS: `launchd`
- Linux: `systemd --user timer`
- Windows: タスクスケジューラ
- 初期実行時刻: 毎日09:00（端末のローカル時刻）
- 実行内容: Excel・CSV生成、データ検証、pytest実行、ログ保存

## 1. 初回準備

リポジトリ直下で実行します。

### macOS / Linux

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt -e .
.venv/bin/python scripts/scheduler.py install
```

### Windows PowerShell

```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt -e .
.\.venv\Scripts\python.exe .\scripts\scheduler.py install
```

これで毎日09:00の登録が完了します。

## 2. 実行時刻を変更

例: 毎日07:30

```bash
.venv/bin/python scripts/scheduler.py install --time 07:30
```

Windows:

```powershell
.\.venv\Scripts\python.exe .\scripts\scheduler.py install --time 07:30
```

再実行すると既存設定を同じ名前で更新します。

## 3. 状態確認

```bash
.venv/bin/python scripts/scheduler.py status
```

Windows:

```powershell
.\.venv\Scripts\python.exe .\scripts\scheduler.py status
```

## 4. 今すぐ実行

```bash
.venv/bin/python scripts/scheduler.py run-now
```

## 5. 設定解除

```bash
.venv/bin/python scripts/scheduler.py uninstall
```

## 6. 事前確認だけ行う

端末を変更せず、作成される設定とコマンドだけ確認できます。

```bash
.venv/bin/python scripts/scheduler.py install --dry-run
```

## 7. ログ

- 共通ログ: `logs/daily-run.log`
- macOS標準出力: `logs/launchd.out.log`
- macOS標準エラー: `logs/launchd.err.log`
- Linux詳細: `journalctl --user -u real-estate-broker-database.service`
- Windows詳細: タスクスケジューラの履歴

## 8. スリープ・電源OFF時

- Linuxのsystemd timerは `Persistent=true` のため、停止中に実行時刻を過ぎた場合、次回起動後に実行します。
- Windowsはタスク設定の「開始時刻を逃した場合にすぐ実行」に対応する既存PowerShellインストーラーも利用できます。
- macOSは起動中にlaunchdが実行します。長期間スリープする端末では、GitHub Actionsの日次実行が補完します。

## 9. GitHubとの二重化

ローカル端末とは別に、GitHub Actionsの `Publish database` も毎日09:00 JSTに動作します。そのため、端末が停止していてもExcel・CSV生成とGoogle Drive同期を継続できます。
