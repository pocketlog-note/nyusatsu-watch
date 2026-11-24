# niche-news-sites

## 目的
キュレーションに頼らない、ニッチ業界向けニュースサイトの企画と試作。一次データのファクトとキャラクターの見解を組み合わせた記事を、アイキャッチ画像付きで毎日投稿する形を目指す。

## ゴール／期限
- 5案のモックアップを比較し、本格的に作る案を決める（おすすめは案1 入札ウォッチ、次に案5 士業DXノート）
- 決めた案で、データ収集→記事の下書き→画像→人の確認→投稿 の流れを自動化する

## 技術スタック
- 静的HTML/CSS（モックアップ）
- Python 3.10 標準ライブラリのみ（`tools/make_eyecatch.py`）
- 投稿の仕組みは `play\pocket-log` のものを流用する予定

## 入札ウォッチ（site/）の公開の仕組み
- 公開先は「自前サイト＋X」に決定（2026-11-23）。構成は play\pocket-log と同じ: `site/content/*.md` → `site/build.py` → `site/docs/` → GitHub Actions（`.github/workflows/pages.yml`）で GitHub Pages。
- 記事の書き方は `site/build.py` の冒頭。`:::facts`（各行「- 事実｜出典」）、`:::opinion 見出し`、`:::next`、`:::method` のブロックで書く。
- ビルドすると `site/docs/images/eyecatch/<slug>.svg`（アイキャッチ）と `site/x-drafts/<slug>.txt`（X 投稿文の下書き）も作られる。X への投稿は当面手動。
- 公開されない条件: `draft: true`／`date` が未来（予約公開）／本文に【要確認】が残っている。
- コマンド（site フォルダで実行。`$env:PYTHONIOENCODING="utf-8"` を付けると文字化けしない）
  - 点検: `python check.py`（`--all` で下書きも）。公開対象にエラーがあると終了コード1
  - 本番ビルド: `python build.py`／下書き込み: `$env:INCLUDE_DRAFTS=1; python build.py`
  - プレビュー: `.claude/launch.json` の `site-preview`（http://localhost:8124）
- 未決・未着手（ユーザーの指示が要る）: GitHub アカウントとリポジトリ（匿名にするか）、`SITE_URL`、独自ドメイン、X アカウント、PNG 化（Pillow の追加が必要）、収集と下書き作成の定期実行。

## 公告データの収集（2026-11-23 作成）
- データ源: 官公需情報ポータルサイト（中小企業庁）の検索API `http://www.kkj.go.jp/api/`。仕様は https://www.kkj.go.jp/doc/ja/api_guide.pdf （V1.1）。国・都道府県・市区町村の**公告**が取れる。**落札結果・応札者数・落札率は取れない**（1者応札率の記事はこのデータだけでは書けない）。開札日もほとんど入っていない。
- 利用規約（https://www.kkj.go.jp/s/?tc=1 、2024-06-25 改定）: API を使うサイトは「API を用いている旨」とポータルへのリンクを載せる（フッターと about.md に記載済み）。同じサーバーから継続して大量にアクセスしない → 問い合わせは順番に、間を5秒あける。1日に数回まで。二次利用・転載についての定めは規約にない。
- 流れ（site フォルダで実行。`python -X utf8` を付けると表示が文字化けしない）
  1. `python collect.py`（直近7日）／`python collect.py 2026-11-01 2026-11-22`（期間指定）→ `data/notices.jsonl` に重複なく追記
  2. `python draft_weekly.py [終了日]` → `content/<終了日>-weekly-it.md`（draft、見解は【要確認】）と `data/reports/<終了日>.json`
  3. ミハルの見解を書いて【要確認】を消す → yomiyasu で推敲 → `python check.py --all` → 人が確認して `draft: true` を外す
- 判定の規則: 検索条件と件名の絞り込みは `queries.json`（`title_pattern`／`exclude_pattern`）。自治体かどうかは `collect.py` の `org_type`（機関名が「京都府京都市」のように都道府県名から始まるか等。国の機関にも市区町村コードが付くことがあるので、コードだけで判定しない）。規則を直したら `python collect.py --reclassify` で保存済みの全件に当て直す。
- 2026-11-23 時点: 11/9〜11/22 の2週間分 1,071件を取得。自治体のIT関連は 11/16〜22 が14件、前の週が9件。週次の下書き `content/2026-11-22-weekly-it.md` は実データで、見解まで書いてある（draft のまま）。
- `data/raw/`（API の応答そのまま）は git 管理外。

## 定期運用（2026-11-23 開始）
- 定期タスク `nyusatsu-watch-daily`（毎日10時30分ごろ。Claude アプリが起動中のとき。閉じていれば次回起動時）。Auto モードで保存。
- 毎日 `collect.py` を1回、月曜は前週の週次記事を作って見解・推敲・点検まで行い、通れば公開して push（ユーザー指示 2026-11-24）。手順は `plan/operations.md`、履歴は `plan/log.md`。

## 公開（2026-11-24）
- GitHub: 匿名アカウント `pocketlog-note` の公開リポジトリ `nyusatsu-watch`（ポケットログと同じアカウント。ユーザー判断）。公開URL: https://pocketlog-note.github.io/nyusatsu-watch/
- コミットの作者は `pocketlog-note` と noreply アドレス（ローカル設定）。公開前に、それまでの5件のコミットの作者を個人アドレスから書き換えた。個人のメールアドレスを出さない。
- ブランチは `main`。
- タスクの中身を変えるときはアプリの「Scheduled」から（`~\.claude\scheduled-tasks\` を直接編集しない）。手順の細部は `plan/operations.md` を直せばよい。
- サンプル記事 `2026-11-23-hyojunka-1sha.md` は架空の数字なので `draft: true` のまま。公開しない。

## よく使うコマンド
- プレビュー: `python -m http.server 8765`（`.claude\launch.json` に登録済み）→ http://localhost:8765
- アイキャッチ生成: `python tools/make_eyecatch.py eyecatch/01-nyusatsu.json`（1ファイルずつ）
- 文章の検査（yomiyasu）: `python C:/Users/Administrator/.claude/plugins/cache/yomiyasu/yomiyasu/3.2.3/skills/yomiyasu/scripts/yomiyasu_check.py run --source _text/0N-src.md --final _text/0N-final.md --doc-type article --fact-gaps`

## ファイル構成
- `index.html` 5案の比較、キャラクター、毎日の投稿の流れ
- `01-nyusatsu.html` 〜 `05-shigyo-ai.html` 各サイトの記事モックアップ
- `images/char-0N.svg` キャラクター（200×200）、`images/eyecatch-0N.svg` アイキャッチ（1200×630）
- `eyecatch/*.json` アイキャッチの中身（数字・説明・ひとこと）
- `PLAN.md` 記事の形・キャラクター設定・文体ルール（横展開やエージェントへの依頼に使う）
- `_text/` yomiyasu で推敲した記事本文（推敲前 src / 推敲後 final）

## ルール・注意点
- モックアップの数値・団体・出典はすべて架空。各ページ上部に明記する
- 記事は「ファクト（出典つき）」と「キャラクターの見解」を分ける。意見は見解欄だけに書く
- 見解欄はブロガー調でよい。本文とファクト欄は落ち着いた文体。画面の日本語は yomiyasu で推敲する
- 実在の企業・団体名を架空のデータと組み合わせない

## メモ・決定事項
- 2026-11-23 5案のモックアップを作成。対談形式をやめ「ファクト＋見解」形式に統一。キャラクター5体とアイキャッチ生成スクリプトを作成
- 未決: キャラクターに架空の体験（「ぼくが通った銭湯も」など）を語らせてよいか
- 未決: 公開先（ブログ基盤・SNS）
- 未着手: 実データの収集、PNG化（SNS向け）、pocket-log への接続
