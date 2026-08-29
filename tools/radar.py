# -*- coding: utf-8 -*-
"""발주레이더 파이프라인: 네이버 카페 발주 게시판 스윕 → 주간 리포트 HTML 생성.

사용법:
    python tools/radar.py sweep   [--days 10]   # 수집 → data/leads-YYYYMMDD.json
    python tools/radar.py build   [--data 경로]  # 최신 JSON → reports/YYYY-MM-DD.html + index 갱신
    python tools/radar.py all     [--days 10]   # sweep + build

리포트에는 공개 게시글의 제목·게시판·작성일·댓글수·원문링크만 담는다.
작성자 닉네임은 수집하지 않고, 제목에 연락처가 있으면 마스킹한다.
"""
import argparse
import glob
import json
import os
import re
import sys
import time
import urllib.request
from datetime import datetime, timedelta, timezone

KST = timezone(timedelta(hours=9))
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
API = ("https://apis.naver.com/cafe-web/cafe2/ArticleListV2dot1.json"
       "?search.clubid={clubid}&search.page={page}&search.perPage=50")
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}

TECH = re.compile(r"(AI|A\.I|인공지능|챗\s?GPT|GPT|클로드|Claude|Gemini|제미나이|코파일럿|Copilot|"
                  r"생성형|LLM|RPA|자동화|챗봇|데이터|머신러닝|딥러닝|에이전트|프롬프트|바이브|코딩|파이썬|Python)",
                  re.IGNORECASE)

INTENT = re.compile(r"(문의|견적|제안|요청|의뢰|모집|섭외|추천|구합|찾습)")

CAFES = [
    {
        # 인사혁신 게시판엔 칼럼 글이 많아 발주 의도 토큰까지 요구한다.
        "clubid": 10733571, "slug": "ak573", "name": "기업 인사담당자 커뮤니티",
        "boards": ("강의", "강사", "교육기획", "AI"),   # menuName 부분일치
        "tech_required": True, "intent_required": True, "category": "AI 교육·강의 발주",
    },
    {
        "clubid": 24229900, "slug": "peopleofit", "name": "기업 IT담당자 커뮤니티",
        "boards": ("견적",),
        "tech_required": False, "category": "SW·시스템 구축 발주",
    },
    {
        # 섭외 공고는 제목이 기관명뿐(상세는 본문)이라 기술토큰 필터를 걸지 않는다.
        "clubid": 31209799, "slug": "kiea", "name": "강사협회 커뮤니티",
        "boards": ("섭외",),
        "tech_required": False, "category": "공공·기관 강사 섭외",
    },
]

CLOSED = re.compile(r"\[\s*(마감|취소|완료)\s*\]")

EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
PHONE = re.compile(r"(01[016789]|0\d{1,2})[-.\s]?\d{3,4}[-.\s]?\d{4}")


def mask(text):
    text = EMAIL.sub("[이메일 마스킹]", text)
    text = PHONE.sub("[연락처 마스킹]", text)
    return text


def fetch(clubid, page):
    url = API.format(clubid=clubid, page=page)
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=20) as r:
        d = json.load(r)
    return d["message"]["result"]["articleList"]


def sweep(days):
    cutoff = datetime.now(KST) - timedelta(days=days)
    cutoff_ms = int(cutoff.timestamp() * 1000)
    rows, stats = [], []
    for cafe in CAFES:
        kept, scanned, page = 0, 0, 1
        while page <= 40:
            try:
                arts = fetch(cafe["clubid"], page)
            except Exception as e:
                print(f"  ! {cafe['slug']} p{page} 실패: {e}", file=sys.stderr)
                break
            if not arts:
                break
            oldest = min(a.get("writeDateTimestamp", 0) for a in arts)
            for a in arts:
                ts = a.get("writeDateTimestamp", 0)
                if ts < cutoff_ms:
                    continue
                scanned += 1
                menu = a.get("menuName") or ""
                subject = (a.get("subject") or "").strip()
                if not any(b in menu for b in cafe["boards"]):
                    continue
                if CLOSED.search(subject):
                    continue
                if cafe["tech_required"] and not TECH.search(subject):
                    continue
                if cafe.get("intent_required") and not INTENT.search(subject):
                    continue
                rows.append({
                    "category": cafe["category"],
                    "source": cafe["name"],
                    "board": menu,
                    "subject": mask(subject),
                    "ai": bool(TECH.search(subject)),
                    "date": datetime.fromtimestamp(ts / 1000, KST).strftime("%Y-%m-%d"),
                    "ts": ts,
                    "comments": a.get("commentCount", 0),
                    "reads": a.get("readCount", 0),
                    "url": f"https://cafe.naver.com/{cafe['slug']}/{a['articleId']}",
                })
                kept += 1
            if oldest < cutoff_ms:
                break
            page += 1
            time.sleep(0.4)
        stats.append({"source": cafe["name"], "scanned": scanned, "kept": kept})
        print(f"  {cafe['slug']}: {scanned}건 스캔 → {kept}건 채택 ({page}p)")
    # articleId 중복 제거(공지 반복 노출 대비) 후 최신순
    seen, uniq = set(), []
    for r in sorted(rows, key=lambda r: -r["ts"]):
        if r["url"] in seen:
            continue
        seen.add(r["url"])
        uniq.append(r)
    today = datetime.now(KST).strftime("%Y%m%d")
    out = {
        "generated": datetime.now(KST).strftime("%Y-%m-%d %H:%M"),
        "period_days": days,
        "period_from": cutoff.strftime("%Y-%m-%d"),
        "period_to": datetime.now(KST).strftime("%Y-%m-%d"),
        "stats": stats,
        "leads": uniq,
    }
    path = os.path.join(ROOT, "data", f"leads-{today}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    print(f"  → {path} ({len(uniq)}건)")
    return path


ROW = ('<tr><td class="d">{date}</td><td class="b">{board}</td>'
       '<td><a href="{url}" target="_blank" rel="noopener">{subject}</a></td>'
       '<td class="n">{comments}</td><td class="n">{reads}</td></tr>')

REPORT_TMPL = """<!DOCTYPE html>
<html lang="ko"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>발주레이더 주간 리포트 {date}</title>
<link rel="stylesheet" href="../assets/style.css">
</head><body class="report">
<header class="rp-head">
  <a class="brand" href="../index.html">발주레이더</a>
  <h1>주간 발주 리포트 <span class="date">{date}</span></h1>
  <p class="meta">수집 기간 {pfrom} ~ {pto} · 총 <strong>{total}건</strong> · 발행 {generated} (KST)</p>
</header>
<main>
<section class="notice">
  <p>이 리포트는 공개 커뮤니티 발주 게시글의 <strong>제목·게시판·작성일 메타데이터 큐레이션</strong>입니다.
  개인 연락처는 수집·게재하지 않으며, 원문·연락처 확인은 각 커뮤니티 가입 후 원문 링크에서 하시면 됩니다.
  <strong>댓글 수가 적을수록 선점 여지가 큰 리드</strong>입니다.</p>
</section>
{sections}
</main>
<footer class="rp-foot">
  <p>발주레이더 · Petaflo AI Lab · <a href="../index.html#subscribe">주간 이메일 구독 안내</a></p>
</footer>
</body></html>
"""

SECTION_TMPL = """<section class="cat">
<h2>{category} <span class="cnt">{count}건</span> <span class="src">{source}</span></h2>
<div class="tbl-wrap"><table>
<thead><tr><th>작성일</th><th>게시판</th><th>제목</th><th>댓글</th><th>조회</th></tr></thead>
<tbody>
{rows}
</tbody></table></div>
</section>
"""


def esc(s):
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def build(data_path):
    with open(data_path, encoding="utf-8") as f:
        d = json.load(f)
    date = d["period_to"]
    cats = {}
    for lead in d["leads"]:
        cats.setdefault(lead["category"], []).append(lead)
    sections = []
    order = [c["category"] for c in CAFES]
    for cat in order:
        leads = cats.get(cat, [])
        if not leads:
            continue
        rows = "\n".join(ROW.format(
            date=l["date"], board=esc(l["board"]), url=l["url"],
            subject=esc(l["subject"]), comments=l["comments"], reads=l["reads"],
        ) for l in leads)
        sections.append(SECTION_TMPL.format(
            category=esc(cat), count=len(leads), source=esc(leads[0]["source"]), rows=rows))
    html = REPORT_TMPL.format(
        date=date, pfrom=d["period_from"], pto=d["period_to"],
        total=len(d["leads"]), generated=d["generated"], sections="\n".join(sections))
    out = os.path.join(ROOT, "reports", f"{date}.html")
    with open(out, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"  → {out}")
    update_index()
    return out


def update_index():
    idx_path = os.path.join(ROOT, "index.html")
    if not os.path.exists(idx_path):
        return
    files = sorted(glob.glob(os.path.join(ROOT, "reports", "*.html")), reverse=True)
    items = []
    for f in files:
        name = os.path.splitext(os.path.basename(f))[0]
        items.append(f'      <li><a href="reports/{name}.html">주간 발주 리포트 {name}</a></li>')
    with open(idx_path, encoding="utf-8") as f:
        html = f.read()
    html = re.sub(
        r"(<!-- REPORT-LIST-START -->)(.*?)(<!-- REPORT-LIST-END -->)",
        lambda m: m.group(1) + "\n" + "\n".join(items) + "\n      " + m.group(3),
        html, flags=re.S)
    with open(idx_path, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"  → index.html 리포트 목록 갱신 ({len(items)}건)")


def latest_data():
    files = sorted(glob.glob(os.path.join(ROOT, "data", "leads-*.json")))
    if not files:
        sys.exit("data/ 에 수집 파일이 없습니다. 먼저 sweep을 실행하세요.")
    return files[-1]


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["sweep", "build", "all"])
    ap.add_argument("--days", type=int, default=10)
    ap.add_argument("--data", default=None)
    a = ap.parse_args()
    if a.cmd in ("sweep", "all"):
        path = sweep(a.days)
    else:
        path = a.data or latest_data()
    if a.cmd in ("build", "all"):
        build(path)
