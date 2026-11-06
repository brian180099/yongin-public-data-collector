# Codex 작업 지시 (핸드오프)

작성: Claude Code · 2026-11-06 12:06 KST
읽는 주체: Codex. 작업 전 `docs/AGENT_WORKLOG.md`를 먼저 읽고, 작업 후 그 파일
맨 아래에 처리 주체·요약·시간을 기록한다. `AGENTS.md` 지침을 따른다.

---

## 1. 프로젝트 한 줄 정의

용인시 공공데이터를 자연어로 조회·분석하는 서비스. LLM은 질문을 "조회 계획(JSON)"으로
번역만 하고, 실제 계산은 서버가 검증된 읽기 전용 SQL로 수행한다. 모든 답변에
출처·기준일·계산 방법을 함께 제시한다. (환각 차단이 핵심)

## 2. 지금까지 확인된 사실 (Claude Code가 실제 검증)

- **Supabase가 운영 DB** (사용자가 정본 확정). 2026-11-06 직접 조회 기준:
  등록 자료 278개(active 60), 현재 레코드 262,912행, change_history 262,912건,
  raw_artifacts 253건. collection_runs: success 246·no_change 13·failed 5·running 1.
  - failed 5건은 11-04 `giheung_events` 초기 진단분 → 데이터 손실 아님.
  - running 1건 `portal_csv_15171160` → 이후 success 기준 적재 16행 완료, 활성 락 없음.
- **테스트**: `pytest` 60 passed (문서의 "60개 통과" 사실 확인). `psycopg_pool 3.3.3` 설치됨.
- **n8n 가동 중**(HTTP 200). YONGIN 워크플로 3개 모두 active=True:
  - `YNGN01CollectWk1` → `yongin-collector:8080`
  - `YNGN02AnalysisV1` (webhook `yongin-analysis-v1`) → `yongin-analysis:8080` (이 저장소, Supabase)
  - `YNGN03QuestionAgentV1` (webhook `yongin-question-agent-v1`) → `yongin-question-agent:8091` (별도 프로젝트, 로컬 PG)
  - 두 분석 Webhook 모두 종단 응답은 됨.

## 3. 변경 사항 (현재 작업 트리 상태)

### 커밋됨
- `046ae71` 공용 작업 로그 `docs/AGENT_WORKLOG.md` 신설 + `AGENTS.md`에 로그 기록 지침 1줄.
- `2429cb1` 운영 DB를 Supabase로 표기, 11-06 검증 기록. 문서 3건
  (`AGENT_WORKLOG.md`, `BULK_CSV_EXPANSION.md`, `LOCAL_POSTGRESQL.md`) 상단에 "운영 DB=Supabase,
  로컬 적재분은 보존용 스냅샷" 배너 추가.

### 미커밋 (11-06 오전, Codex 작업으로 추정 — Codex가 직접 커밋·검증할 것)
- 운영 DB 로컬→Supabase 복귀: `compose.collector.yaml`(`local-collector.env`→`collector.env`),
  `README.md`, `docs/COLLECTOR_STATUS.md`.
- 연결 풀 도입: 새 파일 `src/yongin_collector/analysis_db.py`,
  `chat_analysis.py`·`csv_analysis.py`가 `psycopg.connect` → `analysis_pool().connection()`.
  의존성 `psycopg[binary,pool]`, `psycopg-pool==3.3.3`, `selenium>=4.38`.
- LLM 호출 축소: 대표 MVP 질문은 규칙+고정 SQL만, 자유형 CSV 질문만 OpenAI.
  새 테스트 `test_known_mvp_question_does_not_wait_for_model`.
- n8n 워크플로 JSON `active: false→true` (분석·수집 둘 다), 관련 테스트 수정.
- 웹 주소 `8501`→`8090`.
- 새 스크립트 3건: `scripts/apply_vehicle_api_selenium.py`, `run_vehicle_api_selenium.ps1`,
  `configure_portal_credentials.ps1` (자동차 등록 API 활용신청, 자동 제출 안 함).

## 4. 해야 할 일 (우선순위)

### P0 — 운영 경로·일관성 (지금 바로)
1. **11-06 미커밋 변경분을 Codex가 검토·커밋한다.** `docs/AGENT_WORKLOG.md`에 Codex
   항목이 없다 — 반드시 기록할 것.
2. **분석 스택이 2개 동시 active 문제 해결.** `yongin-analysis`(Supabase)와
   `yongin-question-agent`(로컬 PG)가 둘 다 켜져 있고 둘 다 n8n에서 active다.
   `docs/LOCAL_POSTGRESQL.md`는 "yongin-analysis는 중지"라고 적혀 있어 실제와 모순.
   → 운영 경로를 **하나로 확정**하고(웹 8090이 어느 Webhook을 쓰는지 포함), 나머지는
   비활성화하거나 문서를 실제에 맞게 갱신한다.

### P1 — 정확성 (환각 차단의 신뢰성)
3. **의도 분류 불안정 수정.** "숲체험일정 몇 건이야?"를 두 Webhook에 실제 호출한 결과,
   문서가 말한 "8,830건"이 아니라 `yongin-analysis`는 카탈로그 목록(`csv_catalog`),
   `yongin-question-agent`는 되묻기(clarification)를 반환했다. 대표 질문이 매번 같은
   의도로 해석되도록 규칙/프롬프트를 보강하고 회귀 테스트를 추가한다.

### P2 — 데이터 범위 정리
4. **빈 자료 32개 처리.** Supabase에 등록됐지만 레코드 0행인 자료 32개(홈페이지 접속통계,
   주정차단속, 빅데이터 플랫폼 통계, ZIP 2번째 CSV 등). 각 `collection_runs`를 보고
   "재적재 대상 / 범위 밖이라 등록 해제 대상"으로 분류한다.
5. **`AGENTS.md` 범위 지침 vs 실제 자료 정합.** 지침은 "생활여가·문화·체육 CSV"인데
   Supabase엔 범위 밖(홈페이지 통계 등) 자료도 등록돼 있다. 지침을 넓히든 자료를
   정리하든 사용자 결정에 맞춰 일치시킨다.

### P3 — 로드맵(미착수, 완료로 표기 금지)
6. 데이터셋별 "분석 가능 컬럼 계약" 사전 검증·캐시 (1천만 행+ 성능).
7. 날짜 범위(부터~까지) 조회, 정렬·상위 N·합계·평균(검증된 숫자 컬럼만).
8. 316개 자료 목록 검색·필터, 표·차트 정리, 모바일·접근성.
9. DB 백업·복구, 상태 점검, (필요 시) 외부 공개용 인증·보안.
10. 자동 재수집·재검증·변경 이력 체계 완성 후 스케줄 가동.

## 5. 지켜야 할 규칙 (재확인)

- 실제로 실행·검증 못 한 것을 완료로 표기하지 않는다.
- 원본 바이트·출처·수집일·데이터 기준일·해시 보존. 키·원본 파일은 Git에 올리지 않는다.
- Git 이력 보존, force push 금지.
- 수집기는 분석 통계를 하지 않는다. 품질 통과분만 트랜잭션 적재.
