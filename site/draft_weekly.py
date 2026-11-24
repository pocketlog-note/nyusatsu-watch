"""集めた公告（data/notices.jsonl）を1週間分集計し、週次ニュースの下書きを content/ に作る。

使い方（site フォルダで実行）:
  python draft_weekly.py               今日の前日までの7日間（公告日）を集計
  python draft_weekly.py 2026-11-22    この日までの7日間を集計
  python draft_weekly.py 2026-11-22 --force   同じ日付の下書きがあっても作り直す

作るもの:
  content/<終了日>-weekly-it.md   draft: true の下書き
    - 見出し・リード・本文・ファクト・次に注目する点・集計方法 は自動で埋める
    - ミハルの見解は【要確認】の目印だけ置く。人（または Claude）が書いて目印を消すまで公開されない
  data/reports/<終了日>.json      集計結果（見解を書くときの材料）
"""
import html
import json
import sys
from collections import Counter
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).parent
NOTICES = ROOT / "data" / "notices.jsonl"
JST = timezone(timedelta(hours=9))
LOCAL = ("都道府県", "市区町村")
API_CREDIT = "官公需情報ポータルサイト（https://www.kkj.go.jp/s/）の検索APIを用いて取得"


def load():
    return [json.loads(l) for l in NOTICES.read_text(encoding="utf-8").splitlines() if l.strip()]


def in_week(n, start, end):
    return n["org_type"] in LOCAL and n["topics"] and start.isoformat() <= n["issue_date"] <= end.isoformat()


def stats(ns):
    return {
        "total": len(ns),
        "hyojunka": sum(1 for n in ns if "hyojunka" in n["topics"]),
        "by_type": dict(Counter(n["org_type"] for n in ns)),
        "by_pref": Counter((n["pref"] or n["org"][:3]) for n in ns).most_common(5),
        "orgs": len({n["org"] for n in ns}),
    }


def esc(s):
    return html.escape(s, quote=True)


def pct(a, b):
    return round(a * 100 / b) if b else 0


def main(argv):
    force = "--force" in argv
    args = [a for a in argv if not a.startswith("--")]
    end = date.fromisoformat(args[0]) if args else datetime.now(JST).date() - timedelta(days=1)
    start = end - timedelta(days=6)
    p_end, p_start = start - timedelta(days=1), start - timedelta(days=7)

    all_ns = load()
    week = sorted([n for n in all_ns if in_week(n, start, end)], key=lambda n: (n["issue_date"], n["org"]))
    prev = [n for n in all_ns if in_week(n, p_start, p_end)]
    s, ps = stats(week), stats(prev)
    fetched = max((n["first_seen"][:10] for n in week), default="")

    out = ROOT / "content" / f"{end}-weekly-it.md"
    if out.exists() and not force:
        print(f"{out.name} はすでにあります（作り直すときは --force）")
        return 1
    report = ROOT / "data" / "reports" / f"{end}.json"
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(json.dumps({"period": [str(start), str(end)], "week": s, "prev_week": ps,
                                  "notices": [{k: n[k] for k in ("issue_date", "org", "org_type", "title", "url", "topics")}
                                              for n in week]}, ensure_ascii=False, indent=1), encoding="utf-8")

    diff = s["total"] - ps["total"]
    diff_txt = (f"前の週（{ps['total']}件）から{abs(diff)}件{'増え' if diff > 0 else '減り'}ました" if diff
                else f"前の週と同じ件数でした")
    md_start, md_end = f"{start.month}月{start.day}日", f"{end.month}月{end.day}日"
    pref_txt = "、".join(f"{p}（{c}件）" for p, c in s["by_pref"][:3])
    city, pref = s["by_type"].get("市区町村", 0), s["by_type"].get("都道府県", 0)

    rows = "\n".join(
        f'<tr><td>{n["issue_date"][5:].replace("-", "/")}</td><td>{esc(n["org"])}</td>'
        f'<td><a href="{esc(n["url"])}" target="_blank" rel="noopener">{esc(n["title"][:60])}</a></td></tr>'
        for n in week)

    title = f"今週の自治体IT調達の公告は{s['total']}件　標準化・共同利用の関連は{s['hyojunka']}件"
    md = f"""---
title: {title}
date: {datetime.now(JST).date()}
description: {md_start}〜{md_end}に公告された自治体の情報システム関連の調達は{s['total']}件でした。{diff_txt}。
category: 週次まとめ｜公告
big: {s['total']}件
big_color: #0b5cad
lines: 今週の自治体IT調達の公告 / （{md_start}〜{md_end}）
bubble: {"前の週より / " + str(abs(diff)) + ("件多いです" if diff > 0 else "件少ないです") if diff else "前の週と / 同じ件数です"}
x_text: 【今週の数字】{s['total']}件\\n{md_start}〜{md_end}に公告された自治体の情報システム関連の調達は{s['total']}件。{diff_txt}。標準化・共同利用の関連は{s['hyojunka']}件です。
draft: true
---

{md_start}から{md_end}までの7日間に、自治体が公告した情報システム関連の調達は{s['total']}件でした。{diff_txt}。このうち、基幹業務システムの標準化や共同利用に関係する案件は{s['hyojunka']}件です。

## 発注したのは{s['orgs']}団体

内訳は市区町村が{city}件、都道府県が{pref}件でした。都道府県別では{pref_txt}が多くなっています。

## 今週の公告の一覧

<div class="tbl"><table>
<tr><th>公告日</th><th>発注機関</th><th>件名（公告ページへ）</th></tr>
{rows}
</table></div>

:::facts
- {md_start}〜{md_end}の自治体の情報システム関連の公告は{s['total']}件｜{API_CREDIT}（{fetched}）、本誌集計
- 前の週（{p_start.month}月{p_start.day}日〜{p_end.month}月{p_end.day}日）は{ps['total']}件｜同上
- 標準化・共同利用に関係する案件は{s['hyojunka']}件｜同上（件名に「標準化」「基幹系」「共同利用型」などを含むもの）
- 市区町村の公告は{city}件（{pct(city, s['total'])}%）、都道府県は{pref}件｜同上
:::

:::opinion 【要確認】見解の見出し
【要確認】ミハルの見解を書く。材料は data/reports/{end}.json。ファクトにない数字は書かない。
:::

:::next
- 来週の公告件数と、標準化・共同利用に関係する案件の数
- 今週の案件の開札と、落札結果の公表
:::

:::method
{API_CREDIT}した公告のうち、発注機関が都道府県・市区町村（一部事務組合などを含む）で、件名に「システム」「クラウド」「ネットワーク」などを含むものを数えました。工事や設備の案件は除いています。官公需情報ポータルサイトに載らない公告（パスワードが必要な調達システムだけで公開されたものなど）は含まれません。
:::
"""
    out.write_text(md, encoding="utf-8")
    print(f"下書きを作りました: content/{out.name}（{s['total']}件、前の週 {ps['total']}件）")
    print(f"集計結果: data/reports/{report.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
