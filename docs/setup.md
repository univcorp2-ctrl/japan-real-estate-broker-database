# 初期設定ガイド

## 1. GitHub / Codespaces

リポジトリをCodespacesで開くと、`.devcontainer/devcontainer.json` によりPython 3.12環境と依存関係が自動準備されます。

## 2. Excel生成

```bash
python -m real_estate_db.build_excel
```

`database/` にExcel、CSV、NotionインポートCSV、集計Markdownが生成されます。

## 3. 毎日ローカル実行とスケジューラー登録

OSを自動判定する共通インストーラーを追加しています。

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

初期設定では毎日09:00に実行します。状態確認は `status`、今すぐ実行は `run-now`、解除は `uninstall` です。

```bash
.venv/bin/python scripts/scheduler.py status
.venv/bin/python scripts/scheduler.py run-now
.venv/bin/python scripts/scheduler.py uninstall
```

時刻を変更する例:

```bash
.venv/bin/python scripts/scheduler.py install --time 07:30
```

詳しい説明は [local-scheduler.md](local-scheduler.md) を参照してください。

## 4. GitHub Actionsの日次実行

GitHub Actionsの `Publish database` は毎日09:00 JSTに実行されます。ローカルPCが停止していても、GitHub側でExcelとCSVの生成が継続されます。

## 5. Google Drive

GitHubリポジトリはCloudflare Worker経由でGoogle Driveの `repos/japan-real-estate-broker-database` に完全同期されます。生成されたExcelも、Actionsの自動コミット後に同じフォルダへ同期されます。

## 6. Notion

Notionへ直接同期する場合は、対象データベースをIntegrationへ共有し、GitHub Secretsへ次の名前を登録します。

- `NOTION_TOKEN`
- `NOTION_DATA_SOURCE_ID`

登録後、Actionsの `Sync to Notion` を実行します。

## 7. 本番運用に必要なもの

- ローカル実行時は対象PCにPython仮想環境が存在すること
- ローカルスケジューラー登録時に、その端末のユーザー権限があること
- GitHub Actionsが有効であること
- Google Drive同期WorkerのGoogle OAuth設定
- Notionへ直接同期する場合のみNotion Secrets
- 調査データ更新時の根拠URLと確認日

## 8. データ更新

1. `data/real_estate_brokers.csv` に会社を追加または修正
2. 公式URLと根拠URLを記入
3. 不明項目は `要確認` とする
4. ローカルまたはGitHub Actionsが毎日Excelを生成
5. 生成物がmainへコミットされGoogle Driveへ同期
