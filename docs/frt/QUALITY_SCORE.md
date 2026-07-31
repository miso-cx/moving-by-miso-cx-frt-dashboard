# FRT 3분이내 달성 — 측정 품질 점검

수치 KPI(K1)와 별개로, **측정·보고가 믿을 만한가**를 추적한다.

채점: A / B / C / D (A=운영 가능, D=즉시 수정)

| 영역 | 현재 | 기준 | 메모 |
|------|:----:|------|------|
| Definition lock | A | `FRT_DEFINITION.md` v1 + SLA 3분 고정 | 임의 공식 변경 없음 |
| Daily runner | B | `run_frt_daily.py` + 09:00 스케줄 | 도입일 기준, 연속 7일 성공 시 A |
| Report artifacts | B | `FRT_DAILY_*` + `FRT_REPORT_*` 쌍 | 누락 시 C |
| Dashboard refresh | B | 1시간 `OpsHourly` | LastTaskResult=0 유지 |
| Fact freshness | C | `fct_stream` ≥ 대상일 | 현재 raw 폴백 의존 |
| Agent skill/rule | A | skill + alwaysApply rule | |
| Observability | B | `daily_status.json` / logs | |

## 목표 상태 (다음 2주)

1. Fact 재빌드 → Fact freshness **A**, raw는 검증용만  
2. 일일 런 7일 연속 ok → Daily runner **A**  
3. QUALITY_SCORE 주 1회 갱신 (금요일 또는 실패 직후)

## 개정

| 일자 | 변경 |
|------|------|
| 2026-07-28 | 초기 채점 |
