# -*- coding: utf-8 -*-
"""
FRT 3분이내 달성 — 일일 마감 러너.

D-1(기본) Ops-in FRT 측정 → MD 리포트 2종 → status JSON.
옵션으로 ops 대시보드도 재생성.

사용:
  python tools/run_frt_daily.py
  python tools/run_frt_daily.py --date 2026-07-27
  python tools/run_frt_daily.py --no-dashboard
"""
from __future__ import annotations

import argparse
import csv
import json
import subprocess
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"
FRT_DIR = DOCS / "frt"
DAILY_DIR = FRT_DIR / "daily"
STATUS = FRT_DIR / "daily_status.json"
LOG = FRT_DIR / "daily.log"
AGG_CSV = FRT_DIR / "daily" / "FRT_DAILY_AGGREGATE.csv"
KST = timezone(timedelta(hours=9))

sys.path.insert(0, str(ROOT / "tools"))
from frt_lib import measure_day  # noqa: E402


def log(msg: str) -> None:
    FRT_DIR.mkdir(parents=True, exist_ok=True)
    line = f"{datetime.now(tz=KST).isoformat()} {msg}"
    with LOG.open("a", encoding="utf-8") as f:
        f.write(line + "\n")
    print(msg, flush=True)


def default_target() -> date:
    """기본: 어제(KST). 운영일이 끝난 완전한 하루."""
    return datetime.now(tz=KST).date() - timedelta(days=1)


def render_daily_md(m: dict) -> str:
    ops = m["ops"]
    off = m["off"]
    d = m["date"]
    tag = d.replace("-", "")
    return f"""# FRT 3분이내 달성 — 일일 마감 {d}

- Definition: `docs/FRT_DEFINITION.md` (v1)
- 운영 루프: `docs/frt/HARNESS.md`
- Scope: **Ops-in** (KST 10:00–19:00) = 본지표
- SLA: ≤ 3분 (`SLA_MS=180000`)
- Partner: `{m["partner_id"]}`
- Source: **{m["source"]}** (fct_stream max={m.get("fact_max_date") or "-"})
- Measured: {m["measured_at"]}

---

## 0. 마감 요약 (Ops-in)

| 지표 | 값 |
|------|---:|
| K1 SLA≤3분 | **{ops.get("sla_pct") if ops.get("sla_pct") is not None else "-"}%** |
| K2 FRT p50 | **{ops.get("p50_min") if ops.get("p50_min") is not None else "-"}분** |
| K3 FRT avg | {ops.get("avg_min") if ops.get("avg_min") is not None else "-"}분 |
| K4 무응답률 | {ops.get("no_reply_pct") if ops.get("no_reply_pct") is not None else "-"}% |
| n_eligible | {ops["n_eligible"]} |
| n_no_reply | {ops["n_no_reply"]} |
| unique customers (ops reply) | {m["ops_unique_customers"]} |

---

## 1. Ops-in 상세

| metric | value |
|--------|------:|
| n_eligible | {ops["n_eligible"]} |
| n_no_reply | {ops["n_no_reply"]} |
| no_reply_rate | {ops["no_reply_rate"]} |
| frt_p50_min | {ops.get("p50_min")} |
| frt_p90_min | {ops.get("p90_min")} |
| frt_avg_min | {ops.get("avg_min")} |
| sla_hit_rate | {ops["sla_hit_rate"]} |

---

## 2. Ops-out (참고, SLA 본지표 제외)

| metric | value |
|--------|------:|
| n_eligible | {off["n_eligible"]} |
| n_no_reply | {off["n_no_reply"]} |
| frt_p50_min | {off.get("p50_min")} |
| frt_avg_min | {off.get("avg_min")} |
| sla_hit_rate (참고) | {off["sla_hit_rate"]} |

---

## 3. Notes

- 세션 규칙(raw): 채널 내 60분 무활동 갭 → 새 스트림
- Fact 신선도: `{m.get("fact_max_date") or "unknown"}` — source={m["source"]}
- Dashboard: `docs/frt/ops_dashboard.html`
- Tag: `{tag}`

작성: FRT 일일 마감 (`tools/run_frt_daily.py`)
"""


def render_skill_report(m: dict) -> str:
    ops = m["ops"]
    d = m["date"]
    tag = d.replace("-", "")
    return f"""# FRT Report (KST {d} ~ {d})

- Definition: docs/FRT_DEFINITION.md (v1)
- Scope: Ops-in only (KST 10:00–19:00)
- SLA_MS: 180000 (3 min)
- Partner: {m["partner_id"]}
- Source: {m["source"]}
- Daily twin: docs/frt/daily/FRT_DAILY_{tag}.md

## Summary

| metric | value |
|--------|------:|
| n_eligible | {ops["n_eligible"]} |
| n_no_reply | {ops["n_no_reply"]} |
| no_reply_rate | {ops["no_reply_rate"]} |
| frt_p50_min | {ops.get("p50_min")} |
| frt_p90_min | {ops.get("p90_min")} |
| frt_avg_min | {ops.get("avg_min")} |
| sla_hit_rate | {ops["sla_hit_rate"]} |

## Notes

- EXPLAIN: mysql.exe CLI path (raw_message / fact freshness check)
- Caveats: Fact max={m.get("fact_max_date")}; measured_at={m["measured_at"]}
"""


def write_status(ok: bool, m: dict | None, detail: str) -> None:
    payload = {
        "last_run": datetime.now(tz=KST).isoformat(),
        "ok": ok,
        "detail": detail,
        "interval": "daily 09:00 KST",
        "target_date": m["date"] if m else None,
        "source": m.get("source") if m else None,
        "ops": m.get("ops") if m else None,
        "artifacts": {
            "daily_md": str(DAILY_DIR / f"FRT_DAILY_{(m['date'].replace('-', '') if m else 'NA')}.md")
            if m
            else None,
            "aggregate_csv": str(AGG_CSV),
            "ops_dashboard": str(FRT_DIR / "ops_dashboard.html"),
        },
    }
    STATUS.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def upsert_aggregate_row(m: dict) -> None:
    DAILY_DIR.mkdir(parents=True, exist_ok=True)
    fields = [
        "date",
        "source",
        "partner_id",
        "ops_n_eligible",
        "ops_n_no_reply",
        "ops_no_reply_pct",
        "ops_p50_min",
        "ops_p90_min",
        "ops_avg_min",
        "ops_sla_pct",
        "off_n_eligible",
        "off_n_no_reply",
        "off_p50_min",
        "off_avg_min",
        "off_sla_pct",
        "pause_label",
        "n_pause_excluded",
        "measured_at",
    ]
    row = {
        "date": m["date"],
        "source": m.get("source"),
        "partner_id": m.get("partner_id"),
        "ops_n_eligible": m["ops"].get("n_eligible"),
        "ops_n_no_reply": m["ops"].get("n_no_reply"),
        "ops_no_reply_pct": m["ops"].get("no_reply_pct"),
        "ops_p50_min": m["ops"].get("p50_min"),
        "ops_p90_min": m["ops"].get("p90_min"),
        "ops_avg_min": m["ops"].get("avg_min"),
        "ops_sla_pct": m["ops"].get("sla_pct"),
        "off_n_eligible": m["off"].get("n_eligible"),
        "off_n_no_reply": m["off"].get("n_no_reply"),
        "off_p50_min": m["off"].get("p50_min"),
        "off_avg_min": m["off"].get("avg_min"),
        "off_sla_pct": m["off"].get("sla_pct"),
        "pause_label": m.get("pause_label"),
        "n_pause_excluded": m.get("n_pause_excluded"),
        "measured_at": m.get("measured_at"),
    }

    rows: list[dict] = []
    if AGG_CSV.exists():
        with AGG_CSV.open("r", encoding="utf-8-sig", newline="") as rf:
            rows = list(csv.DictReader(rf))

    by_date = {r.get("date"): r for r in rows if r.get("date")}
    by_date[row["date"]] = {k: ("" if row.get(k) is None else str(row.get(k))) for k in fields}
    out_rows = [by_date[d] for d in sorted(by_date.keys())]

    with AGG_CSV.open("w", encoding="utf-8-sig", newline="") as wf:
        w = csv.DictWriter(wf, fieldnames=fields)
        w.writeheader()
        w.writerows(out_rows)


def main() -> int:
    if sys.platform == "win32":
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except (AttributeError, OSError):
            pass

    ap = argparse.ArgumentParser(description="FRT daily harness")
    ap.add_argument("--date", help="KST YYYY-MM-DD (default: yesterday)")
    ap.add_argument("--no-dashboard", action="store_true")
    args = ap.parse_args()

    target = date.fromisoformat(args.date) if args.date else default_target()
    tag = target.strftime("%Y%m%d")
    log(f"daily start target={target.isoformat()}")

    try:
        m = measure_day(target)
    except Exception as e:
        log(f"daily failed: {e}")
        write_status(False, None, str(e)[:2000])
        return 1

    DAILY_DIR.mkdir(parents=True, exist_ok=True)
    daily_path = DAILY_DIR / f"FRT_DAILY_{tag}.md"
    report_path = DOCS / f"FRT_REPORT_{tag}_{tag}.md"
    daily_path.write_text(render_daily_md(m), encoding="utf-8")
    report_path.write_text(render_skill_report(m), encoding="utf-8")
    snap = DAILY_DIR / f"FRT_DAILY_{tag}.json"
    snap.write_text(json.dumps(m, ensure_ascii=False, indent=2), encoding="utf-8")
    upsert_aggregate_row(m)

    log(f"wrote {daily_path.name} + {report_path.name}")
    log(f"updated {AGG_CSV.name}")
    ops = m["ops"]
    log(
        f"Ops-in K1={ops.get('sla_pct')}% p50={ops.get('p50_min')}m "
        f"avg={ops.get('avg_min')}m n={ops['n_eligible']} source={m['source']}"
    )

    if not args.no_dashboard:
        dash = ROOT / "tools" / "build_frt_ops_dashboard.py"
        proc = subprocess.run(
            [sys.executable, str(dash)],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        if proc.returncode != 0:
            log(f"dashboard rebuild warn: {(proc.stderr or proc.stdout)[:500]}")
        else:
            log("dashboard rebuilt")

    write_status(True, m, "daily report ok")
    log("daily ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
