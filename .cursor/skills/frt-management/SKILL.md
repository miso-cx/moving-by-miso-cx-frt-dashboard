---
name: frt-management
description: >-
  Measures and reports chat First Response Time (FRT) from chat_poc using the
  locked definition in docs/FRT_DEFINITION.md. Use when the user asks for FRT,
  first response time, 첫 응답, 응답 속도, SLA 준수율, daily FRT, 데일리 FRT,
  FRT 마감, or partner reply latency on Sendbird/chat_poc.
---

# FRT 3분이내 달성

## Goal

Reproduce **Ops-in stream-level FRT** for a KST date (or range): eligible count, no-reply rate, p50/p90, SLA hit rate (≤ **3 min**). Do not invent a new FRT formula.

- Ops-in: stream start KST hour 10–18 (10:00 ≤ t < 19:00)
- `SLA_MS` = `180000`
- Daily cadence: D-1 report via `tools/run_frt_daily.py` (`docs/frt/HARNESS.md`)

## Mandatory reads (before any query)

1. `docs/frt/AGENTS.md` — map
2. `docs/FRT_DEFINITION.md` — sole definition
3. `docs/frt/HARNESS.md` — daily loop
4. `DATA_ANALYSIS_CONTEXT.md` §0 — EXPLAIN-before-SELECT (when using SQL templates)

## Execution spine

### A) Daily closing (default when user says 어제/오늘 마감/데일리 FRT)

```text
FRT daily:
- [ ] 1. Target date = yesterday KST (or --date)
- [ ] 2. python tools/run_frt_daily.py [--date YYYY-MM-DD]
- [ ] 3. Confirm docs/frt/daily/FRT_DAILY_YYYYMMDD.md + docs/FRT_REPORT_YYYYMMDD_YYYYMMDD.md
- [ ] 4. Chat: K1 SLA%, K2 p50, K3 avg, K4 no_reply, n_eligible, source=
```

### B) Ad-hoc range (skill classic path)

```text
FRT run:
- [ ] 1. Confirm period; SLA_MS=180000; Ops-in only
- [ ] 2. Prefer run_frt_daily per day OR queries/frt/*.sql if fct_stream fresh
- [ ] 3. Write docs/FRT_REPORT_{start}_{end}.md
- [ ] 4. Chat summary: n, p50, p90, sla_hit, no_reply_rate
```

### Step rules

1. **Period**: Ask if missing. Daily default = D-1 KST.
2. **Definition lock**: Use `FRT_DEFINITION.md`. Change formula only after version bump.
3. **DB**: `chat_poc`. Prefer `tools/frt_lib.py` / mysql.exe. Fact stale → raw fallback, label `source=`.
4. **Output files**: Always save daily MD + `FRT_REPORT_*`. Chat alone is not enough.
5. **Display**: minutes = `ms/60000` (1 decimal).

## Report template (range)

```markdown
# FRT Report (KST YYYY-MM-DD ~ YYYY-MM-DD)

- Definition: docs/FRT_DEFINITION.md (v1)
- Scope: Ops-in only (KST 10:00–19:00)
- SLA_MS: 180000 (3 min)
- Partner: ...

## Summary
| metric | value |
|--------|------:|
| n_eligible | |
| n_no_reply | |
| no_reply_rate | |
| frt_p50_min | |
| frt_p90_min | |
| sla_hit_rate | |

## Notes
- EXPLAIN: ok / issues
- Caveats
```

## Out of scope (unless user asks)

- Channel lifetime FRT (label separately)
- Template-message exclusion (v2)
- Editing Cursor Automations (automate skill only if asked)

## Failure modes

| Symptom | Action |
|---------|--------|
| Access denied | mysql.exe path (`MYSQL_CONNECTION.txt` §5b) |
| `fct_stream` stale | raw fallback via `run_frt_daily` / `frt_lib`; note source |
| Definition conflict | Propose definition vN, wait for approval |
| Missing report file | Harness bug — fix runner/skill, re-run |
