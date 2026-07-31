# FRT 3분이내 달성 — 운영 가이드

에이전트는 이 파일을 **목차**로만 쓴다. 세부 정의·쿼리·리포트 포맷은 아래 링크로 들어간다.

## 목표

**운영시간 내 고객 챗 첫 응답을 3분 이내로.**

## 정본 (바꾸지 말고 먼저 읽기)

| 우선 | 경로 | 역할 |
|-----:|------|------|
| 1 | `docs/FRT_DEFINITION.md` | FRT·SLA·Ops-in·Pause(점심) 모수 잠금 (v1.2) |
| 2 | `docs/frt/HARNESS.md` | 일일 측정·보고 루프 |
| 3 | `docs/FRT_KPI_PROPOSAL.md` | K1~K4·단계 목표 |

## 실행

| 경로 | 역할 |
|------|------|
| `.cursor/skills/frt-management/SKILL.md` | 에이전트 실행 순서 |
| `tools/run_frt_daily.py` | 매일 D-1 측정 → MD 리포트 + 집계 CSV → 상태 JSON |
| `tools/build_frt_ops_dashboard.py` | Ops vs Off HTML 대시보드 |
| `tools/refresh_frt_ops_dashboard.py` | 30분 대시보드 갱신 + 배포 |
| `tools/build_frt_weekly.py` | 주간(목요일) 보고서 생성 |
| `queries/frt/*.sql` | fct_stream 템플릿 (Fact 신선할 때) |

## 산출물

| 경로 | 역할 |
|------|------|
| `docs/frt/daily/FRT_DAILY_YYYYMMDD.md` | 일일 마감 리포트 |
| `docs/frt/daily/FRT_DAILY_AGGREGATE.csv` | 일자별 집계 시트(누적) |
| `docs/FRT_REPORT_YYYYMMDD_YYYYMMDD.md` | 스킬 호환 리포트 |
| `docs/WEEKLY_FRT_YYMMDD.md` | 목요일 주간 리포트 |
| `docs/frt/ops_dashboard.html` | 운영/비운영 시각화 |
| `docs/frt/DEPLOY_GITHUB.md` | **GitHub Pages 배포 (추천)** |
| `docs/frt/DEPLOY.md` | Netlify 등 대안 |
| `docs/frt/daily_status.json` | 마지막 일일 런 상태 |
| `docs/frt/QUALITY_SCORE.md` | 측정·보고 품질 점검 |

## 규칙

| 경로 | 역할 |
|------|------|
| `.cursor/rules/frt-chat.mdc` | FRT 요청 시 정의·파일 저장 강제 |

## 한 줄 원칙

1. 정의 문서를 바꾸기 전에 수치/공식을 바꾸지 않는다.  
2. 조회가 되면 리포트 파일 없이 채팅만으로 끝내지 않는다.  
3. Fact(`fct_stream`)가 낡으면 raw 폴백을 쓰고, 리포트에 출처를 명시한다.  
4. 실패는 패치가 아니라 **운영 루프 버그**로 취급한다 → `HARNESS.md` / 스킬 / 스크립트를 고친다.
