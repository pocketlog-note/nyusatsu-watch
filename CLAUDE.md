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
