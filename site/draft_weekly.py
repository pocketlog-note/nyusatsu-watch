"""集めた公告（data/notices.jsonl）を1週間分集計し、週次ニュース（3,000〜8,000字）の下書きを content/ に作る。

使い方（site フォルダで実行）:
  python draft_weekly.py               今日の前日までの7日間（公告日）を集計
  python draft_weekly.py 2026-11-22    この日までの7日間を集計
  python draft_weekly.py 2026-11-22 --force   同じ日付の下書きがあっても作り直す

作るもの:
  content/<終了日>-weekly-it.md   draft: true の下書き
    自動で埋める: 見出し、リード、今週の数字、件数の推移（直近8週）、分野別・調達の形・地域別の内訳、
                  公告の一覧、用語の解説（glossary.json のうち件名に出てきたもの）、ファクト、次に注目する点、集計方法
    人（または Claude）が書く: 「注目の案件」3件の解説、ミハルの見解（【要確認】の目印を消すまで公開されない）
  data/reports/<終了日>.json      集計結果と各公告の公告文の抜粋（書くときの材料）
"""
import html
import json
import re
import sys
import unicodedata
from collections import Counter
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).parent
NOTICES = ROOT / "data" / "notices.jsonl"
JST = timezone(timedelta(hours=9))
LOCAL = ("都道府県", "市区町村")
API_CREDIT = "官公需情報ポータルサイト（https://www.kkj.go.jp/s/）の検索APIを用いて取得"

# 件名による分類（上から順に当てはめ、最初に合ったものにする）。本誌の分類で、目安。
FIELDS = [
    ("基幹系・標準化", r"標準化|基幹|共同利用型基幹|ガバメントクラウド|住民記録|住基|税務|戸籍"),
    ("教育", r"学校|教育|児童生徒|GIGA|ＧＩＧＡ|校務|教職員|学習"),
    ("福祉・子育て・医療", r"児童相談|保育|福祉|介護|子育て|子ども|健康|医療|病院|障害"),
    ("議会・会議録", r"議会|会議録|本会議"),
    ("財務・内部事務", r"財務会計|文書管理|内部事務|内部情報|庶務|人事|給与|タレントマネジメント|例規|電子決裁|起債|公営企業会計|電子請求|FAQ"),
    ("防災・安全", r"防災|避難|震度|緊急通報|災害"),
    ("インフラ・施設管理", r"道路|下水道|上下水道|水道|管路|台帳|墓地|GIS|地図|地籍|森林|積算"),
    ("窓口・住民サービス", r"窓口|コンビニ交付|電子申請|オンライン申請|申請管理|LINE|ＬＩＮＥ|SNS|ＳＮＳ|相談|予約|図書館|証明書|キャッシュレス|POS|ＰＯＳ|ホームページ|出願"),
    ("ネットワーク・基盤", r"ネットワーク|WAN|ＷＡＮ|LAN|ＬＡＮ|セキュリティ|UTM|ＵＴＭ|漏洩|無害化|メール|サーバ|端末|パソコン|複合機|クラウド|ファイル"),
]
FORMS = [
    ("意見招請", r"意見招請|意見等の招請|意見の招請"),
    ("プロポーザル", r"プロポーザル|企画提案"),
    ("賃貸借・リース", r"賃貸借|リース"),
    ("構築・導入・更新", r"構築|導入|更新|更改|改修|移行"),
    ("保守・運用", r"保守|運用|管理業務"),
    ("物品の購入", r"買入|購入|調達"),
]


def title_core(title):
    """件名から、公告ごとに変わる飾り（日付、ファイルの大きさ、「その1」など）を外した芯の部分。"""
    t = unicodedata.normalize("NFKC", title)
    t = re.sub(r"[（(][^）)]*(PDF|KB|MB|ファイル)[^）)]*[）)]", "", t)
    t = re.sub(r"入札説明書.*|その[0-9０-９]+.*|【[^】]*】|［[^］]*］|\[[^\]]*\]", "", t)
    t = re.sub(r"令和[0-9０-９]+年[0-9０-９]+月[0-9０-９]+日|[0-9]{4}年[0-9]+月[0-9]+日|公告|更新|\s", "", t)
    return t[:30]


def dedupe(ns, days=45):
    """同じ団体・同じ件名の公告が45日以内に重ねて出ていたら（その1／その2、再掲、二重登録など）最初の1件だけ残す。"""
    seen, out = {}, []
    for n in sorted(ns, key=lambda n: (n["issue_date"], n["key"])):
        k = (n["org"], title_core(n["title"]))
        d = date.fromisoformat(n["issue_date"])
        if k in seen and (d - seen[k]).days <= days:
            continue
        seen[k] = d
        out.append(n)
    return out


ZEN = str.maketrans("０１２３４５６７８９", "0123456789")


def stale(n):
    """件名の「令和N年度」が公告日の年度より前なら、古い公告の再登録とみなす（ポータルに過去の公告が新しい日付で載ることがある）。"""
    d = date.fromisoformat(n["issue_date"])
    fy = (d.year - 2018) if d.month >= 4 else (d.year - 2019)
    m = re.search(r"令和([0-9０-９]+)年度", n["title"])
    return bool(m) and int(m.group(1).translate(ZEN)) < fy


def load():
    ns = [json.loads(l) for l in NOTICES.read_text(encoding="utf-8").splitlines() if l.strip()]
    local = [n for n in ns if n["org_type"] in LOCAL and n["topics"] and n["issue_date"] and not stale(n)]
    return dedupe(local)


def in_week(n, start, end):
    return n["org_type"] in LOCAL and n["topics"] and start.isoformat() <= n["issue_date"] <= end.isoformat()


def classify(title, rules, other="その他"):
    for name, pat in rules:
        if re.search(pat, title):
            return name
    return other


def stats(ns):
    return {
        "total": len(ns),
        "hyojunka": sum(1 for n in ns if "hyojunka" in n["topics"]),
        "by_type": dict(Counter(n["org_type"] for n in ns)),
        "by_pref": Counter((n["pref"] or n["org"][:3]) for n in ns).most_common(),
        "orgs": len({n["org"] for n in ns}),
        "by_field": Counter(classify(n["title"], FIELDS) for n in ns).most_common(),
        "by_form": Counter(classify(n["title"], FORMS) for n in ns).most_common(),
    }


def esc(s):
    return html.escape(s, quote=True)


def pct(a, b):
    return round(a * 100 / b) if b else 0


def jday(d):
    return f"{d.month}月{d.day}日"


def bars(items, total, hi=None):
    mx = max((c for _, c in items), default=1) or 1
    rows = "".join(
        f'<div class="row"><span>{esc(k)}</span><div class="track"><div class="fill{" hi" if k == hi else ""}" '
        f'style="width:{round(c * 100 / mx)}%"></div></div><span>{c}件</span></div>' for k, c in items)
    return f'<div class="bars">{rows}</div>'


def join_jp(items, fmt="{k}（{c}件）"):
    return "、".join(fmt.format(k=k, c=c) for k, c in items)


def main(argv):
    force = "--force" in argv
    args = [a for a in argv if not a.startswith("--")]
    end = date.fromisoformat(args[0]) if args else datetime.now(JST).date() - timedelta(days=1)
    start = end - timedelta(days=6)
    p_end, p_start = start - timedelta(days=1), start - timedelta(days=7)

    all_ns = load()
    data_start = date.fromisoformat(min(n["issue_date"] for n in all_ns if n["issue_date"]))
    week = sorted([n for n in all_ns if in_week(n, start, end)], key=lambda n: (n["issue_date"], n["org"]))
    prev = [n for n in all_ns if in_week(n, p_start, p_end)]
    s, ps = stats(week), stats(prev)
    fetched = max((n["first_seen"][:10] for n in week), default="")
    if not week:
        print(f"{start}〜{end} は対象の公告が0件のため、記事は作りません")
        return 0

    out = ROOT / "content" / f"{end}-weekly-it.md"
    if out.exists() and not force:
        print(f"{out.name} はすでにあります（作り直すときは --force）")
        return 1

    # 直近8週の推移（データがある週だけ）
    trend = []
    for k in range(7, -1, -1):
        e = end - timedelta(days=7 * k)
        st = e - timedelta(days=6)
        if st < data_start:
            continue
        trend.append((f"{st.month}/{st.day}〜", sum(1 for n in all_ns if in_week(n, st, e))))
    t_counts = [c for _, c in trend]
    t_avg = sum(t_counts) / len(t_counts)

    report = ROOT / "data" / "reports" / f"{end}.json"
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(json.dumps({
        "period": [str(start), str(end)], "week": s, "prev_week": ps, "trend": trend,
        "notices": [{"issue_date": n["issue_date"], "org": n["org"], "org_type": n["org_type"], "title": n["title"],
                     "url": n["url"], "field": classify(n["title"], FIELDS), "form": classify(n["title"], FORMS),
                     "procedure": n["procedure"], "opening_date": n["opening_date"], "excerpt": n["excerpt"]}
                    for n in week]}, ensure_ascii=False, indent=1), encoding="utf-8")

    total = s["total"]
    diff = total - ps["total"]
    diff_txt = (f"前の週（{ps['total']}件）から{abs(diff)}件{'増え' if diff > 0 else '減り'}ました" if diff
                else f"前の週（{ps['total']}件）と同じ件数でした")
    md_start, md_end = jday(start), jday(end)
    city, pref = s["by_type"].get("市区町村", 0), s["by_type"].get("都道府県", 0)
    named = [(k, c) for k, c in s["by_field"] if k != "その他"] or s["by_field"]
    top_field, top_field_n = named[0]
    ties = [k for k, c in named if c == top_field_n]
    if len(ties) == 1:
        field_head = f"{top_field}が{top_field_n}件"
    else:
        field_head = f"{'と'.join(ties[:2])}が{top_field_n}件ずつ"
    top_form, top_form_n = s["by_form"][0]
    prefs_n = len(s["by_pref"])

    # 推移の説明
    if len(trend) >= 2:
        hi_w = max(trend, key=lambda x: x[1])
        lo_w = min(trend, key=lambda x: x[1])
        rank = sorted(t_counts, reverse=True).index(total) + 1
        trend_txt = (f"本誌がデータを集め始めた週からの{len(trend)}週で見ると、1週間あたりの件数は平均{t_avg:.1f}件でした。"
                     f"最も多かったのは{hi_w[0].rstrip('〜')}からの週の{hi_w[1]}件、最も少なかったのは{lo_w[0].rstrip('〜')}からの週の{lo_w[1]}件です。"
                     f"今週の{total}件はこの{len(trend)}週の中で{rank}番目に多い件数でした。")
    else:
        trend_txt = "比べられる週のデータがまだ少ないため、推移はこれから記録していきます。"

    # 直近4週を合わせた内訳
    st4 = max(end - timedelta(days=27), data_start)
    four = [n for n in all_ns if in_week(n, st4, end)]
    s4 = stats(four)
    weeks4 = ((end - st4).days + 1) // 7
    four_txt = (f"今週を含む直近{weeks4}週（{jday(st4)}〜{md_end}）の公告は、合わせて{s4['total']}件でした。"
                f"分野別では{join_jp(s4['by_field'][:4])}、調達の形では{join_jp(s4['by_form'][:3])}が多くなっています。"
                f"公告を出した団体は{s4['orgs']}団体で、そのうち市区町村の公告が{s4['by_type'].get('市区町村', 0)}件、"
                f"都道府県が{s4['by_type'].get('都道府県', 0)}件です。")
    four_top = [(k, c) for k, c in s4["by_field"] if k != "その他"][:1]
    if four_top:
        four_txt += f"1週だけで見ると件数の少ない分野でも、{weeks4}週を合わせると{four_top[0][0]}の公告が続いていることが分かります。"

    field_txt = join_jp(s["by_field"])
    form_txt = join_jp(s["by_form"])
    pref_txt = join_jp(s["by_pref"][:5])
    multi = [(o, c) for o, c in Counter(n["org"] for n in week).most_common() if c >= 2]
    multi_txt = (f"同じ団体から複数の公告が出たのは、{join_jp(multi)}でした。" if multi
                 else "今週は、1つの団体から複数の公告が出た例はありませんでした。")

    rows = "\n".join(
        f'<tr><td>{n["issue_date"][5:].replace("-", "/")}</td><td>{esc(n["org"])}</td>'
        f'<td>{esc(classify(n["title"], FIELDS))}</td>'
        f'<td><a href="{esc(n["url"])}" target="_blank" rel="noopener">{esc(n["title"][:70])}</a></td></tr>'
        for n in week)

    titles = " ".join(n["title"] for n in week)
    gloss = [g for g in json.loads((ROOT / "glossary.json").read_text(encoding="utf-8")) if re.search(g["pattern"], titles)]
    gloss_md = "\n\n".join(f"**{g['term']}**　{g['text']}" for g in gloss) or "今週の件名には、解説が必要な用語はありませんでした。"

    hyo_txt = (f"このうち、基幹業務システムの標準化や共同利用に関係する案件は{s['hyojunka']}件です。" if s["hyojunka"]
               else "基幹業務システムの標準化や共同利用に関係する案件は、今週はありませんでした。")

    title = f"自治体IT調達の公告まとめ（{md_start}〜{md_end}）　{total}件、{field_head}"
    md = f"""---
title: {title}
date: {end + timedelta(days=1)}
description: {md_start}〜{md_end}に公告された自治体の情報システム関連の調達は{total}件でした。{diff_txt}。分野別では{top_field}が{top_field_n}件、調達の形では{top_form}が{top_form_n}件でした。
category: 週次まとめ｜公告
big: {total}件
big_color: #0b5cad
lines: 自治体IT調達の公告 / （{md_start}〜{md_end}）
bubble: {"前の週より / " + str(abs(diff)) + ("件多いです" if diff > 0 else "件少ないです") if diff else "前の週と / 同じ件数です"}
x_text: 【今週の数字】{total}件\\n{md_start}〜{md_end}に公告された自治体の情報システム関連の調達は{total}件。{diff_txt}。分野別では{top_field}が{top_field_n}件でした。
draft: true
---

{md_start}から{md_end}までの7日間に、自治体が公告した情報システム関連の調達は{total}件でした。{diff_txt}。{hyo_txt}

この記事では、今週の公告を分野、調達の形、地域に分けて整理し、注目の案件と、公告の一覧をまとめています。

<div class="kpis"><div class="kpi"><div class="n">{total}件</div><div class="l">今週の公告（前の週 {ps['total']}件）</div></div><div class="kpi"><div class="n">{s['orgs']}団体</div><div class="l">公告を出した自治体</div></div><div class="kpi"><div class="n">{prefs_n}</div><div class="l">公告があった都道府県の数</div></div></div>

## 件数の推移

{trend_txt}

{bars(trend, sum(t_counts), hi=trend[-1][0])}

1週間の件数は祝日の有無や年度の予定によって上下するので、この記事では数週間の流れで見るようにしています。

## 直近{weeks4}週の動き

{four_txt}

{bars(s4['by_field'], s4['total'])}

## 発注したのは{s['orgs']}団体

公告を出した団体の内訳は、市区町村が{city}件（{pct(city, total)}%）、都道府県が{pref}件（{pct(pref, total)}%）でした。都道府県別に見ると、{pref_txt}の順に多くなっています。今週、公告があったのは{prefs_n}の都道府県です。

{multi_txt}

## 分野別の内訳

件名から分野を分けると、{field_txt}でした。分野は件名に含まれる語で本誌が分けたもので、1件を1つの分野に数えています。

{bars(s['by_field'], total, hi=top_field)}

## 調達の形

調達の形で見ると、{form_txt}でした。意見招請やプロポーザルは、入札とは進め方が違います。意見招請は仕様書の案への意見を集める段階なので、これから入札の公告が出ることになります。

{bars(s['by_form'], total, hi=top_form)}

## 注目の案件

【要確認】一覧から3件を選び、それぞれ「### 発注機関：件名の要点」の見出しを付けて、公告日、件名と公告文の抜粋（data/reports/{end}.json の excerpt）から分かること、事業者にとっての意味を書く。推測で数字や条件を足さない。

## 今週の公告の一覧

<div class="tbl"><table>
<tr><th>公告日</th><th>発注機関</th><th>分野</th><th>件名（公告ページへ）</th></tr>
{rows}
</table></div>

公告の内容や締切は、必ずリンク先の発注機関の公告で確かめてください。公告は訂正や取り消しが出ることがあります。

## 用語の解説

{gloss_md}

:::facts
- {md_start}〜{md_end}の自治体の情報システム関連の公告は{total}件｜{API_CREDIT}（{fetched}）、本誌集計
- 前の週（{jday(p_start)}〜{jday(p_end)}）は{ps['total']}件｜同上
- 標準化・共同利用に関係する案件は{s['hyojunka']}件｜同上（件名に「標準化」「基幹系」「共同利用型」などを含むもの）
- 市区町村の公告は{city}件、都道府県は{pref}件｜同上
- 分野別で最も多かったのは{top_field}の{top_field_n}件｜同上（件名による本誌の分類）
:::

:::opinion 【要確認】見解の見出し
【要確認】ミハルの見解を書く（3〜4段落）。材料は data/reports/{end}.json。ファクト欄と本文にない数字は書かない。
:::

:::next
- 来週の公告件数と、今週多かった分野が続くかどうか
- 意見招請の案件で、入札の公告が出るかどうか
- 今週の案件の開札と、落札結果の公表
:::

:::method
{API_CREDIT}した公告のうち、発注機関が都道府県・市区町村（一部事務組合などを含む）で、件名に「システム」「クラウド」「ネットワーク」などを含むものを数えました。工事や設備、測定機器の案件は除いています。分野と調達の形は件名に含まれる語で本誌が分けたもので、目安です。官公需情報ポータルサイトに載らない公告（パスワードが必要な調達システムだけで公開されたものなど）は含まれません。
:::
"""
    out.write_text(md, encoding="utf-8")
    print(f"下書きを作りました: content/{out.name}（{total}件、前の週 {ps['total']}件）")
    print(f"集計結果: data/reports/{report.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
