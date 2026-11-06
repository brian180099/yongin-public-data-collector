# 에이전트 작업 로그 (Claude Code ↔ Codex)

이 파일은 Claude Code와 Codex가 같은 저장소에서 작업할 때 서로의 작업 내용을
전달하기 위한 공용 기록이다. 2026-11-05 이전 작업은 Git 커밋 이력과
`docs/COLLECTOR_STATUS.md`를 기준으로 한다.

## 작성 규칙

- 작업을 마칠 때마다 **맨 아래에** 항목을 추가한다. 기존 항목은 수정하지 않는다.
  정정이 필요하면 새 항목에 "정정"으로 남긴다.
- 시간은 `YYYY-MM-DD HH:MM KST` 형식으로 쓴다.
- 처리 주체는 `Claude Code` 또는 `Codex` 중 하나로 쓴다.
- 실제로 실행·검증하지 못한 것은 "미검증"으로 쓴다(`AGENTS.md` 지침).
- API 키, 접속 문자열, 원본 데이터 내용은 적지 않는다.
- 상대 에이전트에게 넘길 일이 있으면 `전달 사항`에 적는다.

### 항목 양식

```markdown
### YYYY-MM-DD HH:MM KST · <처리 주체>

- 요약: <무엇을 했는지 한두 줄>
- 변경 파일: <경로 목록 또는 "없음">
- 커밋: <해시 또는 "미커밋">
- 검증: <실행한 테스트·확인 결과, 또는 "미검증">
- 전달 사항: <상대 에이전트가 이어서 볼 내용, 없으면 "없음">
```

## 기록

### 2026-11-05 17:32 KST · Claude Code

- 요약: 커밋 이력 15건(2026-11-03 ~ 2026-11-05)을 분석해 진행 상황을
  사용자에게 브리핑했다. 에이전트 간 공용 작업 로그인 이 파일을 만들고
  `AGENTS.md`에 이 로그를 읽고 기록하라는 지침 한 줄을 추가했다.
- 변경 파일: `docs/AGENT_WORKLOG.md`(신규), `AGENTS.md`(지침 1줄 추가)
- 커밋: 미커밋
- 검증: 문서 작업만 수행. 코드·DB·n8n은 실행하지 않음.
- 전달 사항: `AGENTS.md`의 범위·적재 대상 지침(생활여가·문화·체육 CSV,
  Supabase `collector` 스키마 트랜잭션 적재)과 커밋 `742d967`의 실제 상태
  (용인시 제공 CSV 281종을 로컬 PostgreSQL에 적재, Supabase 추가 쓰기 중단)가
  서로 맞지 않는다. 사용자가 어느 쪽을 기준으로 할지 정하기 전에는 지침을
  임의로 바꾸지 않는다.

### 2026-11-06 11:29 KST · Claude Code

- 요약: 사용자가 운영 DB 정본을 **Supabase**로 확정했다. (1) Supabase를 직접
  읽기 전용 조회해 저장 상태를 확인했고, (2) 미커밋 상태이던 11-06 변경분
  (운영 DB를 로컬→Supabase 복귀, 분석 서비스 통합, 연결 풀 도입, LLM 호출
  축소)의 테스트를 실제 실행해 검증했으며, (3) 로컬 운영이라고 기술돼 있던
  문서 두 건에 Supabase 복귀 갱신 배너를 추가했다.
- 변경 파일: `docs/LOCAL_POSTGRESQL.md`, `docs/BULK_CSV_EXPANSION.md`
  (각 상단에 2026-11-06 운영 경로 갱신 배너 추가), `docs/AGENT_WORKLOG.md`.
- 커밋: 미커밋
- 검증:
  - Supabase 조회 — 등록 자료 278개(active 60), 현재 레코드 262,912행,
    change_history 262,912건, raw_artifacts 253건. collection_runs
    success 246·no_change 13·failed 5·running 1. 실패 5건은 모두 11-04
    `giheung_events` 초기 진단분으로 데이터 손실 아님. `running` 1건
    (`portal_csv_15171160`)은 이후 success 기준 적재 16행 완료, 활성 락 없음.
    등록됐으나 레코드 0행인 자료 32개 발견(원인 미분류).
  - `pytest` — **60 passed, 1 warning in 15.45s** (문서의 "60개 통과" 사실
    확인). `psycopg_pool 3.3.3` 설치 확인, 신규 모듈 import 정상.
- 미검증: 두 Docker 컨테이너 Supabase 재연결·건강상태, n8n 워크플로 교체·게시,
  n8n 종단 응답 시간(~4.9s/~2.1s), n8n 경유 응답 건수. Docker·n8n 미기동.
- 전달 사항: 11-06 변경분(Codex 추정)은 아직 **미커밋**이며 이 로그에
  Codex 항목이 없다. `AGENTS.md` 범위 지침과 Supabase 등록 자료(홈페이지
  접속통계 등 범위 밖 포함, 빈 자료 32개)가 여전히 불일치. 이 32개의
  "재적재 대상 vs 등록 해제 대상" 구분과 범위 지침 정합은 다음 작업으로 남김.

### 2026-11-06 12:06 KST · Claude Code

- 요약: 실제 n8n·컨테이너를 라이브로 확인하고, Codex용 작업 지시 핸드오프
  `docs/CODEX_HANDOFF.md`를 작성했다.
- 변경 파일: `docs/CODEX_HANDOFF.md`(신규), `docs/AGENT_WORKLOG.md`.
- 커밋: 미커밋
- 검증(라이브):
  - n8n HTTP 200, YONGIN 워크플로 3개 모두 active=True
    (YNGN01→yongin-collector:8080, YNGN02 webhook yongin-analysis-v1→yongin-analysis:8080,
    YNGN03 webhook yongin-question-agent-v1→yongin-question-agent:8091).
  - 컨테이너 가동: yongin-collector/analysis(healthy), yongin-question-agent/web,
    yongin-local-postgres(healthy).
  - 두 분석 Webhook POST 종단 응답 확인.
- 발견(불일치):
  - 분석 스택 2개(yongin-analysis=Supabase, yongin-question-agent=로컬 PG)가 동시 active.
    LOCAL_POSTGRESQL.md의 "yongin-analysis 중지" 서술과 모순 → 운영 경로 단일화 필요.
  - "숲체험일정 몇 건이야?" 실호출 시 문서의 8,830건이 아니라 yongin-analysis는
    카탈로그(csv_catalog), yongin-question-agent는 clarification 반환 → 의도 분류 불안정.
- 전달 사항: 상세 지시는 `docs/CODEX_HANDOFF.md`의 P0~P3 참조. 11-06 코드 변경분은
  여전히 미커밋이며 Codex가 직접 커밋·로그 기록할 것.

### 2026-11-06 12:12 KST · Codex

- 요약: Supabase 수집·분석 운영 경로, 대표 질문 규칙 처리, 분석 연결 풀,
  n8n 정의와 웹 문서를 검토했다. 중복 로컬 분석 경로 `YNGN03`을 백업 후
  게시 해제하고 이전 질문 컨테이너의 자동 재시작을 해제·중지해 8090 웹과
  `YNGN02` Supabase 분석 경로로 단일화했다.
- 변경 파일: `README.md`, `compose.collector.yaml`, `docs/COLLECTOR_STATUS.md`,
  `docs/AGENT_WORKLOG.md`, `docs/CODEX_HANDOFF.md`, `pyproject.toml`,
  `requirements.lock`, `src/yongin_collector/analysis_db.py`,
  `src/yongin_collector/chat_analysis.py`, `src/yongin_collector/csv_analysis.py`,
  `src/yongin_collector/static/index.html`, `tests/test_chat_analysis.py`,
  `tests/test_pipeline.py`, `workflows/n8n/yongin-analysis-v1.json`,
  `workflows/n8n/yongin-weekly-collector.json`, `scripts/apply_vehicle_api_selenium.py`,
  `scripts/configure_portal_credentials.ps1`, `scripts/run_vehicle_api_selenium.ps1`.
- 커밋: 이 항목을 포함해 커밋 예정.
- 검증: `pytest` 60개 통과. 수집·분석 컨테이너 healthy, 두 컨테이너 모두
  Supabase 전용 DSN 사용 확인. 활성 n8n은 `YNGN01`·`YNGN02`, `YNGN03`은
  비활성. `yongin-analysis-v1` Webhook에서 숲체험일정 8,830건과 출처 1건을
  실제 확인했고 `yongin-question-agent-v1` Webhook은 비활성 응답을 확인했다.
- 전달 사항: Supabase에 현재 레코드가 없는 등록 자료 32개의 재적재/등록 해제
  분류와 자동차 Open API 활용신청 최종 제출·승인은 아직 완료되지 않았다.

### 2026-11-06 12:14 KST · Codex

- 요약: `origin`을 fetch해 원격 브랜치와 커밋을 재확인했다. 새 원격 브랜치는
  없었고, 검증된 11-06 변경분과 Claude Code 핸드오프를 커밋해 GitHub
  `main`과 동기화했다.
- 변경 파일: `docs/AGENT_WORKLOG.md`.
- 커밋: 기능 변경 `951eeef`, 이 동기화 기록은 후속 문서 커밋.
- 검증: 원격은 `origin/main` 단일 브랜치. 기능 커밋 전 `pytest` 60개 통과,
  staged diff 비밀정보 패턴 없음, `git diff --check`는 빈 줄 경고 외 오류 없음.
- 전달 사항: 원격에 별도 작업 브랜치가 생기면 fetch 후 `main`과 차이를 먼저
  검토하고, 현재 운영 변경을 덮어쓰지 않도록 병합할 것.

### 2026-11-06 12:21 KST · Codex

- 요약: 최신 사용자 지시에 맞춰 수집 저장소를 원본 수집·검증·적재 역할로 다시 한정했다. 구 분석 Webhook `YNGN02AnalysisV1`을 게시 해제하고 `yongin-analysis` 컨테이너를 중지했으며, Compose 정의에서 분석 서비스를 제거했다. 구 워크플로 JSON은 비활성 기록으로 보존했다.
- 변경 파일: `README.md`, `compose.collector.yaml`, `workflows/n8n/yongin-analysis-v1.json`, `docs/COLLECTOR_STATUS.md`, `docs/LOCAL_POSTGRESQL.md`, `docs/AGENT_WORKLOG.md`.
- 커밋: 이 항목 작성 시점 미커밋.
- 검증: 구 Webhook HTTP 404, 새 분석 Webhook HTTP 200·숲체험일정 8,830건, 수집 워크플로 활성 상태. `docker compose config --quiet` 통과, 전체 테스트 60개 통과. 원본·현재 레코드는 수정하지 않았다.
- 다음 작업자에게: 질문 답변은 별도 `LG_AX_개인 프로젝트`의 `localhost:8501`과 `YNGN03QuestionAgentV1`만 사용한다. 구 `yongin-analysis` 서비스와 `YNGN02AnalysisV1`은 다시 게시·실행하지 말 것.

### 2026-11-06 12:29 KST · Codex

- 요약: 공공데이터포털 로그인 대기 중 세션 만료를 줄이기 위해 자동차 API
  활용신청 Selenium 보조기에 별도 계정 탭 60초 주기 새로고침을 추가했다.
  신청 폼 탭은 새로고침하지 않아 입력값을 유지한다.
- 변경 파일: `scripts/apply_vehicle_api_selenium.py`, `README.md`,
  `docs/AGENT_WORKLOG.md`.
- 커밋: 이 항목 작성 시점 미커밋.
- 검증: Python 구문 검사와 `--help` 실행 성공, 전체 `pytest` 60개 통과,
  `git diff --check` 오류 없음. 실제 포털 세션의 60초 유지 여부는 로그인된
  브라우저 장시간 실행 전이므로 미검증.
- 전달 사항: 포털의 절대 세션 만료·강제 로그아웃·CAPTCHA는 우회하지 않는다.
  감지 시 상태 파일에 `session_expired` 또는 `keepalive_failed`를 기록하고 중단한다.

### 2026-11-06 14:57 KST · Codex

- 요약: 기존 Selenium 전용 Chrome 세션에 다시 연결해 공공데이터포털 로그인 완료 후 별도 계정 탭을 60초마다 새로고침하는 세션 유지 루프를 실행했다. 신청서 탭은 새로고침하지 않으며 최종 신청 제출도 수행하지 않았다.
- 변경 파일: `docs/AGENT_WORKLOG.md`.
- 검증: `KEEPALIVE_ACTIVE` 이후 `KEEPALIVE_OK: 2026-11-06T14:57:00+09:00` 로그를 확인했다. 실행 중인 Selenium/Python 프로세스와 전용 Chrome 창이 유지되는 동안에만 동작한다.
- 제한: 포털의 절대 세션 만료, 서버 측 강제 로그아웃, CAPTCHA 재인증은 우회하지 않는다. 감지 시 `session_expired` 또는 `keepalive_failed`로 기록하고 중단한다.

### 2026-11-06 15:32 KST · Codex

- 요약: 공공데이터포털 세션 유지 Selenium 실행기에 창 없는 Chrome `--headless` 모드와 PowerShell `-Headless` 옵션을 추가했다. 저장된 로그인 세션이 없거나 만료된 경우 CAPTCHA를 우회하지 않고 `HEADLESS_LOGIN_REQUIRED`로 종료한다.
- 변경 파일: `scripts/apply_vehicle_api_selenium.py`, `scripts/run_vehicle_api_selenium.ps1`, `README.md`, `docs/AGENT_WORKLOG.md`.
- 검증: Python 구문 검사, PowerShell 파서 검사, CLI 도움말과 `--debugger-address`/`--headless` 충돌 검사를 통과했고 전체 `pytest` 60개가 통과했다. 기존 visible 유지 프로세스는 `2026-11-06T15:32:25+09:00`까지 계속 새로고침 중임을 확인했다.
- 미검증: 현재 visible Chrome이 전용 프로필을 사용 중이므로 프로필 충돌과 로그인 중단을 피하기 위해 실제 headless Chrome 실행은 수행하지 않았다. headless 실행 전 visible Chrome을 종료해야 하며, 포털 세션이 보존되지 않으면 화면 표시 모드에서 다시 로그인해야 한다.

