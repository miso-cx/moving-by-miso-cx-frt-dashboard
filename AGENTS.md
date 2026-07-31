# AGENTS.md — miso_automation

에이전트용 **짧은 맵**. 세부 문서는 링크로만 연다.

## FRT 3분이내 달성

→ `docs/frt/AGENTS.md`

일일 마감: `python tools/run_frt_daily.py`  
정의: `docs/FRT_DEFINITION.md`  
운영 루프: `docs/frt/HARNESS.md`

## 데이터 접근

→ `DATA_ANALYSIS_CONTEXT.md` (EXPLAIN-before-SELECT)  
→ `tools/MYSQL_CONNECTION.txt` (mysql.exe 폴백)

## 원칙

1. 정의 문서 없이 지표 공식을 바꾸지 않는다.  
2. 조회 결과가 나오면 채팅만으로 끝내지 말고 산출물 파일을 남긴다.  
3. 같은 실수가 반복되면 스크립트/룰/스킬(하네스)을 고친다.
