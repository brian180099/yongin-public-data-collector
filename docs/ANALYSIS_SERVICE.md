# 용인 생활여가 질문 서비스 MVP

기준: 2026-11-04. 이 문서는 실행된 데이터와 기능만 설명한다.

## 현재 데이터와 대표 질문

Supabase `analytics.giheung_events`에 기흥구 이벤트 781행이 있다. 고유키는
`management_id`(원본 `관리번호`), 행사 시작일은 2017~2024년, 원본 기준일은
2026-09-10이다. 제공기관은 경기도 용인시, 원본은
<https://www.data.go.kr/data/15136583/fileData.do>이다. 기준일이 최근이라고
행사 개최 상태가 현재라는 의미는 아니다.

| 실제 지원 질문 | `query_id` | 필터/계산 | 결과 표시 | 검증값 |
|---|---|---|---|---:|
| 기흥구 행사 전체 몇 건이야? | `event_count` | 활성 행의 `count(*)`, 기간 필터 없음 | 답변·표 | 781 |
| 기흥구 2024년 행사 몇 건이야? | `event_count` | `start_date >= 2024-01-01` 및 `< 2025-01-01` | 답변·표 | 105 |
| 기흥구 2024년 월별 행사 수를 보여줘 | `event_monthly` | 같은 연도 필터 후 시작 월별 `count(*)`, 없는 월 0 | 답변·표·막대그래프 | 합계 105 |

각 계산은 검증된 고유키 781개를 가진 현재 활성 스냅샷을 사용한다. 시작일
결측은 연도·월 필터에서 제외한다. 지역 단위는 기흥구 하나이다. 시설 검색
(`facility_search`)과 구별 비교(`regional_comparison`) 의도는 분류하지만,
운영 DB에 시설·다른 구 자료가 없어 `unsupported`로 응답한다. 사용자가
연도 없이 월을 묻거나 현재·예정 행사 여부를 묻는 경우는 `clarification`이다.

정의된 SQL은 `src/yongin_collector/analysis.py`의 `event_count`,
`event_monthly` 두 가지다. 연도·월은 정수 파라미터로 바인딩한다. 사용자 또는
LLM이 만든 SQL을 실행하지 않는다. 결과 최대 12행, `statement_timeout` 5초,
DB 연결 제한 15초를 적용한다. 조회 트랜잭션은 읽기 전용이고
`yongin_analysis_reader`로 `SET ROLE`한다. 이 역할은 `analytics` 뷰만 읽으며
`collector` 스키마의 `USAGE`가 없다.

## 서비스 경로

브라우저 <http://localhost:8090/> → 분석 FastAPI `/ask` → 기존 n8n의 별도
`YONGIN_02_생활여가_질문분석` Webhook → 분석 FastAPI `/v1/analyze` →
Supabase `analytics` 뷰 → n8n JSON 응답 → 화면 표·막대그래프.

n8n 편집 URL: <http://localhost:5678/workflow/YNGN02AnalysisV1>.
Webhook: `POST http://localhost:5678/webhook/yongin-analysis-v1`.
수집 워크플로 `YNGN01CollectWk1`과는 별개다. 프론트엔드에서 DB 또는 n8n
관리 키를 사용하지 않는다. `yongin-analysis`와 `yongin-collector`는 별도
프로세스·컨테이너다.

응답은 `request_id`, `status`, `intent`, `answer`, `filters`, `result`,
`visualization`, `sources`, `calculation`, `limitations`를 포함한다. 상태는
`ok`, `empty`, `clarification`, `unsupported`, `error`다. 출처에는
데이터셋명·기관·기준일·수집일·마지막 정상 갱신일·원본 URL을 포함하고
없는 값은 `null`로 둔다. 데이터베이스 오류 시 수치를 만들지 않는다.
호스트의 `data/analysis_state/analysis_queries.jsonl`에는 질문 원문 없이 요청 ID, 의도,
`query_id`, 필터, 결과 행 수, 상태를 기록한다.

## 실행

```powershell
.\.venv\Scripts\python.exe scripts/apply_migrations.py --apply
.\.venv\Scripts\python.exe scripts/provision_runtime_roles.py
docker compose -f compose.collector.yaml up -d --build
```

외부 화면은 `127.0.0.1:8090`, 수집 API는 `127.0.0.1:8088`에 바인딩한다.
기존 Docker `n8n_default` 네트워크와 n8n 2.31.7이 필요하다. n8n 워크플로는
`workflows/n8n/yongin-analysis-v1.json`을 별도 ID로 가져와 게시한다.
CLI 게시 후 실행 중인 n8n에는 Webhook 등록을 위해 컨테이너 재시작이 필요하다.
서버 이전 시 `.env`, `.runtime/`, `data/`와 n8n의 기존 SQLite 볼륨·암호화 키를 안전하게
백업·복원하고 Compose 외부 네트워크명을 확인한다.

## 현재 제한

- LLM 키가 없어 규칙 기반 의도 분류와 계산 결과의 고정 문장을 사용한다.
  LLM 설명 단계와 정확도 평가는 미구현이다.
- 분석 컨테이너는 별도 `yongin_analysis_login`으로 접속하며 읽기 전용
  트랜잭션과 `SET ROLE yongin_analysis_reader`를 적용한다. 수집 컨테이너는
  `yongin_collector_login`으로 접속한다. `.runtime/`은 컨테이너 볼륨으로
  마운트하지 않는다.
- 로컬 PC가 종료되거나 절전 중이면 n8n 예약 실행과 질문 서비스가 동작하지 않는다.
