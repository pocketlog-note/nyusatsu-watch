"""weekly_manual.py の手書き部分を site/content/<日付>-weekly-it.md に差し込む。
yomiyasu の検査用に、手書き部分だけを _text/weekly/<日付>-final.md にも書き出す。

使い方（プロジェクトのルートで）: python _text/splice_manual.py [--publish]
  --publish  差し込んだ記事の draft: true を外す
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).parent))
from weekly_manual import MANUAL  # noqa: E402

publish = "--publish" in sys.argv
outdir = ROOT / "_text" / "weekly"
outdir.mkdir(exist_ok=True)
for end, m in MANUAL.items():
    path = ROOT / "site" / "content" / f"{end}-weekly-it.md"
    t = path.read_text(encoding="utf-8")
    t, n1 = re.subn(r"(## 注目の案件\n\n)【要確認】[^\n]*\n", lambda x: x.group(1) + m["cases"] + "\n", t)
    t, n2 = re.subn(r":::opinion 【要確認】[^\n]*\n【要確認】[^\n]*\n:::",
                    lambda x: f":::opinion {m['title']}\n{m['opinion']}\n:::", t)
    extra = "".join(f"- {f}\n" for f in m["facts"])
    t, n3 = re.subn(r"(:::facts\n(?:- [^\n]*\n)+)", lambda x: x.group(1) + extra, t, count=1)
    if (n1, n2, n3) != (1, 1, 1):
        raise SystemExit(f"{path.name}: 差し込み位置が見つかりません {(n1, n2, n3)}")
    if publish:
        t = t.replace("draft: true\n", "")
    path.write_text(t, encoding="utf-8")
    (outdir / f"{end}-final.md").write_text(
        f"# {end} の週\n\n## 注目の案件\n\n{m['cases']}\n\n## {m['title']}\n\n{m['opinion']}\n", encoding="utf-8")
    print(f"差し込みました: {path.name}")
