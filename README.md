# ✺ Curiosity Radar — 好奇心レーダー

個人用のニュース＆OSS発見ダッシュボード。AI、GitHubプロジェクト、国内旅行、セキュリティ、インターネットの話題、ゲーム、収益化のアイデアを一か所に集め、興味の重みに応じて優先表示します。

## 設計書とCodex開発フロー

- [ユーザーストーリー・受入基準](docs/USER_STORIES.md)：実現したい体験、優先度、完成判定（US/AC ID）。
- [システム設計書](docs/SYSTEM_DESIGN.md)：アーキテクチャ、情報源、データ契約、推薦、安全性、運用。
- [Codex実装計画](docs/IMPLEMENTATION_PLAN.md)：PR-00からの段階的実装とテスト。
- [Codexへ最初に渡す指示](CODEX_START_HERE.md)：最初はPR-00のみ。

**この仕様書は将来の設計も含むため、すべて実装済みという意味ではありません。** GitHub Pagesへの初回デプロイと収集ジョブの単発成功は2026-10-23に確認済み。ただし、定期実行の継続稼働・各情報源の恒常的な取得成功・新しいv2仕様は未検証です。

## できること

- GitHub Search APIで最近作られた人気リポジトリと更新の活発なOSSを探索。スター増分は**前回保存時との比較**（「24時間の増分」とは限りません）。
- 公開RSSとCISA KEV、Hacker Newsから新着情報を収集。元記事へのリンクを優先。
- GitHub Actionsで1日2回を目安に自動収集し、GitHub Pagesへ静的配信（遅延する場合あり）。
- カテゴリ、検索、未読、ブックマーク、興味の重み、並べ替え。状態はブラウザーのlocalStorageに保存。
- OSS・事業仮説についてCodexに貼り付ける評価・検証指示をコピー。
- スマホ向け画面、PWAインストール対応（オフラインでは直近キャッシュ表示）。

### 重要な制限

- **AIによる要約・推薦ではありません**。v1ではRSS抜粋、GitHubメタデータ、ルールベースのスコア・推薦理由・収益化仮説を使います。LLM追加は次の段階です。
- **X/Twitterの人気ポスト自動収集はしません**。X公式APIの利用や手動で選択した投稿の公式埋め込みが安全な拡張方針です。Hacker NewsのデータをX人気ポストとして表示しません。
- 収益性・OSSの安全性・ライセンス適合性は確認していません。第三者OSSの実行前に必ず検証してください。
- セキュリティの緊急対応には必ず原典を参照してください。CISA KEVのリンクはCVE詳細であり、該当製品の利用確認が必要です。
- 「デモデータ」のままなら実ニュースの取得・公開はまだ行われていません。

## GitHubへの公開手順（初回）

1. GitHubで **新規リポジトリ** `curiosity-radar` を作成します。既存リポジトリを使わないでください。GitHub FreeならPages公開のため **Public** を選びます。GitHub Pro等ならPrivateリポジトリからのPages公開も可能ですが、**Pagesサイト自体は一般公開されます**。機密情報は含めないでください。
2. このフォルダーの中身（`index.html`、`scripts/`、`.github/`、`data/`など）をそのリポジトリの `main` ブランチの**直下**にプッシュします。zipファイルそのものをプッシュするだけでは展開されません。
3. GitHubの **Settings → Pages → Build and deployment → Source: GitHub Actions** を選びます。
4. **Actions → Refresh and publish Curiosity Radar → Run workflow** で初回更新します。
5. Actionsの実行成功後、Pagesで表示されたURLを開きます。通常 `https://<ユーザー名>.github.io/curiosity-radar/` ですが、必ず実際のPages URLを確認してください。

個人情報は含めず、Pages公開用アーティファクトには `index.html`・静的アセット・公開ニュースJSONだけをコピーします。

### Actionsの運用・復旧

- PRでは `test` ジョブだけ実行し、収集・データ保存・Pages公開は行いません。Pythonテスト、JS構文、公開JSONを検証します。
- mainへのpush（`data/news.json`だけの更新を除く）、定期実行、mainを選択した手動実行では、`test` → `collect` → `deploy` の順に進みます。定期実行は07:30／19:30 JST目安で、遅延や長期無活動による停止があり得ます。復旧時はActions画面でスケジュール状態を確認し、mainの `Run workflow` を実行してください。
- 権限はテストが `contents: read`、収集・スナップショット保存が `contents: write`、公開が `pages: write`／`id-token: write` です。PagesのSourceは事前にGitHub Actionsへ設定してください（workflowによるPagesの自動有効化は行いません）。
- テスト失敗時のマージ自体を防ぐには、SettingsのRulesets／Branch protectionでmainへのPRと、このworkflowの `test` 成功を必須にしてください。workflowだけではマージ制限を設定できません。
- スナップショットのpushが拒否された場合はActionsログとリポジトリ／組織の書き込みポリシーを確認してください。従来どおり配信は継続しますが、次回のスター増分は最後に**保存できた**スナップショットとの差になります。
- 全取得失敗はジョブを失敗させて既存JSON・公開サイトを保持します。不正な候補も公開せず、正常な候補だけ一時ファイルから原子的に置換します。一部失敗はソース名・例外分類を `errors` に残します（生の例外詳細は公開しません）。
- デモは `mode=demo`、実収集は `mode=live`。古いライブデータもライブのまま元の `generated_at` を維持し、鮮度を偽りません。部分成功・48時間超の表示改善は後続PRの対象です。
- 公開後はPagesの一覧、`data/news.json` の `mode`・件数・`generated_at` と画面の更新日時を照合してください。CI成功だけでは外部API・Pagesの正常動作の証明にはなりません。
- 不具合時は原因コミットをrevertし、mainで手動実行します。収集障害中は既存Pagesを維持し、必要なら最後の正常なPagesアーティファクトを再デプロイしてください。リポジトリ全体を初期化しないでください。

### ローカルで試す

```bash
cd curiosity-radar
python -m unittest discover -s tests -v
python -m http.server 8000
# http://localhost:8000 をブラウザーで表示。初期状態は明示的なプレビュー用データ。

# 実際の情報を収集する場合（ネット接続が必要）
python scripts/collect.py
```

## 技術構成

- HTML / CSS / Vanilla JS：ビルド・JS依存なし、スマホ優先
- Python 3.12標準ライブラリ：RSS/Atom/RDF、公開API取得、正規化、簡易スコアリング
- GitHub Actions + Pages：無料枠や利用規約の範囲で定期更新
- localStorage：個人設定・既読・保存を端末内に保持（同期しない）

## ソースと帰属

- GitHub Search API: https://docs.github.com/en/rest/search/search#search-repositories
- Hacker News Algolia API: https://hn.algolia.com/api
- JVN: https://jvn.jp/rss/jvn.rdf
- JPCERT/CC: https://www.jpcert.or.jp/rss/jpcert.rdf
- IPA: https://www.ipa.go.jp/security/alert-rss.rdf
- CISA KEV: https://www.cisa.gov/known-exploited-vulnerabilities-catalog
- Cisco Talos脅威研究: https://blog.talosintelligence.com/rss/ （「VRT」がTalos Vulnerability Research Teamの意味かは未確認）
- Google News RSS検索: Google Newsの検索結果を各カテゴリに利用。検索・ソースの網羅性は保証できません。

収集したニュースの全文や画像は転載しません。抜粋の利用・再配布は情報元の条件に従い、商用利用の前に見直してください。

## 今後の改善（Codex向け）

1. RSSの日本語品質評価、取得元のドメイン検証、重複のクラスタリング、非日本語記事の適切な翻訳。
2. 許可済みのLLM APIによる「要点・具体的な応用・事実と仮説の区別」。秘密鍵はGitHub Actions secretsに限定し、出力コストに上限を設ける。
3. フィードの正常性テスト、取得失敗通知、参照元ごとの取得成功率、変更検知。安全なURLの許可リストとレート制限。
4. SNS枠：X公式の提供方法が利用可能な場合のみ組み込み。代替でBlueskyの公開APIを検討。
5. 自分専用の旅行興味地点・実装中プロジェクトを追加できる画面。プライベート情報を公開サイトのリポジトリに保存しない。
6. 収益化の検証用テンプレート（顧客インタビュー、競合調査、検証前提、ランニング費用）を追加。

## セキュリティ・プライバシー

公開GitHubリポジトリとPages上の `data/news.json` は誰でも閲覧できるため、個人の会話履歴、金融状況、シークレット、ログインCookie等を絶対に配置しないこと。ユーザーの興味の重みは公開JSONには含めずブラウザー内だけに保存します。リンクは外部の情報源へ移動します。HTTP通信、外部の入力に対して安全性を保証しません。


## v2 の企画・設計（まだ未実装）

ユーザーの追加要望をもとに、ニュースを集める方針を「量より一次情報の発見」に変更する計画を作成しました。現在の収集・表示プログラムがすでに対応しているわけではありません。

- [v2追加ユーザーストーリーと受入基準](docs/USER_STORIES_V2.md)
- [情報源・編集ポリシー](docs/EDITORIAL_POLICY_V2.md)
- [記事詳細・ChatGPT考察導線](docs/ARTICLE_EXPERIENCE_V2.md)
- [プロジェクトのルールとChatGPT/Codexの役割](AGENTS.md)

大きな開発変更はCodexで細かなPull Requestに分けて実施します。議論で決めた要件はまずここに記録し、実装済みの機能と混同しないでください。


## 次のプロジェクトでも再利用する開発ルール

- [新しいものを作るときの共通プレイブック](docs/PROJECT_CREATION_PLAYBOOK.md) — 規模別の準備、企画テンプレート、PR開発、完成定義
- [共通AGENTS.mdテンプレート](templates/COMMON_AGENTS_TEMPLATE.md) — 別プロジェクトに持ち込む短い不変条件の雛形。**このパスにあるだけでは自動適用されない**
- [Curiosity Radar初動レビュー](docs/KICKOFF_RETROSPECTIVE.md) — 確認できた成功・改善すべきこと・優先順位・検証方法

この共通ルールはCuriosity Radar専用の既存 [AGENTS.md](AGENTS.md) と役割が異なる。共通指示をすべてのリポジトリに自動適用したい場合は、使用するCodex環境のグローバル指示を別途設定・確認すること。既存プロジェクトの製品ルールはルートのAGENTS.mdを正本とする。
