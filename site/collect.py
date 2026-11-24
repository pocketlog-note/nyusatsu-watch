"""官公需情報ポータルサイトの検索APIから、自治体IT調達の公告を集める。標準ライブラリだけで動く。

使い方（site フォルダで実行）:
  python collect.py                      直近7日分（公告日）を取得
  python collect.py 2026-11-01 2026-11-22   期間を指定して取得
  python collect.py --reclassify         API に問い合わせず、保存済みデータの判定（自治体か・テーマ）だけやり直す

出力:
  data/notices.jsonl   公告1件=1行。Key で重複を除き、何度実行しても同じ公告は1件にまとまる
  data/raw/<取得日>/    API の応答 XML そのまま（git 管理外）

検索の条件は queries.json で決める。

利用規約（https://www.kkj.go.jp/s/?tc=1）の要点:
  - サーバーに負荷をかけない。特定のサーバーから継続して大量にアクセスしない
    → 1回ずつ順番に問い合わせ、間に WAIT_SEC 秒あける。1日に数回の実行にとどめる
  - API を使うサイトには「API を用いている旨」とポータルサイトへのリンクを載せる（about.md とフッターに記載）
API の仕様: https://www.kkj.go.jp/doc/ja/api_guide.pdf （V1.1）
"""
import json
import re
import sys
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).parent
DATA = ROOT / "data"
NOTICES = DATA / "notices.jsonl"
API = "http://www.kkj.go.jp/api/"
UA = "niche-news-collector/0.1"
WAIT_SEC = 5
COUNT = 1000          # API の上限
JST = timezone(timedelta(hours=9))

PREF_HEAD = re.compile(r"^(北海道|東京都|京都府|大阪府|[^\s都道府県]{2,3}県)(.*)$")
NATIONAL = re.compile(r"^(国|内閣|衆議院|参議院|最高裁判所|会計検査院|人事院)|省|庁|裁判所|独立行政法人|国立研究開発法人|国立大学法人|大学共同利用機関|機構|日本司法支援センター")
LOCAL_TAIL = re.compile(r"(市|区|町|村)(役所|役場)?$|広域連合|一部事務組合|事務組合|企業団|消防組合")


def org_type(n):
    """発注機関を 都道府県 / 市区町村 / 国など に分ける（目安）。
    機関名は「京都府京都市」「香川県」のように都道府県名から始まる自治体が多いので、まずそれを見る。
    国の機関にも市区町村コードが付いていることがあるため、コードだけでは判定しない。"""
    name = n.get("org", "")
    m = PREF_HEAD.match(name)
    if m and not NATIONAL.search(name):
        rest = m.group(2)
        return "市区町村" if re.search(r"[市区町村]", rest) else "都道府県"
    if NATIONAL.search(name):
        return "国など"
    if LOCAL_TAIL.search(name) or n.get("city_code"):
        return "市区町村"
    return "不明"


def topics(n, queries):
    """件名が各テーマの title_pattern に合うかで、テーマを付ける。API は公告文全体を検索するため、件名で絞り直す。"""
    title = n.get("title", "")
    return [q["id"] for q in queries
            if re.search(q["title_pattern"], title)
            and not (q.get("exclude_pattern") and re.search(q["exclude_pattern"], title))]


def fetch(params, raw_dir, label):
    url = API + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=120) as res:
        body = res.read()
    raw_dir.mkdir(parents=True, exist_ok=True)
    (raw_dir / f"{label}.xml").write_bytes(body)
    root = ET.fromstring(body)
    err = root.findtext("Error")
    if err:
        raise RuntimeError(f"API エラー: {err}（{params}）")
    hits = int(root.findtext(".//SearchHits") or 0)
    results = []
    for s in root.iter("SearchResult"):
        rec = {c.tag: (c.text or "").strip() for c in s if c.tag != "Attachments"}
        rec["Attachments"] = [{"name": a.findtext("Name") or "", "uri": a.findtext("Uri") or ""}
                              for a in s.iter("Attachment")]
        results.append(rec)
    return hits, results


def daterange(start, end):
    d = start
    while d <= end:
        yield d
        d += timedelta(days=1)


def collect_query(q, start, end, raw_dir):
    """1つの検索条件で期間内の公告を集める。1,000件を超えたら1日ずつに分けて取り直す。"""
    params = {"Query": q["query"], "CFT_Issue_Date": f"{start}/{end}", "Count": COUNT}
    params.update(q.get("params", {}))
    hits, results = fetch(params, raw_dir, f"{q['id']}_{start}_{end}")
    print(f"  {q['id']} {start}〜{end}: {hits}件ヒット・{len(results)}件取得")
    if hits <= len(results) or start == end:
        if hits > len(results):
            print(f"  注意: {start} は {hits}件あり、{len(results)}件しか取れていません（検索条件を絞ってください）")
        return results
    out = []
    for d in daterange(start, end):
        time.sleep(WAIT_SEC)
        out += collect_query(q, d, d, raw_dir)
    return out


def normalize(rec, qid, fetched_at):
    def day(v):
        return v[:10] if v else ""
    return {
        "key": rec.get("Key", ""),
        "title": rec.get("ProjectName", ""),
        "org": rec.get("OrganizationName", ""),
        "org_type": "",
        "pref": rec.get("PrefectureName", ""),
        "city": rec.get("CityName", ""),
        "lg_code": rec.get("LgCode", ""),
        "city_code": rec.get("CityCode", ""),
        "category": rec.get("Category", ""),
        "procedure": rec.get("ProcedureType", ""),
        "issue_date": day(rec.get("CftIssueDate")),
        "tender_date": day(rec.get("TenderSubmissionDeadline")),
        "opening_date": day(rec.get("OpeningTendersEvent")),
        "period_end": day(rec.get("PeriodEndTime")),
        "url": rec.get("ExternalDocumentURI", ""),
        "attachments": rec.get("Attachments", []),
        "excerpt": re.sub(r"\s+", " ", rec.get("ProjectDescription", ""))[:400],
        "queries": [qid],
        "first_seen": fetched_at,
        "source": "官公需情報ポータルサイト検索API",
    }


def load_notices():
    notices = {}
    if NOTICES.exists():
        for line in NOTICES.read_text(encoding="utf-8").splitlines():
            if line.strip():
                n = json.loads(line)
                notices[n["key"]] = n
    return notices


def save_notices(notices):
    DATA.mkdir(exist_ok=True)
    rows = sorted(notices.values(), key=lambda n: (n["issue_date"], n["key"]))
    NOTICES.write_text("".join(json.dumps(n, ensure_ascii=False) + "\n" for n in rows), encoding="utf-8")


def main(argv):
    today = datetime.now(JST).date()
    queries = json.loads((ROOT / "queries.json").read_text(encoding="utf-8"))
    if argv == ["--reclassify"]:   # API に問い合わせず、保存済みの全件の判定だけやり直す
        notices = load_notices()
        for n in notices.values():
            n["org_type"] = org_type(n)
            n["topics"] = topics(n, queries)
        save_notices(notices)
        print(f"{len(notices)}件の判定をやり直しました")
        return
    if len(argv) == 2:
        start, end = date.fromisoformat(argv[0]), date.fromisoformat(argv[1])
    else:
        start, end = today - timedelta(days=7), today
    fetched_at = datetime.now(JST).isoformat(timespec="seconds")
    raw_dir = DATA / "raw" / today.isoformat()
    notices = load_notices()
    before = len(notices)
    for i, q in enumerate(queries):
        if i:
            time.sleep(WAIT_SEC)
        for rec in collect_query(q, start, end, raw_dir):
            n = normalize(rec, q["id"], fetched_at)
            if not n["key"]:
                continue
            if n["key"] in notices:
                old = notices[n["key"]]
                old["queries"] = sorted(set(old["queries"]) | {q["id"]})
            else:
                notices[n["key"]] = n
    for n in notices.values():   # 判定の規則を直したときも、保存済みの全件に当て直す
        n["org_type"] = org_type(n)
        n["topics"] = topics(n, queries)
    save_notices(notices)
    local = [n for n in notices.values() if n["org_type"] in ("都道府県", "市区町村")]
    on_topic = sum(1 for n in local if n["topics"])
    print(f"新規 {len(notices) - before}件。保存済み {len(notices)}件（うち自治体 {len(local)}件、"
          f"件名がテーマに合う自治体の公告 {on_topic}件）→ {NOTICES.relative_to(ROOT)}")


if __name__ == "__main__":
    main(sys.argv[1:])
