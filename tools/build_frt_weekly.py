# -*- coding: utf-8 -*-
"""
FRT 주간 리포트 생성기 (기본: 최근 완료된 목요일 기준 직전 7일).

Usage:
  python tools/build_frt_weekly.py
  python tools/build_frt_weekly.py --end-date 2026-07-30
  python tools/build_frt_weekly.py --template docs/frt/WEEKLY_FRT_TEMPLATE.md
"""
from __future__ import annotations

import argparse
import csv
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"
FRT = DOCS / "frt"
DAILY_AGG = FRT / "daily" / "FRT_DAILY_AGGREGATE.csv"
DEFAULT_TEMPLATE = FRT / "WEEKLY_FRT_TEMPLATE.md"
KST = timezone(timedelta(hours=9))


def _to_float(v: str | None) -> float | None:
    if v is None or v == "":
        return None
    try:
        return float(v)
    except ValueError:
        return None


def _last_thursday(today: date) -> date:
    # Monday=0 ... Thursday=3
    delta = (today.weekday() - 3) % 7
    return today - timedelta(days=delta)


def _load_rows() -> list[dict]:
    if not DAILY_AGG.exists():
        raise FileNotFoundError(f"aggregate csv not found: {DAILY_AGG}")
    with DAILY_AGG.open("r", encoding="utf-8-sig", newline="") as rf:
        rows = list(csv.DictReader(rf))
    return rows


def _fmt(n: float | None, ndigits: int = 1) -> str:
    if n is None:
        return "-"
    return f"{round(n, ndigits):.{ndigits}f}"


def build_weekly(end_date: date, template_path: Path) -> Path:
    rows = _load_rows()
    start_date = end_date - timedelta(days=6)
    period = {
        d.isoformat()
        for d in (start_date + timedelta(days=i) for i in range(7))
    }
    picked = [r for r in rows if (r.get("date") or "") in period]
    picked.sort(key=lambda r: r.get("date") or "")

    if not picked:
        raise RuntimeError(f"no aggregate rows for {start_date}~{end_date}")

    ops_avg_values = [_to_float(r.get("ops_avg_min")) for r in picked]
    ops_avg_values = [v for v in ops_avg_values if v is not None]
    ops_sla_values = [_to_float(r.get("ops_sla_pct")) for r in picked]
    ops_sla_values = [v for v in ops_sla_values if v is not None]
    ops_nr_values = [_to_float(r.get("ops_no_reply_pct")) for r in picked]
    ops_nr_values = [v for v in ops_nr_values if v is not None]
    n_eligible_values = [_to_float(r.get("ops_n_eligible")) for r in picked]
    n_eligible_values = [v for v in n_eligible_values if v is not None]

    ops_avg = sum(ops_avg_values) / len(ops_avg_values) if ops_avg_values else None
    ops_sla = sum(ops_sla_values) / len(ops_sla_values) if ops_sla_values else None
    ops_nr = sum(ops_nr_values) / len(ops_nr_values) if ops_nr_values else None
    ops_n = int(sum(n_eligible_values)) if n_eligible_values else 0

    daily_rows = []
    for r in picked:
        daily_rows.append(
            "| {date} | {avg} | {sla} | {n} | {nr} |".format(
                date=r.get("date") or "-",
                avg=_fmt(_to_float(r.get("ops_avg_min"))),
                sla=_fmt(_to_float(r.get("ops_sla_pct"))),
                n=r.get("ops_n_eligible") or "-",
                nr=_fmt(_to_float(r.get("ops_no_reply_pct"))),
            )
        )

    tpl = template_path.read_text(encoding="utf-8")
    week_label = f"{start_date.strftime('%y.%m.%d')}~{end_date.strftime('%y.%m.%d')}"
    out = (
        tpl.replace("{{WEEK_LABEL}}", week_label)
        .replace("{{GENERATED_AT}}", datetime.now(tz=KST).strftime("%Y-%m-%d %H:%M KST"))
        .replace("{{START_DATE}}", start_date.isoformat())
        .replace("{{END_DATE}}", end_date.isoformat())
        .replace("{{OPS_AVG_MIN}}", _fmt(ops_avg))
        .replace("{{OPS_SLA_PCT}}", _fmt(ops_sla))
        .replace("{{OPS_NO_REPLY_PCT}}", _fmt(ops_nr))
        .replace("{{OPS_N_ELIGIBLE}}", f"{ops_n}")
        .replace("{{DAILY_ROWS_MD}}", "\n".join(daily_rows))
    )

    tag = end_date.strftime("%y%m%d")
    out_path = DOCS / f"WEEKLY_FRT_{tag}.md"
    out_path.write_text(out, encoding="utf-8")
    return out_path


def main() -> int:
    ap = argparse.ArgumentParser(description="build weekly FRT markdown")
    ap.add_argument("--end-date", help="YYYY-MM-DD, default=recent Thursday(KST)")
    ap.add_argument(
        "--template",
        default=str(DEFAULT_TEMPLATE),
        help="weekly template markdown path",
    )
    args = ap.parse_args()

    today = datetime.now(tz=KST).date()
    end_date = date.fromisoformat(args.end_date) if args.end_date else _last_thursday(today)
    template_path = Path(args.template)
    if not template_path.is_absolute():
        template_path = ROOT / template_path
    if not template_path.exists():
        raise FileNotFoundError(f"template not found: {template_path}")

    out = build_weekly(end_date, template_path)
    print(f"weekly report created: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
