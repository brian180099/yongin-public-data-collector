# 용인시 제공 CSV 로컬 적재

> 2026-11-06 현재 질문 분석 웹은 `http://localhost:8501`이며 전용 n8n Webhook `yongin-question-agent-v1`을 사용한다. 이 문서의 `yongin-analysis-v1` 경로 설명은 이전 운영 기록이다.

> **갱신(2026-11-06):** 정기 수집의 운영 DB는 **Supabase**다. 별도 분석 웹은
> 로컬 스냅샷과 Supabase의 마지막 정상 적재 시각을 비교해 자료별 조회 DB를 고른다.
> 아래의 로컬 PostgreSQL 대량 적재분은 수집기의 자동 갱신 대상이 아니다.
> 최신 운영 상태는 [COLLECTOR_STATUS.md](COLLECTOR_STATUS.md)와
> [README.md](../README.md)를 기준으로 한다. 이 문서는 로컬 대량 적재 절차의
> 기록이다.

2026-11-05 기준 공공데이터포털 파일데이터에서 `용인`, `용인시`를 검색해 중복을 제거하고, CSV 표시 자료 중 제공기관이 정확히 `경기도 용인시`인 자료만 대상으로 삼았다. 검색 결과는 고유 자료 384종, CSV 표시 자료 348종, 이 중 용인시 제공 281종이다. 다른 제공기관의 67종은 사용자의 범위 선택에 따라 제외했다. 검색 목록은 Git 제외 경로 `data/state/portal_search_inventory.json`에 보관한다.

Supabase Free 인스턴스의 기존 원본·현재 레코드·변경 이력은 보존했다. 추가 대량 적재는 중단하고, 그 시점의 DB를 로컬 PostgreSQL로 복제한 다음 로컬에 적재한다. 두 DB는 자동 동기화되지 않는다. 웹과 n8n 분석 경로는 로컬 DB의 별도 읽기 전용 로그인 `yongin_analysis_login`을 사용한다. 수집·적재는 로컬 쓰기 로그인 `yongin_collector_login`을 사용한다.

## 실행 경로

```text
공식 포털 CSV → data/raw 원본 보존 → 구조·건수 검증 → 로컬 PostgreSQL collector
                                                       ↓ 읽기 전용 analytics 뷰
Streamlit 웹 :8501 → n8n Webhook /webhook/yongin-analysis-v1 → 질문 분석 서비스 :8091
```

로컬 DB는 `compose.local-db.yaml`의 `yongin-local-postgres` 컨테이너와 영속 볼륨에 있다. 수집기 서비스는 `compose.collector.yaml`의 `yongin-collector`다. 이전 `yongin-analysis` 서비스는 중복 응답을 막기 위해 중지 상태로 둔다. 실제 분석·답변은 별도 `LG_AX_개인 프로젝트`의 `yongin-question-agent`가 맡는다.

비밀 값은 Git 제외 `.runtime/`에만 둔다. `local-postgres.env`, `local-collector.env`, `local-analysis.env`, `local-host.env`는 각각 DB 관리, Docker 수집기, Docker 읽기, 호스트 작업용이다. `data/raw/` 및 `data/state/`도 Git 제외다. 접속 문자열과 원본 파일은 커밋하지 않는다.

```powershell
docker compose -f compose.local-db.yaml up -d
docker compose -f compose.collector.yaml up -d --build --no-deps yongin-collector
.\.venv\Scripts\python.exe scripts/discover_portal_csv_inventory.py
.\.venv\Scripts\python.exe scripts/collect_discovered_csv.py
.\.venv\Scripts\python.exe scripts/profile_discovered_csv.py
.\.venv\Scripts\python.exe scripts/profile_discovered_zip.py
.\.venv\Scripts\python.exe scripts/publish_discovered_csv.py --local --apply
.\.venv\Scripts\python.exe scripts/profile_large_csv.py
.\.venv\Scripts\python.exe scripts/profile_large_zip.py
.\.venv\Scripts\python.exe scripts/profile_irregular_csv.py
.\.venv\Scripts\python.exe scripts/publish_large_csv_local.py
```

각 적재 명령은 검증 결과와 이전 성공 상태를 확인하며 재실행 시 성공 자료를 건너뛴다. 대용량 적재는 스트리밍 `COPY`와 자료별 트랜잭션으로 처리한다. 실패하면 해당 자료의 현재 레코드를 반영하지 않고 `collection_runs`에 실패를 기록한다. 동일한 내용의 원본 행은 임의로 제거하지 않으며 내용 해시와 출현 순번으로 별도 레코드로 유지한다. 이름이 없는 헤더는 운영 payload에서만 `__unnamed_column_N`으로 표시하고, 완전히 빈 패딩 행은 개수를 기록한 뒤 운영 레코드에서 제외한다. 원본 파일은 변경하지 않는다.

대량 자료는 현재 기준 스냅샷이다. 새 자료의 자동 갱신은 활성화하지 않았다. 정기 갱신을 시작하려면 원본 변경 처리와 스트리밍 재검증 경로를 추가로 검증해야 한다. 두 공식 포털 자료는 다운로드 버튼 대신 외부 링크만 있어 CSV 원본을 확보하지 못했다. 개별 ID와 사유는 `data/state/`의 수집·검증 상태 파일에 있다.

## 확인

```powershell
.\.venv\Scripts\python.exe -m pytest -q
docker ps --filter name=yongin-local-postgres
```

웹은 <http://localhost:8501>, n8n은 <http://localhost:5678/workflow/YNGN02AnalysisV1>에서 확인한다. n8n의 실제 `/webhook/yongin-analysis-v1` 요청은 질문 분석 서비스로 전달하며, 수집기 분석 서비스로 전달하지 않는다.
