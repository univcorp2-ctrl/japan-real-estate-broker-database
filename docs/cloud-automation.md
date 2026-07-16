# クラウド完全自動化

## 目的

PCやローカルスケジューラーを使わず、GitHub Actionsだけで毎日次の処理を完結させます。

1. 国土交通省の公開「宅地建物取引業者検索」から新しい候補を取得
2. 関東を高頻度で巡回しながら全国47都道府県も順番に巡回
3. 会社ID、会社名、都道府県、免許行政庁、免許番号を重複排除
4. 新規会社をマスターCSVへ追加
5. 公式サイト候補を検索し、会社名と不動産関連表記を照合
6. 戸建て、収益不動産、その他物件、問い合わせフォーム、電話番号を自動判定
7. Excel、CSV、Notion取込CSV、地域別集計を生成
8. 日次レポートと再開位置を保存
9. GitHubのmainへ自動コミット
10. GitHub push webhookによりGoogle Driveへリポジトリ全体を同期
11. Notion Secretsが設定済みの場合だけNotionも同期

## 実行時刻

`.github/workflows/cloud-daily-pipeline.yml` は `Asia/Tokyo` の毎日09:17に実行します。GitHub側の混雑による遅延があっても、同一日の実行は一つに制限されます。

## 毎日増える仕組み

`config/cloud_pipeline.json` の `registry_schedule` に従い、公的登録検索の対象地域を毎日切り替えます。関東のコードを複数回含めることで、関東は他地域より高頻度で巡回します。

- 既定の新規追加上限: 10社/日
- 既定の公式サイト確認上限: 8社/日
- 公的検索: 1ページ/日、最大50件を候補として確認
- 重複判定: 公的候補ID、および正規化会社名＋都道府県

新規候補は `data/research_queue.csv` に保存されます。公式サイトを特定できなかった候補は削除せず、試行回数を記録して翌日以降に再調査します。

## データ品質

自動追加直後の行は `確認状態=公的登録確認・公式サイト要確認` です。国土交通省の検索結果URLを `根拠URL` に保存するため、出典へクリックできます。

公式サイトを確認できた行は以下を更新します。

- `公式URL`
- `問い合わせURL`
- `サービスURL`
- `電話番号`
- `戸建て取扱`
- `収益不動産取扱`
- `その他取扱物件`
- `問い合わせフォーム`
- `根拠URL`
- `確認日`
- `確認状態`

推測で「あり」にせず、ページ本文に対応キーワードがある場合だけ「あり」にします。それ以外は `要確認` のまま残します。

## 障害時の動作

公的検索や公式サイトへの通信が失敗しても、ワークフロー全体を即停止しません。

- 既存候補の調査を継続
- ExcelとCSVを再生成
- エラー内容を日次レポートへ保存
- 検索位置を進めず翌日再試行
- 生成物をActions artifactへ保存

CSV破損、重複ID、Excel生成失敗、テスト失敗はデータ破損につながるため、ワークフローを失敗として停止します。

## Google Drive

このリポジトリはGitHub push webhookからCloudflare Workerを経由して、Google Driveの `repos/japan-real-estate-broker-database` へ完全同期する設定です。日次ワークフローがmainへpushすると、ローカルPCを介さずDrive同期が始まります。

Google Driveへ保存される主なファイル:

- `database/real_estate_brokers.xlsx`
- `database/real_estate_brokers.csv`
- `database/notion_import.csv`
- `database/summary.md`
- `data/real_estate_brokers.csv`
- `data/research_queue.csv`
- `reports/YYYY-MM-DD.md`
- `reports/latest.json`
- `state/discovery_state.json`

## 手動実行

Actions画面の `Cloud daily discovery pipeline` から実行できます。入力欄で、その回だけ新規追加件数と公式サイト確認件数を変更できます。

## 設定ファイル

`config/cloud_pipeline.json` で以下を調整します。

- 1日あたりの追加件数
- 1日あたりの公式サイト確認件数
- 公的検索のページサイズ
- タイムアウト
- リクエスト間隔
- 最大HTMLサイズ
- 地域巡回順
- User-Agent

## セキュリティと負荷制御

- 公開情報のみを取得
- 1日1ページの公的検索
- 公式サイトアクセス間隔を設定
- `robots.txt` を確認
- HTML最大サイズを制限
- ログへSecretsを出力しない
- Notion連携はSecrets設定時のみ実行
