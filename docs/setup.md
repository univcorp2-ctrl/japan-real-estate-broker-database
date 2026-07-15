# 初期設定ガイド

## 1. GitHub / Codespaces

リポジトリをCodespacesで開くと、`.devcontainer/devcontainer.json` によりPython 3.12環境と依存関係が自動準備されます。

## 2. Excel生成

```bash
python -m real_estate_db.build_excel
```

`database/` にExcel、CSV、NotionインポートCSV、集計Markdownが生成されます。通常はGitHub Actionsが自動実行するため、ローカル操作は不要です。

## 3. Google Drive

GitHubリポジトリはCloudflare Worker経由でGoogle Driveの `repos/japan-real-estate-broker-database` に完全同期されます。生成されたExcelも、Actionsの自動コミット後に同じフォルダへ同期されます。

## 4. Notion

### 必要なもの

- Notion Integration Token
- データベース配下のData Source ID
- 対象データベースをIntegrationへ共有する設定

### 推奨プロパティ

| プロパティ | 種類 |
|---|---|
| 会社名 | Title |
| 会社ID | Rich text |
| 地域 | Select |
| 都道府県 | Select |
| 営業エリア | Rich text |
| 戸建て取扱 | Select |
| 収益不動産取扱 | Select |
| 問い合わせフォーム | Select |
| 公式URL | URL |
| 問い合わせURL | URL |
| 確認日 | Date |
| 確認状態 | Select |
| 優先度 | Select |
| 特徴・強み | Rich text |
| 備考 | Rich text |

### GitHub Secrets

Repository Settings → Secrets and variables → Actions で次のSecret名を登録します。

- `NOTION_TOKEN`
- `NOTION_DATA_SOURCE_ID`

登録後、Actionsの `Sync to Notion` を実行します。

## 5. 本番運用に必要なもの

- GitHub Actionsが有効であること
- Google Drive同期WorkerのGoogle OAuth設定
- Notionへ直接同期する場合のみ上記2つのNotion Secrets
- 調査データ更新時の根拠URLと確認日

## 6. データ更新

1. `data/real_estate_brokers.csv` に会社を追加または修正
2. 公式URLと根拠URLを記入
3. 不明項目は `要確認` とする
4. pushするとCIとExcel生成が自動実行
5. 生成物がmainへコミットされGoogle Driveへ同期
