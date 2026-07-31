# FRT 3분이내 달성 — 정의 (chat_poc)

> **상태**: v1.2 잠금안  
> **데이터**: `chat_poc.raw_message` (운영) / `fct_stream` (Fact 신선 시)  
> **관련**: `CHAT_POC_SCHEMA_SAMPLE.md`, `CX_DEFINITION_202603_202605.md`, `ORDER_LEAD_SLOT_METRIC_WINDOWS.md`

이 문서는 FRT 집계·리포트의 **단일 기준서**다. 에이전트·자동화는 이 정의를 바꾸지 않고, 변경이 필요하면 문서 버전을 올린다.

---

## 1. 한 줄 정의

**FRT** = 세션(`fct_stream`)에서 고객이 말한 뒤, **파트너의 첫 응답까지 걸린 시간(ms)**.

정본 컬럼: `fct_stream.first_response_ms`

**목표**: **운영시간 내** FRT **≤ 3분** (SLA).

---

## 2. 측정 단위

| 항목 | 값 |
|------|-----|
| 단위 | **스트림(세션)** — `partner_id` + `channel_url` + `stream_seq` |
| 기간 필터 | `stream_start_date_kst` (KST 일자) |
| 채널/고객 롤업 | 스트림 FRT를 채널·일자로 재집계할 때만 사용 (기본 리포트는 스트림) |

채널 lifetime “첫 고객 문의 → 첫 파트너 응답”은 **별도 지표(Channel FRT)** 로 부르며, 기본 FRT와 혼용하지 않는다.

---

## 3. 운영시간 (Ops-in)

리드·매칭 지표와 동일 (`ORDER_LEAD_SLOT_METRIC_WINDOWS.md`):

| 구분 | KST 구간 |
|------|----------|
| **운영시간 내 (Ops-in)** | 당일 **10:00 ≤ t < 19:00** |
| **운영시간 외 (Ops-out)** | 전일 19:00 ≤ t < 당일 10:00 |

### 3.1 FRT에 적용하는 방식

- **SLA·목표 리포트 모수** = Ops-in 스트림만.
- 판정 시각: 스트림 시작의 KST 시각  
  `stream_start_kst = FROM_UNIXTIME(stream_start_ms/1000) + 9h`  
  → `HOUR(stream_start_kst) IN (10..18)` 즉 **10:00 ≤ hour < 19:00**.
- Ops-out은 별도 섹션으로만 집계(참고). SLA 준수율 본지표에 **넣지 않음**.

---

## 4. 모수 (eligible streams) — SLA 본지표

다음을 **모두** 만족:

```text
Ops-in (stream start KST hour 10..18)
AND customer_msg_count > 0
AND has_partner_reply = 1
AND first_response_ms IS NOT NULL
AND first_response_ms >= 0
```

| 포함 | 제외 |
|------|------|
| 운영시간 내 시작 + 고객 발화 + 파트너(사람) 응답 | Ops-out |
| `starter_role` 무관 | Pause 구간 시작 세션 (§4.2) |
| | `has_partner_reply = 0` (사람 응답 없음) |
| | `first_response_ms` NULL |
| | 고객 메시지 0 (ADMM만 등) |

### 4.1 무응답 보조 지표 (FRT와 분리, Ops-in만)

```text
no_reply_streams =
  Ops-in
  AND customer_msg_count > 0
  AND has_partner_reply = 0
```

무응답률 = `no_reply / (eligible_frt + no_reply)`. FRT 중앙값에 무응답을 섞지 않는다.

### 4.2 일시 부재(Pause) 구간 — 점심 자동응답 (v1.2)

운영시간 **중** 자리비움(점심 등)은 Ops-out이 아니므로, 자동응답 본문에서 구간을 읽어 **모수에서 제외**한다.

| 단계 | 규칙 |
|------|------|
| 탐지 | 파트너 `MESG` body에 `미소 AI`(또는 `[미소 AI]`) **그리고** `점심` |
| 시각 파싱 | `HH시 MM분 - HH시 MM분` → 당일 KST `[start, end)` |
| 무시 | `운영시간` + `외` 안내(운영외 자동응답). Pause로 **쓰지 않음** |
| 제외 | **고객 첫 문의 시각**이 Pause에 있으면 해당 세션 전체 FRT 집계에서 제외 |

운영외 자동응답은 기존 Ops-out 필터로 이미 본지표에서 빠진다.

---

## 5. 응답 인정 범위

`raw_message` 재구성 경로(현재 운영) 기준:

- 파트너 응답 = `user_id`가 `Supplier_` 인 `MESG` / `FILE`
- 시스템 `ADMM`은 파트너 응답으로 **치지 않음**
- **`미소 AI` / `[미소 AI]` 자동응답은 파트너 첫 응답으로 치지 않음** (v1.2). 이후 **사람** 파트너 메시지까지를 FRT로 측정
- Fact(`fct_stream`) 경로를 쓸 때는 웨어하우스 빌드가 동일 규칙을 반영하기 전까지 raw 폴백을 우선

---

## 6. SLA·리포트 지표

| 이름 | 값 |
|------|-----|
| `SLA_MS` | **180000** (3분) |
| 목표 | 운영시간 내 `first_response_ms <= 180000` |
| 목표 `sla_hit_rate` | 단계안: T1 40% → T2 55% → T3 70% (`docs/FRT_KPI_PROPOSAL.md`, 합의 전) |

기간 `[start_date, end_date]` (양끝 포함, KST), **Ops-in 모수** 기준:

| 지표 | 산출 |
|------|------|
| `n_eligible` | 모수 스트림 수 |
| `n_no_reply` | Ops-in 무응답 수 |
| `no_reply_rate` | `n_no_reply / (n_eligible + n_no_reply)` |
| `frt_p50_ms` / `frt_p90_ms` / `frt_avg_ms` | 모수 내 분포 |
| `sla_hit_rate` | `first_response_ms <= 180000` 비율 |

표시: ms → 분 (`/ 60000`, 소수 1자리).

---

## 7. 금지·주의

1. **EXPLAIN 없이** `chat_poc` 집계 실행 금지 (`DATA_ANALYSIS_CONTEXT.md` §0).
2. 대용량 시 `stream_start_date_kst` + `partner_id` 조건 필수.
3. `created_ts`를 KST로 가정하지 않는다. 시각은 `stream_start_ms` + 9h 또는 `*_date_kst`.
4. Ops-out FRT를 본 SLA에 섞지 않는다.
5. 정의 변경 없이 Channel FRT를 본지표에 넣지 않는다.
6. Pause가 아닌 자동응답(점심 키워드·시각 없음)을 NLP로 추정해 제외하지 않는다.

---

## 8. 운영 산출물

| 경로 | 역할 |
|------|------|
| `docs/FRT_DEFINITION.md` | 본 정의 (정본) |
| `docs/frt/AGENTS.md` | 운영 가이드 목차 |
| `docs/frt/HARNESS.md` | 일일 측정·보고 루프 |
| `.cursor/skills/frt-management/SKILL.md` | 에이전트 실행 절차 |
| `tools/run_frt_daily.py` | 매일 D-1 마감 러너 |
| `queries/frt/*.sql` | 재현 쿼리 (fct_stream) |
| `.cursor/rules/frt-chat.mdc` | FRT 요청 시 정의·파일 저장 강제 |

리포트:
- 일일: `docs/frt/daily/FRT_DAILY_YYYYMMDD.md`
- 스킬 호환: `docs/FRT_REPORT_YYYYMMDD_YYYYMMDD.md`
- 대시보드: `docs/frt/ops_dashboard.html`

---

## 9. 개정 이력

| 버전 | 일자 | 내용 |
|------|------|------|
| v0 | 2026-07-26 | 초기안. SLA 5분 placeholder |
| v1 | 2026-07-26 | 목표 확정: Ops-in(KST 10~19) FRT ≤ 3분. SLA_MS=180000 |
| v1.1 | 2026-07-28 | 일일 하네스 산출물·러너 경로 문서화 (정의 공식 동일) |
| v1.2 | 2026-07-28 | Pause(점심 자동응답 구간) 세션 제외 · 미소 AI 자동응답 첫응답 미인정 |
