# -*- coding: utf-8 -*-
"""
미소방문 FRT 대시보드 HTML 생성.

구성:
  1) 당일 시간별 평균 FRT 차트
  2) 시간대 클릭 → raw 세션 폴드

사용:
  python tools/build_frt_ops_dashboard.py
  python tools/build_frt_ops_dashboard.py --date 2026-07-27
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOCS_DIR = ROOT / "docs" / "frt"
RAW_DIR = DOCS_DIR / "daily" / "raw"
OUT_HTML = DOCS_DIR / "ops_dashboard.html"
KST = timezone(timedelta(hours=9))
SLA_MS = 180_000

# 한국 공휴일 (2026). 출처: 한국천문연구원 「2026년 월력요항」·관공서 공휴일 규정
KR_HOLIDAYS = {
    "2026-01-01",  # 신정
    "2026-02-16", "2026-02-17", "2026-02-18",  # 설날
    "2026-03-01",  # 삼일절 (일)
    "2026-03-02",  # 삼일절 대체공휴일
    "2026-05-01",  # 근로자의 날
    "2026-05-05",  # 어린이날
    "2026-05-24",  # 부처님오신날 (일)
    "2026-05-25",  # 부처님오신날 대체공휴일
    "2026-06-03",  # 제9회 전국동시지방선거 (임시공휴일)
    "2026-06-06",  # 현충일 (토, 대체 없음)
    "2026-07-17",  # 제헌절
    "2026-08-15",  # 광복절 (토)
    "2026-08-17",  # 광복절 대체공휴일
    "2026-09-24", "2026-09-25", "2026-09-26",  # 추석
    "2026-10-03",  # 개천절 (토)
    "2026-10-05",  # 개천절 대체공휴일
    "2026-10-09",  # 한글날
    "2026-12-25",  # 성탄절
}

sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))
from chat_followup_analyzer import build_followup_payload  # noqa: E402
from frt_lib import (  # noqa: E402
    detect_pause_windows,
    fetch_raw_messages,
    first_customer_at,
    format_pause_label,
    in_pause,
    is_auto_reply,
    split_streams,
    to_kst,
)


def is_ops_hour(dt: datetime) -> bool:
    """
    운영시간 (미소방문 FRT 미션 기준):
      ~ 7/19: 주중·주말 10:00 ≤ t < 19:00
      7/20~:  주중 09:00 ≤ t < 21:00 / 주말 10:00 ≤ t < 19:00
    """
    start, end = ops_window(dt.date())
    return start <= dt.hour < end


def ops_window(d: date) -> tuple[int, int]:
    """(start_hour inclusive, end_hour exclusive)."""
    cutoff = date(2026, 7, 20)
    if d < cutoff:
        return 10, 19
    if d.weekday() >= 5:  # 토·일
        return 10, 19
    return 9, 21


def ops_label(d: date) -> str:
    start, end = ops_window(d)
    kind = "주말" if d.weekday() >= 5 else "주중"
    if d < date(2026, 7, 20):
        return f"10:00~{end:02d}:00 (7/1~7/19 동일)"
    return f"{kind} {start:02d}:00~{end:02d}:00 (7/20~)"


def short_channel(url: str) -> str:
    # sendbird_..._Customer_xxx 형태면 끝부분만
    if "Customer_" in url:
        return url.split("Customer_")[-1][:24]
    return url[-28:]


def build_day_payload(target: date) -> dict:
    day_start = datetime(target.year, target.month, target.day, tzinfo=KST)
    fetch_start = day_start - timedelta(hours=2)
    fetch_end = day_start + timedelta(days=1, hours=6)
    messages = fetch_raw_messages(fetch_start, fetch_end)
    streams = split_streams(messages)
    pauses = detect_pause_windows(messages, target)

    hour_vals: dict[int, list[float]] = defaultdict(list)
    hour_raw: dict[int, list[dict]] = defaultdict(list)
    all_raw: list[dict] = []
    n_pause_excluded = 0

    for stream in streams:
        started = first_customer_at(stream)
        if started is None or started.date() != target:
            continue
        if in_pause(started, pauses):
            n_pause_excluded += 1
            continue
        customer = [m for m in stream if m["role"] == "customer"]
        partner = [m for m in stream if m["role"] == "partner"]
        first = customer[0]
        later = [
            m
            for m in partner
            if m["created_at_ms"] >= first["created_at_ms"]
            and not is_auto_reply(m.get("body"))
        ]
        if not later:
            continue
        frt_ms = later[0]["created_at_ms"] - first["created_at_ms"]
        if frt_ms < 0:
            continue
        frt_min = round(frt_ms / 60000, 1)
        h = started.hour
        hour_vals[h].append(float(frt_ms))
        reply_at = to_kst(later[0]["created_at_ms"])
        row = {
            "hour": h,
            "ops": is_ops_hour(started),
            "channel": short_channel(first["channel_url"]),
            "channel_url": first["channel_url"],
            "customer_id": first["user_id"],
            "customer_at": started.strftime("%H:%M:%S"),
            "partner_at": reply_at.strftime("%H:%M:%S"),
            "frt_min": frt_min,
            "sla_ok": frt_ms <= SLA_MS,
            "customer_msg": (first.get("body") or "")[:80],
            "partner_msg": (later[0].get("body") or "")[:80],
        }
        hour_raw[h].append(row)
        all_raw.append(row)

    hours = []
    ops_start, ops_end = ops_window(target)
    for h in range(24):
        vals = hour_vals.get(h, [])
        avg = round(sum(vals) / len(vals) / 60000, 1) if vals else None
        sla = round(sum(1 for x in vals if x <= SLA_MS) / len(vals) * 100, 1) if vals else None
        hours.append({
            "hour": h,
            "n": len(vals),
            "avg_min": avg,
            "sla_pct": sla,
            "ops": ops_start <= h < ops_end,
        })

    # CSV raw 파일
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    csv_name = f"FRT_RAW_{target.strftime('%Y%m%d')}.csv"
    csv_path = RAW_DIR / csv_name
    with csv_path.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(
            f,
            fieldnames=[
                "hour", "ops", "channel", "customer_id", "customer_at",
                "partner_at", "frt_min", "sla_ok", "customer_msg", "partner_msg",
                "channel_url",
            ],
        )
        w.writeheader()
        for r in sorted(all_raw, key=lambda x: (x["hour"], x["customer_at"])):
            w.writerow(r)

    # 운영시간 내 전용 Chat Raw CSV
    ops_raw = sorted(
        [r for r in all_raw if r.get("ops")],
        key=lambda x: (x["hour"], x["customer_at"]),
    )
    ops_csv_name = f"FRT_OPS_RAW_{target.strftime('%Y%m%d')}.csv"
    ops_csv_path = RAW_DIR / ops_csv_name
    with ops_csv_path.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(
            f,
            fieldnames=[
                "hour", "ops", "channel", "customer_id", "customer_at",
                "partner_at", "frt_min", "sla_ok", "customer_msg", "partner_msg",
                "channel_url",
            ],
        )
        w.writeheader()
        w.writerows(ops_raw)

    ops_frts = [r["frt_min"] for r in all_raw if r.get("ops")]
    ops_day_avg = round(sum(ops_frts) / len(ops_frts), 1) if ops_frts else None
    pause_payload = [
        {"start": s.strftime("%H:%M"), "end": e.strftime("%H:%M")}
        for s, e in pauses
    ]

    return {
        "generated_at": datetime.now(tz=KST).isoformat(),
        "title": "미소방문 FRT 대시보드",
        "date": target.isoformat(),
        "sla_min": 3,
        "ops_hours": ops_label(target),
        "ops_start": ops_start,
        "ops_end": ops_end,
        "ops_rule": "7/1~7/19: 10~19 · 7/20~: 주중 09~21 / 주말 10~19",
        "source": "raw_message",
        "raw_csv": f"daily/raw/{csv_name}",
        "ops_raw_csv": f"daily/raw/{ops_csv_name}",
        "ops_raw": ops_raw,
        "hours": hours,
        "raw_by_hour": {str(h): hour_raw.get(h, []) for h in range(24)},
        "n_eligible": len(all_raw),
        "ops_day_avg_min": ops_day_avg,
        "ops_day_n": len(ops_frts),
        "pause_windows": pause_payload,
        "pause_label": format_pause_label(pauses),
        "n_pause_excluded": n_pause_excluded,
        "holidays": sorted(KR_HOLIDAYS),
    }


def build_trend_payload(end_day: date, lookback_days: int = 60) -> list[dict]:
    """일자별 전체/운영시간내 평균 FRT + 운영시간내 D-7."""
    start_day = end_day - timedelta(days=lookback_days - 1)
    return _build_daily_rows(start_day, end_day, with_d7=True)


def build_month_payload(year: int, month: int, as_of: date) -> list[dict]:
    """해당 월 1일~as_of 일자별 전체/운영시간내 평균 FRT."""
    start_day = date(year, month, 1)
    if month == 12:
        month_end = date(year + 1, 1, 1) - timedelta(days=1)
    else:
        month_end = date(year, month + 1, 1) - timedelta(days=1)
    end_day = min(as_of, month_end)
    if end_day < start_day:
        return []
    return _build_daily_rows(start_day, end_day, with_d7=False)


def _build_daily_rows(start_day: date, end_day: date, with_d7: bool) -> list[dict]:
    fetch_start = datetime(start_day.year, start_day.month, start_day.day, tzinfo=KST) - timedelta(hours=2)
    fetch_end = datetime(end_day.year, end_day.month, end_day.day, tzinfo=KST) + timedelta(days=1, hours=6)
    messages = fetch_raw_messages(fetch_start, fetch_end)
    streams = split_streams(messages)
    pause_cache: dict[date, list[tuple[datetime, datetime]]] = {}

    def pauses_for(d: date) -> list[tuple[datetime, datetime]]:
        if d not in pause_cache:
            pause_cache[d] = detect_pause_windows(messages, d)
        return pause_cache[d]

    day_all: dict[str, list[float]] = defaultdict(list)
    day_ops: dict[str, list[float]] = defaultdict(list)
    for stream in streams:
        started = first_customer_at(stream)
        if started is None:
            continue
        if started.date() < start_day or started.date() > end_day:
            continue
        if in_pause(started, pauses_for(started.date())):
            continue
        customer = [m for m in stream if m["role"] == "customer"]
        partner = [m for m in stream if m["role"] == "partner"]
        first = customer[0]
        later = [
            m
            for m in partner
            if m["created_at_ms"] >= first["created_at_ms"]
            and not is_auto_reply(m.get("body"))
        ]
        if not later:
            continue
        frt_ms = later[0]["created_at_ms"] - first["created_at_ms"]
        if frt_ms < 0:
            continue
        key = started.date().isoformat()
        day_all[key].append(float(frt_ms))
        if is_ops_hour(started):
            day_ops[key].append(float(frt_ms))

    rows: list[dict] = []
    cur = start_day
    while cur <= end_day:
        key = cur.isoformat()
        all_v = day_all.get(key, [])
        ops_v = day_ops.get(key, [])
        avg = round(sum(all_v) / len(all_v) / 60000, 1) if all_v else None
        ops_avg = round(sum(ops_v) / len(ops_v) / 60000, 1) if ops_v else None
        row = {
            "date": key,
            "n": len(all_v),
            "ops_n": len(ops_v),
            "avg_min": avg,
            "ops_avg_min": ops_avg,
        }
        if with_d7:
            row["d7_min"] = None
            row["ops_d7_min"] = None
        rows.append(row)
        cur += timedelta(days=1)

    if with_d7:
        for i in range(len(rows)):
            chunk_all = [r["avg_min"] for r in rows[max(0, i - 6) : i + 1] if r["avg_min"] is not None]
            chunk_ops = [r["ops_avg_min"] for r in rows[max(0, i - 6) : i + 1] if r["ops_avg_min"] is not None]
            rows[i]["d7_min"] = round(sum(chunk_all) / len(chunk_all), 1) if chunk_all else None
            rows[i]["ops_d7_min"] = round(sum(chunk_ops) / len(chunk_ops), 1) if chunk_ops else None

    return rows


def weighted_ops_avg(rows: list[dict]) -> float | None:
    """세션 수 가중 운영시간 내 평균(분)."""
    num = 0.0
    den = 0
    for r in rows:
        if r.get("ops_avg_min") is None:
            continue
        n = int(r.get("ops_n") or 0)
        if n <= 0:
            continue
        num += float(r["ops_avg_min"]) * n
        den += n
    return round(num / den, 1) if den else None


def pick_target(arg_date: str | None) -> date:
    if arg_date:
        return date.fromisoformat(arg_date)
    today = datetime.now(tz=KST).date()
    # 당일 데이터가 거의 없으면(오전 등) 어제 폴백은 HTML에서 안내하되,
    # 기본은 당일. 조회 후 n=0이면 어제 재시도는 main에서.
    return today


def build_html(payload: dict) -> str:
    data_json = json.dumps(payload, ensure_ascii=False)
    return f"""<!DOCTYPE html>
<html lang="ko">
<head>
  <meta charset="UTF-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1"/>
  <title>미소방문 FRT 대시보드</title>
  <script src="https://cdn.jsdelivr.net/npm/chart.js@4"></script>
  <style>
    :root {{
      --bg: #f4f6f8; --card: #fff; --text: #1b1f24; --muted: #68707a;
      --border: #dde3ea; --accent: #2563eb; --sla: #d14343; --good: #0f9f6e;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0; font-family: "Segoe UI","Apple SD Gothic Neo",sans-serif;
      background: var(--bg); color: var(--text); font-size: 14px;
    }}
    header {{
      background: var(--card); border-bottom: 1px solid var(--border);
      padding: 18px 24px; display: flex; justify-content: space-between;
      align-items: baseline; flex-wrap: wrap; gap: 12px;
    }}
    h1 {{ margin: 0; font-size: 1.3rem; }}
    .sub {{ color: var(--muted); font-size: 12px; }}
    .mission {{
      background: var(--card);
      border-bottom: 1px solid var(--border);
      padding: 14px 24px 16px;
    }}
    .mission-inner {{
      max-width: 1200px;
      margin: 0 auto;
      display: grid;
      grid-template-columns: 1.4fr 1fr;
      gap: 16px 24px;
    }}
    .mission h3 {{
      margin: 0 0 8px;
      font-size: 0.85rem;
      color: var(--muted);
      font-weight: 600;
      letter-spacing: 0.02em;
    }}
    .mission .goal-line {{
      margin: 0 0 6px;
      font-size: 14px;
      line-height: 1.45;
    }}
    .mission .goal-line strong {{
      color: #d14343;
      font-weight: 700;
    }}
    .mission ul {{
      margin: 0;
      padding-left: 18px;
      font-size: 13px;
      line-height: 1.55;
      color: var(--text);
    }}
    .mission .note {{
      margin-top: 6px;
      font-size: 11px;
      color: var(--muted);
    }}
    @media (max-width: 900px) {{
      .mission-inner {{ grid-template-columns: 1fr; }}
    }}
    main {{ max-width: 1200px; margin: 0 auto; padding: 20px 24px 40px; }}
    .card {{
      background: var(--card); border: 1px solid var(--border);
      border-radius: 10px; padding: 16px 18px; margin-bottom: 16px;
    }}
    .card h2 {{ margin: 0 0 4px; font-size: 1rem; line-height: 1.4; }}
    .card h2 .card-tag {{
      display: block;
      color: var(--muted);
      font-size: 0.82em;
      font-weight: 600;
      letter-spacing: 0.02em;
      margin-bottom: 2px;
    }}
    .card h2 .n-val {{
      font-weight: 700;
      font-size: 1.15em;
      margin: 0 2px;
    }}
    .card h2 .n-val.hit {{ color: #d14343; }}
    .card h2 .n-val.miss {{ color: #2563eb; }}
    .card h2 .n-hint {{
      color: #9aa3ad;
      font-weight: 400;
      font-size: 0.78em;
    }}
    .card h2 .dow.off {{ color: #d14343; font-weight: 600; }}
    .caption {{ color: var(--muted); font-size: 12px; margin-bottom: 12px; }}
    canvas {{ max-height: 360px; }}
    .row2 {{
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 16px;
      margin-bottom: 16px;
    }}
    .row2.row-top {{
      grid-template-columns: 1.55fr 1fr;
    }}
    .row2 .card {{ margin-bottom: 0; }}
    @media (max-width: 900px) {{
      .row2, .row2.row-top {{ grid-template-columns: 1fr; }}
    }}
    .status-list {{
      list-style: none; margin: 0; padding: 0;
    }}
    .status-list li {{
      display: grid;
      grid-template-columns: 7.6em 3.2em 1fr auto;
      align-items: baseline;
      column-gap: 10px;
      padding: 10px 8px;
      border-bottom: 1px solid var(--border);
      font-size: 13px;
      line-height: 1.45;
      font-variant-numeric: tabular-nums;
    }}
    .status-list li:last-child {{ border-bottom: none; }}
    .status-list li.today {{
      background: #fff7ed;
      border-radius: 6px;
      font-weight: 600;
    }}
    .status-list .col-date {{ color: var(--text); }}
    .status-list .col-date .dow.off {{ color: #d14343; font-weight: 600; }}
    .status-list .col-n {{ text-align: right; }}
    .status-list .col-n.hit {{ color: #d14343; font-weight: 700; }}
    .status-list .col-n.miss {{ color: #2563eb; font-weight: 700; }}
    .status-list .col-label {{ color: var(--muted); font-size: 12px; }}
    .status-list .col-verdict {{ text-align: right; white-space: nowrap; }}
    .status-list .col-verdict.hit {{ color: #d14343; font-weight: 700; }}
    .status-list .col-verdict.miss {{ color: #2563eb; font-weight: 700; }}
    .status-list .rel {{ color: var(--muted); font-weight: 400; font-size: 12px; margin-left: 4px; }}
    .status-list .nodata {{ color: var(--muted); }}
    #chartHourly {{ max-height: 320px; }}
    details.raw-fold {{
      background: var(--card); border: 1px solid var(--border);
      border-radius: 10px; padding: 0; margin-bottom: 16px;
    }}
    details.raw-fold > summary {{
      list-style: none; cursor: pointer; padding: 14px 18px;
      font-weight: 600; user-select: none;
    }}
    details.raw-fold > summary::-webkit-details-marker {{ display: none; }}
    details.raw-fold > summary::before {{
      content: "▸ "; color: var(--accent);
    }}
    details.raw-fold[open] > summary::before {{ content: "▾ "; }}
    .fold-body {{ padding: 0 18px 16px; }}
    .table-wrap {{ overflow: auto; max-height: 420px; border: 1px solid var(--border); border-radius: 8px; }}
    table {{ width: 100%; border-collapse: collapse; font-size: 12px; min-width: 900px; }}
    th, td {{ padding: 8px 10px; border-bottom: 1px solid var(--border); text-align: left; }}
    th {{ background: #f8fafc; position: sticky; top: 0; }}
    tr:hover td {{ background: #f8fafc; }}
    .ok {{ color: var(--good); }}
    .bad {{ color: var(--sla); }}
    .hint {{ color: var(--muted); font-size: 12px; margin-top: 8px; }}
    a {{ color: var(--accent); }}
    .followup-card {{
      border-left: 4px solid var(--sla);
    }}
    .followup-card.empty {{
      border-left-color: var(--good);
    }}
    .followup-meta {{
      display: flex; flex-wrap: wrap; gap: 12px 20px;
      font-size: 12px; color: var(--muted); margin-bottom: 12px;
    }}
    .followup-list {{
      list-style: none; margin: 0; padding: 0;
    }}
    .followup-list li {{
      display: grid;
      grid-template-columns: 6.5em 5em 1fr auto;
      gap: 8px 12px;
      align-items: start;
      padding: 12px 10px;
      border-bottom: 1px solid var(--border);
      font-size: 13px;
      line-height: 1.45;
    }}
    .followup-list li:last-child {{ border-bottom: none; }}
    .followup-list .req {{
      font-weight: 700;
      font-variant-numeric: tabular-nums;
    }}
    .followup-list .cust {{ color: var(--muted); white-space: nowrap; }}
    .followup-list .reason {{ color: var(--text); }}
    .followup-list .badge {{
      font-size: 11px; font-weight: 600;
      padding: 2px 8px; border-radius: 4px;
      white-space: nowrap;
    }}
    .followup-list .badge.reply {{ background: #fee2e2; color: #b91c1c; }}
    .followup-list .badge.detail {{ background: #fef3c7; color: #b45309; }}
    .followup-empty {{
      color: var(--muted); font-size: 13px; padding: 8px 0;
    }}
    @media (max-width: 700px) {{
      .followup-list li {{
        grid-template-columns: 1fr 1fr;
      }}
      .followup-list .reason {{ grid-column: 1 / -1; }}
    }}
  </style>
</head>
<body>
<header>
  <div>
    <h1>미소방문 FRT 대시보드</h1>
    <div class="sub" id="subtitle"></div>
  </div>
  <div class="sub" id="genAt"></div>
</header>
<section class="mission" aria-label="목적과 목표">
  <div class="mission-inner">
    <div>
      <h3>목적 · 목표</h3>
      <p class="goal-line"><b>목적</b> — 문의에 대해 빠른 응대를 통해 고객경험을 개선한다.</p>
      <p class="goal-line"><b>목표</b> — 미소방문 운영시간 내 FRT 평균 <strong>3분 이내</strong></p>
      <p class="goal-line"><b>제외</b> — 운영시간 내 <strong>점심 자동응답</strong> 구간은 FRT에서 제외한다. <span id="pauseRuleNote" class="note" style="display:inline;margin:0"></span></p>
      <p class="note">타이틀 숫자(N)는 운영시간 내 평균 FRT입니다. ≤3분=빨강, &gt;3분=파랑.</p>
    </div>
    <div>
      <h3>미소방문 운영시간</h3>
      <ul>
        <li><b>주중</b> — 09:00 ~ 21:00</li>
        <li><b>주말 · 공휴일</b> — 10:00 ~ 19:00</li>
      </ul>
      <p class="note">참고: 7/1~7/19는 주중·주말 모두 10:00~19:00으로 집계. 7/20부터 위 운영시간을 적용.</p>
    </div>
  </div>
</section>
<main>
  <div class="row2 row-top">
    <div class="card">
      <h2 id="chartTitle">당일 시간별 평균 FRT</h2>
      <div class="caption" id="hourlyCaption">막대 클릭 → raw 폴드 · 파랑=운영시간 · 연보라=운영외 · 빨간 점선=3분 SLA · 연한 배경=운영시간 구간</div>
      <canvas id="chartHourly"></canvas>
      <div class="hint" id="clickHint">시간대를 클릭하면 raw가 펼쳐집니다.</div>
    </div>
    <div class="card">
      <h2 id="statusTitle">일일 운영시간내 FRT 달성 여부</h2>
      <div class="caption">목표 3분 · 성공=≤3 · 간극=실측−3 · 최신일 위 · 주말·공휴일은 요일만 빨강</div>
      <ul id="status7d" class="status-list"></ul>
    </div>
  </div>

  <div class="row2">
    <div class="card">
      <h2 id="trendTitle">7D 기준 · 일자별 평균 FRT</h2>
      <div class="caption">최근 7일 · 회색=당일 전체 평균 · 초록=운영시간 내 평균 · 파랑=운영시간 내 7D · 빨간 점선=3분 SLA</div>
      <canvas id="chartD7"></canvas>
    </div>
    <div class="card">
      <h2 id="monthTitle">7월 일자별 평균 FRT</h2>
      <div class="caption">월 1일~당일 · 옅은 회색=일자별 전체 평균 · 빨강/파랑=운영시간 내(≤3/&gt;3) · 빨간 점선=3분 SLA · 운영규칙: 7/1~19=10~19, 7/20~=주중09~21/주말10~19</div>
      <canvas id="chartMonth"></canvas>
    </div>
  </div>

  <details class="raw-fold" id="opsRawFold">
    <summary id="opsRawSummary">당일 운영시간 내 Chat Raw (접힘)</summary>
    <div class="fold-body">
      <div class="caption" id="opsRawCaption"></div>
      <p><a id="opsRawCsvLink" href="#" download>운영시간 내 CSV 다운로드</a></p>
      <div class="table-wrap">
        <table>
          <thead>
            <tr>
              <th>시</th><th>고객시각</th><th>응답시각</th><th>FRT(분)</th>
              <th>3분</th><th>고객ID</th><th>채널</th>
              <th>고객메시지</th><th>파트너응답</th>
            </tr>
          </thead>
          <tbody id="opsRawTable"></tbody>
        </table>
      </div>
    </div>
  </details>

  <details class="raw-fold" id="rawFold">
    <summary id="rawSummary">전체 시간대 Raw 세션 보기 (접힘)</summary>
    <div class="fold-body">
      <div class="caption" id="rawCaption"></div>
      <p><a id="rawCsvLink" href="#" download>CSV 다운로드</a></p>
      <div class="table-wrap">
        <table>
          <thead>
            <tr>
              <th>시</th><th>구분</th><th>고객시각</th><th>응답시각</th>
              <th>FRT(분)</th><th>3분</th><th>고객ID</th><th>채널</th>
              <th>고객메시지</th><th>파트너응답</th>
            </tr>
          </thead>
          <tbody id="rawTable"></tbody>
        </table>
      </div>
    </div>
  </details>

  <div class="card followup-card" id="followupCard">
    <h2 id="followupTitle">추가 답변 필요</h2>
    <div class="caption" id="followupCaption">당일 고객 문의 중 상세 답변·설명이 더 필요한 주문 (주문번호·마스킹 고객명·사유만 표시)</div>
    <div class="followup-meta" id="followupMeta"></div>
    <ul class="followup-list" id="followupList"></ul>
    <div class="followup-empty" id="followupEmpty" style="display:none">추가 조치가 필요한 건이 없습니다.</div>
  </div>
</main>
<script>
const D = {data_json};
const DOW = ['Sun','Mon','Tue','Wed','Thu','Fri','Sat'];
const holidaySet = new Set(D.holidays || []);
function formatDateLabel(isoDate) {{
  const d = new Date(isoDate + 'T12:00:00');
  const yy = String(d.getFullYear()).slice(2);
  const mm = String(d.getMonth() + 1).padStart(2, '0');
  const dd = String(d.getDate()).padStart(2, '0');
  const dow = d.getDay();
  const isOff = dow === 0 || dow === 6 || holidaySet.has(isoDate);
  return yy + '-' + mm + '-' + dd
    + '(<span class="dow' + (isOff ? ' off' : '') + '">' + DOW[dow] + '</span>)';
}}
const labels = D.hours.map(h => h.hour + '시');
// daily FRT 운영 지표: 운영시간 외 막대는 숨김 (집계·전체 raw는 유지)
const avgs = D.hours.map(h => (h.ops ? h.avg_min : null));
let selectedHour = null;

document.getElementById('subtitle').textContent =
  D.date + ' · 운영 ' + D.ops_hours + ' · SLA ' + D.sla_min + '분 · eligible ' + D.n_eligible
  + (D.pause_label ? (' · ' + D.pause_label + ' 제외 ' + (D.n_pause_excluded || 0) + '건') : '')
  + ' · 규칙: ' + (D.ops_rule || '');
document.getElementById('genAt').textContent = D.generated_at + ' · 30분마다 데이터 갱신';
(function () {{
  const el = document.getElementById('pauseRuleNote');
  if (!el) return;
  if (D.pause_label) {{
    el.textContent = '(오늘 감지: ' + D.pause_label.replace('점심 Pause ', '') + ')';
  }} else {{
    el.textContent = '(당일 점심 자동응답이 있으면 해당 시각을 자동 적용)';
  }}
}})();
(function renderStatus7d() {{
  const root = document.getElementById('status7d');
  if (!root) return;
  const target = D.sla_min || 3;
  const rows = (D.daily_trend || []).slice().reverse().slice(0, 7);
  root.innerHTML = rows.map((r, idx) => {{
    const dateHtml = formatDateLabel(r.date);
    let rel = '';
    if (idx === 0) rel = '<span class="rel">(today)</span>';
    else if (idx === 1) rel = '<span class="rel">(어제)</span>';
    const n = r.ops_avg_min;
    if (n === null || n === undefined) {{
      return '<li class="' + (idx === 0 ? 'today' : '') + '">'
        + '<span class="col-date">' + dateHtml + '</span>'
        + '<span class="col-n nodata">—</span>'
        + '<span class="col-label">운영시간내 FRT</span>'
        + '<span class="col-verdict nodata">—' + rel + '</span></li>';
    }}
    const hit = n <= target;
    const gap = Math.round((n - target) * 10) / 10;
    const gapStr = (gap > 0 ? '+' : '') + gap;
    const tone = hit ? 'hit' : 'miss';
    const verdict = (hit ? '성공' : '실패') + '(' + gapStr + ')';
    return '<li class="' + (idx === 0 ? 'today' : '') + '">'
      + '<span class="col-date">' + dateHtml + '</span>'
      + '<span class="col-n ' + tone + '">' + n + '</span>'
      + '<span class="col-label">운영시간내 FRT</span>'
      + '<span class="col-verdict ' + tone + '">' + verdict + rel + '</span></li>';
  }}).join('') || '<li class="nodata">최근 7일 데이터 없음</li>';
}})();
function titleWithN(tag, prefix, n, hint) {{
  const val = (n !== null && n !== undefined) ? n : '-';
  let cls = 'n-val';
  if (typeof n === 'number') {{
    cls += (n <= 3) ? ' hit' : ' miss';
  }}
  const tagHtml = tag ? '<span class="card-tag">[' + tag + ']</span>' : '';
  const hintHtml = hint ? ' <span class="n-hint">(' + hint + ')</span>' : '';
  return tagHtml + prefix + ' <span class="' + cls + '">' + val + '</span>' + hintHtml;
}}
document.getElementById('chartTitle').innerHTML =
  titleWithN('daily FRT 운영 지표', formatDateLabel(D.date) + ' 시간별차트 *FRT 평균', D.ops_day_avg_min, '운영시간 내 평균 FRT');
document.getElementById('statusTitle').innerHTML =
  '<span class="card-tag">[일일 운영시간내 FRT 달성]</span>일일 운영시간내 FRT 달성 여부';
document.getElementById('hourlyCaption').textContent =
  '운영시간만 막대 표시 · 막대 클릭 → raw · 빨강=3분 이내 · 파랑=3분 초과 · 연녹=운영시간 · 연주황=점심 Pause'
  + (D.pause_label ? ('(' + D.pause_label.replace('점심 Pause ','') + ')') : '')
  + ' · 빨간 점선=3분 SLA';
document.getElementById('rawCsvLink').href = D.raw_csv;
document.getElementById('opsRawCsvLink').href = D.ops_raw_csv;

function escapeHtml(value) {{
  return String(value ?? '')
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#039;');
}}

function rawRowHtml(r, showOps) {{
  const sla = r.sla_ok ? '<span class="ok">OK</span>' : '<span class="bad">OVER</span>';
  const opsCell = showOps ? '<td>' + (r.ops ? '운영' : '운영외') + '</td>' : '';
  return '<tr>'
    + '<td>' + escapeHtml(r.hour) + '</td>'
    + opsCell
    + '<td>' + escapeHtml(r.customer_at) + '</td>'
    + '<td>' + escapeHtml(r.partner_at) + '</td>'
    + '<td>' + escapeHtml(r.frt_min) + '</td>'
    + '<td>' + sla + '</td>'
    + '<td>' + escapeHtml(r.customer_id) + '</td>'
    + '<td>' + escapeHtml(r.channel) + '</td>'
    + '<td>' + escapeHtml(r.customer_msg) + '</td>'
    + '<td>' + escapeHtml(r.partner_msg) + '</td>'
    + '</tr>';
}}

function renderOpsRaw() {{
  const rows = (D.ops_raw || []).slice()
    .sort((a,b) => a.customer_at.localeCompare(b.customer_at));
  document.getElementById('opsRawSummary').textContent =
    '당일 운영시간 내 Chat Raw · ' + rows.length + '건';
  document.getElementById('opsRawCaption').textContent =
    D.date + ' · ' + D.ops_hours + ' · 점심 Pause 제외 · 고객 첫 문의 기준';
  document.getElementById('opsRawTable').innerHTML =
    rows.map(r => rawRowHtml(r, false)).join('')
    || '<tr><td colspan="9">당일 운영시간 내 응답 완료 세션 없음</td></tr>';
}}

function renderRaw(hour) {{
  const fold = document.getElementById('rawFold');
  const rows = hour === null
    ? Object.values(D.raw_by_hour).flat()
    : (D.raw_by_hour[String(hour)] || []);
  rows.sort((a,b) => a.customer_at.localeCompare(b.customer_at));
  document.getElementById('rawSummary').textContent =
    hour === null
      ? 'Raw 세션 보기 · 전체 ' + rows.length + '건'
      : 'Raw 세션 보기 · ' + hour + '시 ' + rows.length + '건';
  document.getElementById('rawCaption').textContent =
    hour === null
      ? '전체 시간대 raw (차트 막대를 클릭하면 해당 시만 필터)'
      : hour + '시 세션 raw · CSV: ' + D.raw_csv;
  document.getElementById('rawTable').innerHTML =
    rows.map(r => rawRowHtml(r, true)).join('')
    || '<tr><td colspan="10">해당 시간대 세션 없음</td></tr>';
  fold.open = true;
  document.getElementById('clickHint').textContent =
    hour === null ? '전체 raw 표시 중' : (hour + '시 raw 표시 중 · 다시 같은 막대 클릭 시 전체로');
}}

function barColor(v) {{
  if (v === null || v === undefined) return 'rgba(0,0,0,0)';
  return v <= 3 ? 'rgba(209,67,67,0.85)' : 'rgba(37,99,235,0.70)';
}}

const ctx = document.getElementById('chartHourly');
const opsBandPlugin = {{
  id: 'opsBand',
  beforeDraw(chart) {{
    const {{ctx, chartArea, scales}} = chart;
    if (!chartArea || !scales.x) return;
    const x = scales.x;
    const unit = x.getPixelForValue(1) - x.getPixelForValue(0);
    const pad = unit / 2;
    const timeToX = (hhmm) => {{
      const parts = String(hhmm).split(':');
      const h = parseInt(parts[0], 10);
      const m = parts.length > 1 ? parseInt(parts[1], 10) : 0;
      return x.getPixelForValue(h) - pad + (m / 60) * unit;
    }};
    const start = D.ops_start;
    const end = D.ops_end;
    const left = x.getPixelForValue(start) - pad;
    const right = x.getPixelForValue(end - 1) + pad;
    ctx.save();
    ctx.fillStyle = 'rgba(15, 159, 110, 0.10)';
    ctx.fillRect(left, chartArea.top, right - left, chartArea.bottom - chartArea.top);
    ctx.strokeStyle = 'rgba(15, 159, 110, 0.55)';
    ctx.lineWidth = 1.5;
    ctx.setLineDash([4, 3]);
    ctx.beginPath();
    ctx.moveTo(left, chartArea.top);
    ctx.lineTo(left, chartArea.bottom);
    ctx.moveTo(right, chartArea.top);
    ctx.lineTo(right, chartArea.bottom);
    ctx.stroke();
    ctx.restore();
    ctx.save();
    ctx.fillStyle = 'rgba(15, 159, 110, 0.85)';
    ctx.font = '11px Segoe UI, sans-serif';
    ctx.fillText('운영시간 ' + start + ':00~' + end + ':00', left + 6, chartArea.top + 14);
    ctx.restore();
    const pauses = D.pause_windows || [];
    pauses.forEach((pw, idx) => {{
      const pl = timeToX(pw.start);
      const pr = timeToX(pw.end);
      ctx.save();
      ctx.fillStyle = 'rgba(217, 119, 6, 0.16)';
      ctx.fillRect(pl, chartArea.top, Math.max(pr - pl, 2), chartArea.bottom - chartArea.top);
      ctx.strokeStyle = 'rgba(217, 119, 6, 0.7)';
      ctx.lineWidth = 1.5;
      ctx.setLineDash([3, 3]);
      ctx.beginPath();
      ctx.moveTo(pl, chartArea.top);
      ctx.lineTo(pl, chartArea.bottom);
      ctx.moveTo(pr, chartArea.top);
      ctx.lineTo(pr, chartArea.bottom);
      ctx.stroke();
      ctx.fillStyle = 'rgba(180, 83, 9, 0.95)';
      ctx.font = '11px Segoe UI, sans-serif';
      ctx.fillText('Pause ' + pw.start + '~' + pw.end, pl + 4, chartArea.top + 28 + idx * 14);
      ctx.restore();
    }});
  }}
}};
const chart = new Chart(ctx, {{
  type: 'bar',
  data: {{
    labels,
    datasets: [
      {{
        label: '평균 FRT (분)',
        data: avgs,
        backgroundColor: avgs.map(barColor),
      }},
      {{
        label: '3분 SLA',
        data: Array(24).fill(3),
        type: 'line',
        borderColor: '#d14343',
        borderDash: [6,3],
        pointRadius: 0,
        borderWidth: 1.5,
      }},
    ],
  }},
  options: {{
    responsive: true,
    interaction: {{ mode: 'index', intersect: false }},
    onClick: (evt, elements) => {{
      if (!elements.length) {{
        selectedHour = null;
        renderRaw(null);
        return;
      }}
      const idx = elements[0].index;
      if (!D.hours[idx].ops) {{
        selectedHour = null;
        renderRaw(null);
        return;
      }}
      const h = D.hours[idx].hour;
      if (selectedHour === h) {{
        selectedHour = null;
        renderRaw(null);
      }} else {{
        selectedHour = h;
        renderRaw(h);
      }}
    }},
    scales: {{
      y: {{
        title: {{ display: true, text: '평균 FRT (분)' }},
        beginAtZero: true,
      }},
      x: {{ title: {{ display: true, text: '시작 시각 (KST)' }} }},
    }},
    plugins: {{
      legend: {{ position: 'bottom' }},
      tooltip: {{
        filter: (item) => item.datasetIndex === 1 || (item.raw !== null && item.raw !== undefined),
        callbacks: {{
          afterBody: (items) => {{
            const i = items[0].dataIndex;
            const h = D.hours[i];
            if (!h.ops) return '운영시간 외 · 시간별차트 비표시';
            const hit = (h.avg_min !== null && h.avg_min <= 3) ? '3분 이내' : '3분 초과';
            return '운영시간 · ' + hit + ' · 세션 ' + h.n + '건 · SLA ' + (h.sla_pct ?? '-') + '%';
          }}
        }}
      }}
    }},
  }},
  plugins: [opsBandPlugin],
}});

// 7D 일자별 평균 FRT
const trend = D.daily_trend || [];
const tLabels = trend.map(r => r.date.slice(5));
const n7d = (D.ops_7d_avg_min !== null && D.ops_7d_avg_min !== undefined) ? D.ops_7d_avg_min : '-';
document.getElementById('trendTitle').innerHTML =
  titleWithN('7D FRT 평균 지표', '7D 일자별 FRT 평균', D.ops_7d_avg_min, '7D 운영시간 평균');
new Chart(document.getElementById('chartD7'), {{
  type: 'line',
  data: {{
    labels: tLabels,
    datasets: [
      {{
        label: '당일 평균 FRT (분)',
        data: trend.map(r => r.avg_min),
        borderColor: 'rgba(100,116,139,0.55)',
        backgroundColor: 'rgba(100,116,139,0.08)',
        tension: 0.25,
        pointRadius: 2,
        borderWidth: 1.5,
      }},
      {{
        label: '운영시간 내 평균 FRT (분)',
        data: trend.map(r => r.ops_avg_min),
        borderColor: '#0f9f6e',
        backgroundColor: 'rgba(15,159,110,0.08)',
        tension: 0.25,
        pointRadius: 3,
        borderWidth: 2,
      }},
      {{
        label: '운영시간 내 7D (분)',
        data: trend.map(r => r.ops_d7_min),
        borderColor: '#2563eb',
        backgroundColor: 'rgba(37,99,235,0.08)',
        tension: 0.3,
        pointRadius: 2,
        borderWidth: 2.5,
      }},
      {{
        label: '3분 SLA',
        data: Array(trend.length).fill(3),
        borderColor: '#d14343',
        borderDash: [6,3],
        pointRadius: 0,
        borderWidth: 1.5,
      }},
    ],
  }},
  options: {{
    responsive: true,
    interaction: {{ mode: 'index', intersect: false }},
    scales: {{
      y: {{
        title: {{ display: true, text: '평균 FRT (분)' }},
        beginAtZero: true,
      }},
      x: {{ title: {{ display: true, text: '일자 (KST)' }} }},
    }},
    plugins: {{
      legend: {{ position: 'bottom' }},
      tooltip: {{
        callbacks: {{
          afterBody: (items) => {{
            const i = items[0].dataIndex;
            const r = trend[i];
            return '전체 ' + r.n + '건 · 운영시간내 ' + r.ops_n + '건';
          }}
        }}
      }}
    }},
  }}
}});

// 월 차트: 일자별 전체 + 운영시간 내 평균 FRT
const month = D.month_trend || [];
const nMonth = (D.ops_month_avg_min !== null && D.ops_month_avg_min !== undefined) ? D.ops_month_avg_min : '-';
document.getElementById('monthTitle').innerHTML =
  titleWithN('Monthly FRT 평균 지표', '월 일자별 평균 FRT', D.ops_month_avg_min, '운영시간 기준 월평균 FRT');
new Chart(document.getElementById('chartMonth'), {{
  type: 'bar',
  data: {{
    labels: month.map(r => r.date.slice(8) + '일'),
    datasets: [
      {{
        label: '일자별 평균 FRT (분)',
        data: month.map(r => r.avg_min),
        backgroundColor: 'rgba(100,116,139,0.28)',
        order: 2,
      }},
      {{
        label: '운영시간 내 평균 FRT (분)',
        data: month.map(r => r.ops_avg_min),
        backgroundColor: month.map(r => barColor(r.ops_avg_min)),
        order: 2,
      }},
      {{
        label: '3분 SLA',
        data: Array(month.length).fill(3),
        type: 'line',
        borderColor: '#d14343',
        borderDash: [6,3],
        pointRadius: 0,
        borderWidth: 1.5,
        order: 1,
      }},
    ],
  }},
  options: {{
    responsive: true,
    interaction: {{ mode: 'index', intersect: false }},
    scales: {{
      y: {{
        title: {{ display: true, text: '평균 FRT (분)' }},
        beginAtZero: true,
      }},
      x: {{ title: {{ display: true, text: '일자' }} }},
    }},
    plugins: {{
      legend: {{ position: 'bottom' }},
      tooltip: {{
        callbacks: {{
          afterBody: (items) => {{
            const i = items[0].dataIndex;
            const r = month[i];
            const hit = (r.ops_avg_min !== null && r.ops_avg_min <= 3) ? '운영내 3분 이내' : '운영내 3분 초과';
            return hit + ' · 전체 ' + r.n + '건 · 운영시간내 ' + r.ops_n + '건';
          }}
        }}
      }}
    }},
  }}
}});

// 운영시간 내 Chat Raw는 별도 접이식 영역으로 제공
document.getElementById('opsRawFold').addEventListener('toggle', (e) => {{
  if (e.target.open && !document.getElementById('opsRawTable').innerHTML) {{
    renderOpsRaw();
  }}
}});
document.getElementById('opsRawSummary').addEventListener('click', () => {{
  setTimeout(() => {{
    if (document.getElementById('opsRawFold').open) renderOpsRaw();
  }}, 0);
}});

// 처음엔 폴드 닫힘. summary 클릭만으로도 전체 raw 볼 수 있게 기본 데이터 준비
document.getElementById('rawFold').addEventListener('toggle', (e) => {{
  if (e.target.open && !document.getElementById('rawTable').innerHTML) {{
    renderRaw(selectedHour);
  }}
}});
document.getElementById('rawSummary').addEventListener('click', () => {{
  // details가 열릴 때 내용 채움
  setTimeout(() => {{
    if (document.getElementById('rawFold').open) renderRaw(selectedHour);
  }}, 0);
}});

(function renderFollowup() {{
  const F = D.followup || {{}};
  const items = F.items || [];
  const card = document.getElementById('followupCard');
  const title = document.getElementById('followupTitle');
  const cap = document.getElementById('followupCaption');
  const meta = document.getElementById('followupMeta');
  const list = document.getElementById('followupList');
  const empty = document.getElementById('followupEmpty');
  const n = items.length;
  title.textContent = '추가 답변 필요 (' + n + '건)';
  if (n === 0) card.classList.add('empty');
  meta.innerHTML = ''
    + '<span>분석 ' + (F.analyzed_at || '—') + '</span>'
    + '<span>후보 ' + (F.n_rule_candidates ?? '—') + '건</span>'
    + '<span>판별 ' + (F.judge_mode || '—') + '</span>';
  list.innerHTML = '';
  if (n === 0) {{
    empty.style.display = 'block';
    return;
  }}
  empty.style.display = 'none';
  items.forEach(it => {{
    const li = document.createElement('li');
    const badgeCls = it.status === 'needs_detail' ? 'detail' : 'reply';
    li.innerHTML = ''
      + '<span class="req">' + (it.request_id || '—') + '</span>'
      + '<span class="cust">' + (it.customer || '—') + '</span>'
      + '<span class="reason">' + (it.reason || '') + '</span>'
      + '<span class="badge ' + badgeCls + '">' + (it.status_label || it.status) + '</span>';
    list.appendChild(li);
  }});
}})();

const REFRESH_MS = 30 * 60 * 1000;
setTimeout(() => location.reload(), REFRESH_MS);
</script>
</body>
</html>"""


def main() -> int:
    if sys.platform == "win32":
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except (AttributeError, OSError):
            pass

    ap = argparse.ArgumentParser()
    ap.add_argument("--date", help="KST YYYY-MM-DD (default: today, else yesterday if empty)")
    args = ap.parse_args()

    target = pick_target(args.date)
    print(f"building for {target.isoformat()} ...")
    payload = build_day_payload(target)

    # 당일 0건(아침 운영 전 등)이어도 화면 날짜는 오늘을 유지한다.
    # 어제 폴백을 쓰면 자정 이후에도 전일 화면이 남아 일일 갱신 체감이 깨진다.
    if payload["n_eligible"] == 0 and not args.date:
        print(f"  no eligible yet on {target} (keep today view)")

    as_of = date.fromisoformat(payload["date"])
    print("building 7D daily trend (last 7 days) ...")
    payload["daily_trend"] = build_trend_payload(as_of, lookback_days=7)
    payload["ops_7d_avg_min"] = weighted_ops_avg(payload["daily_trend"])

    print(f"building month chart {as_of.year}-{as_of.month:02d} ...")
    payload["month_label"] = f"{as_of.month}월"
    payload["month_trend"] = build_month_payload(as_of.year, as_of.month, as_of)
    payload["ops_month_avg_min"] = weighted_ops_avg(payload["month_trend"])

    print("building followup (detail reply needed) ...")
    try:
        payload["followup"] = build_followup_payload(as_of, use_ai=True)
        print(
            f"  followup: {payload['followup'].get('n_needs_action', 0)} action items "
            f"(mode={payload['followup'].get('judge_mode', '?')})"
        )
    except Exception as exc:
        print(f"  followup failed (dashboard continues): {exc}")
        payload["followup"] = {
            "analyzed_at": datetime.now(tz=KST).isoformat(),
            "date": as_of.isoformat(),
            "n_threads": 0,
            "n_rule_candidates": 0,
            "n_needs_action": 0,
            "judge_mode": f"error:{type(exc).__name__}",
            "items": [],
        }

    DOCS_DIR.mkdir(parents=True, exist_ok=True)
    OUT_HTML.write_text(build_html(payload), encoding="utf-8")
    print(f"dashboard -> {OUT_HTML}")
    print(
        f"  date={payload['date']} ops_day={payload.get('ops_day_avg_min')} "
        f"ops_7d={payload.get('ops_7d_avg_min')} ops_month={payload.get('ops_month_avg_min')}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
