# -*- coding: utf-8 -*-
"""FRT 공유 라이브러리 (FRT_DEFINITION.md 잠금 로직)."""
from __future__ import annotations

import os
import re
import statistics
import subprocess
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MYSQL_EXE = Path(r"C:\Program Files\MySQL\MySQL Server 8.4\bin\mysql.exe")
KST = timezone(timedelta(hours=9))
PARTNER_ID = "Supplier_341573"
SLA_MS = 180_000
GAP_MS = 60 * 60 * 1000

# 점심 등 Pause: "13시 20분 - 14시 20분"
PAUSE_TIME_RE = re.compile(
    r"(\d{1,2})\s*시\s*(\d{1,2})\s*분\s*[-–~]\s*(\d{1,2})\s*시\s*(\d{1,2})\s*분"
)

import sys

sys.path.insert(0, str(ROOT))
from db_config import get_mysql_config  # noqa: E402


def mysql_query(sql: str, database: str = "chat_poc") -> str:
    cfg = get_mysql_config()
    env = os.environ.copy()
    env["MYSQL_PWD"] = cfg["password"]
    cmd = [
        str(MYSQL_EXE),
        "-h",
        cfg["host"],
        "-P",
        str(cfg["port"]),
        "-u",
        cfg["user"],
        database,
        "--default-character-set=utf8mb4",
        "-N",
        "-B",
        "-e",
        sql,
    ]
    proc = subprocess.run(
        cmd,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if proc.returncode != 0:
        err = (proc.stderr or proc.stdout or "").replace(cfg["password"], "***")
        raise RuntimeError(err[:2000])
    return proc.stdout


def to_kst(ts_ms: int) -> datetime:
    return datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc).astimezone(KST)


def is_ops_in(dt: datetime) -> bool:
    """FRT_DEFINITION.md §3: 10:00 ≤ hour < 19:00 (일일 리포트 기본)."""
    return 10 <= dt.hour < 19


def is_auto_reply(body: str | None) -> bool:
    """미소 AI 자동응답 — 파트너 첫응답으로 미인정 (v1.2)."""
    b = body or ""
    return "미소 AI" in b or "[미소 AI]" in b


def detect_pause_windows(
    messages: list[dict], day: date
) -> list[tuple[datetime, datetime]]:
    """
    점심 자동응답 본문에서 당일 Pause 구간 [start, end) 추출.
    운영시간 외 안내는 무시.
    """
    windows: list[tuple[datetime, datetime]] = []
    seen: set[tuple[int, int]] = set()
    for msg in messages:
        body = msg.get("body") or ""
        if "미소 AI" not in body and "[미소 AI]" not in body:
            continue
        if "점심" not in body:
            continue
        # 운영외 안내가 점심과 섞인 이상 케이스는 제외
        if "운영시간" in body and "외" in body and "점심" not in body:
            continue
        m = PAUSE_TIME_RE.search(body)
        if not m:
            continue
        h1, m1, h2, m2 = (int(m.group(i)) for i in range(1, 5))
        key = (h1 * 60 + m1, h2 * 60 + m2)
        if key in seen:
            continue
        seen.add(key)
        start = datetime(day.year, day.month, day.day, h1, m1, tzinfo=KST)
        end = datetime(day.year, day.month, day.day, h2, m2, tzinfo=KST)
        if end <= start:
            continue
        windows.append((start, end))
    windows.sort(key=lambda w: w[0])
    return windows


def in_pause(dt: datetime, windows: list[tuple[datetime, datetime]]) -> bool:
    return any(start <= dt < end for start, end in windows)


def format_pause_label(windows: list[tuple[datetime, datetime]]) -> str:
    if not windows:
        return ""
    parts = [
        f"{s.strftime('%H:%M')}~{e.strftime('%H:%M')}" for s, e in windows
    ]
    return "점심 Pause " + ", ".join(parts)


def fetch_raw_messages(start_kst: datetime, end_kst: datetime) -> list[dict]:
    start_ms = int(start_kst.timestamp() * 1000)
    end_ms = int(end_kst.timestamp() * 1000)
    # TAB 구분자 깨짐 방지: body는 짧게, 줄바꿈 제거
    raw = mysql_query(
        f"""
SELECT channel_url, message_id, user_id, created_at_ms,
       REPLACE(REPLACE(LEFT(IFNULL(message_body,''), 200), '\\n', ' '), '\\t', ' ')
FROM raw_message
WHERE partner_id = '{PARTNER_ID}'
  AND created_at_ms >= {start_ms}
  AND created_at_ms < {end_ms}
  AND message_type IN ('MESG','FILE')
ORDER BY channel_url, created_at_ms, message_id
"""
    )
    rows: list[dict] = []
    for line in raw.splitlines():
        if not line.strip():
            continue
        parts = line.split("\t")
        if len(parts) < 4:
            continue
        body = parts[4] if len(parts) > 4 else ""
        rows.append(
            {
                "channel_url": parts[0],
                "message_id": parts[1],
                "user_id": parts[2],
                "role": "partner" if parts[2].startswith("Supplier_") else "customer",
                "created_at_ms": int(float(parts[3])),
                "body": body,
            }
        )
    return rows


def fact_max_date() -> str | None:
    out = mysql_query(
        "SELECT MAX(stream_start_date_kst) FROM fct_stream"
    ).strip()
    if not out or out.upper() == "NULL":
        return None
    return out.split()[0][:10]


def split_streams(messages: list[dict]) -> list[list[dict]]:
    by_channel: dict[str, list[dict]] = defaultdict(list)
    for msg in messages:
        by_channel[msg["channel_url"]].append(msg)
    streams: list[list[dict]] = []
    for _, arr in by_channel.items():
        arr.sort(key=lambda x: (x["created_at_ms"], x["message_id"]))
        current: list[dict] = []
        for msg in arr:
            if not current:
                current = [msg]
                continue
            if msg["created_at_ms"] - current[-1]["created_at_ms"] > GAP_MS:
                streams.append(current)
                current = [msg]
            else:
                current.append(msg)
        if current:
            streams.append(current)
    return streams


def _frt_ms(stream: list[dict]) -> float | None:
    """사람 파트너 첫응답 기준. 자동응답(미소 AI) 스킵. no-reply → -1."""
    customer = [m for m in stream if m["role"] == "customer"]
    partner = [m for m in stream if m["role"] == "partner"]
    if not customer:
        return None
    first = customer[0]["created_at_ms"]
    later = [
        m
        for m in partner
        if m["created_at_ms"] >= first and not is_auto_reply(m.get("body"))
    ]
    if not later:
        return -1.0  # no-reply sentinel
    return float(later[0]["created_at_ms"] - first)


def first_customer_at(stream: list[dict]) -> datetime | None:
    customer = [m for m in stream if m["role"] == "customer"]
    if not customer:
        return None
    return to_kst(customer[0]["created_at_ms"])


def measure_day(target: date) -> dict:
    """대상일(KST)에 시작한 스트림만. Ops-in = 본지표. Pause·AI 자동응답 제외."""
    day_start = datetime(target.year, target.month, target.day, tzinfo=KST)
    fetch_start = day_start - timedelta(hours=2)
    fetch_end = day_start + timedelta(days=1, hours=6)
    messages = fetch_raw_messages(fetch_start, fetch_end)
    streams = split_streams(messages)
    pauses = detect_pause_windows(messages, target)

    ops_frt: list[float] = []
    ops_no_reply = 0
    off_frt: list[float] = []
    off_no_reply = 0
    ops_customers: set[str] = set()
    n_pause_excluded = 0

    for stream in streams:
        started = first_customer_at(stream)
        if started is None or started.date() != target:
            continue
        if in_pause(started, pauses):
            n_pause_excluded += 1
            continue
        frt = _frt_ms(stream)
        if frt is None:
            continue
        bucket_ops = is_ops_in(started)
        if frt < 0:
            if bucket_ops:
                ops_no_reply += 1
            else:
                off_no_reply += 1
            continue
        if bucket_ops:
            ops_frt.append(frt)
            cust = next(m for m in stream if m["role"] == "customer")
            ops_customers.add(cust["user_id"])
        else:
            off_frt.append(frt)

    def pack(vals: list[float], no_reply: int) -> dict:
        if vals:
            sorted_v = sorted(vals)
            p90 = sorted_v[int(0.9 * (len(sorted_v) - 1))]
            sla = sum(1 for x in vals if x <= SLA_MS) / len(vals)
            avg = sum(vals) / len(vals)
            med = statistics.median(vals)
        else:
            p90 = avg = med = sla = None
        denom = len(vals) + no_reply
        return {
            "n_eligible": len(vals),
            "n_no_reply": no_reply,
            "no_reply_rate": round(no_reply / denom, 4) if denom else None,
            "frt_avg_ms": avg,
            "frt_p50_ms": med,
            "frt_p90_ms": p90,
            "sla_hit_rate": round(sla, 4) if sla is not None else None,
            "avg_min": round(avg / 60000, 1) if avg is not None else None,
            "p50_min": round(med / 60000, 1) if med is not None else None,
            "p90_min": round(p90 / 60000, 1) if p90 is not None else None,
            "sla_pct": round(sla * 100, 1) if sla is not None else None,
            "no_reply_pct": round(no_reply / denom * 100, 1) if denom else None,
        }

    fact_max = fact_max_date()
    source = "fct_stream" if fact_max and fact_max >= target.isoformat() else "raw_message"

    return {
        "date": target.isoformat(),
        "partner_id": PARTNER_ID,
        "sla_ms": SLA_MS,
        "source": source,
        "fact_max_date": fact_max,
        "message_scan_count": len(messages),
        "pause_windows": [
            {"start": s.isoformat(), "end": e.isoformat()} for s, e in pauses
        ],
        "pause_label": format_pause_label(pauses),
        "n_pause_excluded": n_pause_excluded,
        "ops": pack(ops_frt, ops_no_reply),
        "off": pack(off_frt, off_no_reply),
        "ops_unique_customers": len(ops_customers),
        "measured_at": datetime.now(tz=KST).isoformat(),
    }
