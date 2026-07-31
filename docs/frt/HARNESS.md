# FRT 3분이내 달성 — 일일 운영 루프

> 목표: **매일** Ops-in FRT를 같은 정의로 측정·보고하고, **3분 이내 응답**을 추적한다.  
> 맵: `docs/frt/AGENTS.md` · 정본: `docs/FRT_DEFINITION.md` **v1.2**

실무 운영 원칙:

| 원칙 | 구현 |
|------|------|
| 짧은 목차 | `docs/frt/AGENTS.md` → 정의/스킬/쿼리로만 깊게 들어감 |
| 정의 잠금 | `FRT_DEFINITION.md` 버전업 없이 공식 변경 금지 |
| Pause 제외 | 점심 `[미소 AI]` 자동응답 구간 시작 세션은 모수 제외 (§4.2) |
| 매일 자동 | `run_frt_daily.py` + Windows 일일 작업 + Cursor rule/skill |
| 상태 확인 | `daily_status.json`, `refresh_status.json`, 로그 |
| 반복 실수 | 수치 오류·누락 리포트는 스크립트/정의/스킬을 고침 |

---

## 1. 일일 루프 (D-1 마감)

기본 대상일 = **어제(KST)**. 운영시간(10~19)이 끝난 완전한 하루를 보고한다.

```text
09:00 KST (스케줄)
  → tools/run_frt_daily.py
      1. 대상일 확정 (기본: D-1)
      2. chat_poc.raw_message 조회 (Fact 신선하면 fct_stream 우선 가능)
      3. Ops-in eligible / no-reply / p50 / avg / SLA≤3분 산출
      4. docs/frt/daily/FRT_DAILY_YYYYMMDD.md 저장
      5. docs/FRT_REPORT_YYYYMMDD_YYYYMMDD.md 동기 저장
      6. (옵션) ops 대시보드 재생성
      7. docs/frt/daily_status.json 갱신
```

보조 루프: **매 30분** `refresh_frt_ops_dashboard.py` → `ops_dashboard.html` + GitHub Pages 배포.

---

## 2. 본지표 (매일 반드시)

| ID | 지표 | 정의 |
|----|------|------|
| **K1** | SLA 준수율 | Ops-in eligible 중 FRT ≤ 3분 |
| K2 | FRT p50 | Ops-in 중위값(분) |
| K3 | FRT avg | Ops-in 평균(분) — 꼬리 참고 |
| K4 | 무응답률 | Ops-in no_reply / (eligible+no_reply) |

Ops-out은 대시보드·일일 리포트 **참고 섹션**만. K1에 섞지 않음.

단계 목표: `docs/FRT_KPI_PROPOSAL.md` (T1 40% → T2 55% → T3 70%).

---

## 3. 데이터 소스 정책

| 조건 | 소스 |
|------|------|
| `fct_stream` max 날짜 ≥ 대상일 | `fct_stream.first_response_ms` (정본 경로) |
| Fact가 대상일보다 오래됨 | `raw_message` + 60분 갭 세션 재구성 (폴백) |

리포트 상단에 `source=` 를 반드시 적는다. 폴백은 임시가 아니라 **현재 운영 경로**로 취급하되, Fact 재빌드 후 정본으로 회귀한다.

---

## 4. 스케줄 (Windows)

| 작업명 | 주기 | 스크립트 |
|--------|------|----------|
| `MisoAutomation_FRT_Daily` | 매일 09:00 | `tools/run_frt_daily.py` |
| `MisoAutomation_FRT_OpsHourly` | 매 30분 | `tools/refresh_frt_ops_dashboard.py` |
| `MisoAutomation_FRT_Weekly` | 매주 목요일 09:10 | `tools/build_frt_weekly.py` |

등록:

```powershell
powershell -ExecutionPolicy Bypass -File tools\register_frt_daily_task.ps1
powershell -ExecutionPolicy Bypass -File tools\register_frt_hourly_task.ps1
powershell -ExecutionPolicy Bypass -File tools\register_frt_weekly_task.ps1
```

---

## 5. 에이전트 계약

사용자가 「오늘/어제 FRT」「데일리 FRT」「FRT 마감」을 말하면:

1. `FRT_DEFINITION.md` 준수  
2. `run_frt_daily.py` 실행 또는 동일 산출물 수동 재현  
3. `docs/frt/daily/FRT_DAILY_*.md` + `FRT_REPORT_*` 저장  
4. 채팅에 K1~K4 요약

정의와 다른 요청이면 **정의 버전을 먼저** 올리고 실행한다.

---

## 6. 실패 시

| 증상 | 조치 |
|------|------|
| Access denied / mysql 실패 | `tools/MYSQL_CONNECTION.txt` §5b (mysql.exe) |
| Fact stale | raw 폴백 + status에 warning |
| 리포트 파일 없음 | 운영 루프 버그 — runner/skill 수정 |
| SLA 공식 임의 변경 | 거부 → 정의 개정 PR/문서만 |

---

## 7. 개정

| 버전 | 일자 | 내용 |
|------|------|------|
| 0.1 | 2026-07-28 | 일일 루프·스케줄·산출물 경로 도입 |
| 0.2 | 2026-07-30 | ops 대시보드 하단 **추가 답변 필요** 섹션 (규칙+Anthropic) |

---

## 8. 추가 답변 필요 (Follow-up) 섹션

`build_frt_ops_dashboard.py` 빌드 시 `tools/chat_followup_analyzer.py`가 당일 채팅을 분석해 대시보드 하단에 표시한다.

| 항목 | 내용 |
|------|------|
| 데이터 | `chat_poc.raw_message` + `raw_channel` (KST 당일) |
| 1단계 | 규칙 후보 (미응답, 확인 후 대기, 짧은 답변 등) |
| 2단계 | Anthropic API 문맥 판별 (`needs_reply` / `needs_detail` / `resolved`) |
| 공개 필드 | 주문번호(`request_id`), 마스킹 고객명, 짧은 사유만 |
| 비공개 | API 키, 원문 대화, 채널 URL, 연락처·주소 |
| 캐시 | `docs/frt/followup_cache/YYYYMMDD.json` (대화 지문 기준) |
| 실패 시 | 빌드 중단 없음 — 규칙 폴백 또는 빈 목록 + `judge_mode` 표시 |

### 설정

```powershell
copy secrets\anthropic.env.example secrets\anthropic.env
# ANTHROPIC_API_KEY 입력
pip install -r requirements-frt.txt
```

키 없으면 규칙만으로 판별 (`judge_mode=rules_only` 또는 `no_api_key`).

### 수동 실행

```powershell
python tools/chat_followup_analyzer.py --date 2026-07-30
python tools/chat_followup_analyzer.py --date 2026-07-30 --no-ai
```

30분 스케줄(`refresh_frt_ops_dashboard.py`)과 동일하게 대시보드 재빌드 시 자동 반영된다.

