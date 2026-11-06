# 용인 공공데이터 원본 수집기

> **현재 운영 경로 (2026-11-06):** 이 저장소와 n8n `YNGN01CollectWk1`은
> 공공데이터 원본 수집·검증·적재를 담당한다. 사용자 질문 분석과 웹은 별도
> `LG_AX_개인 프로젝트`의 <http://localhost:8501>에서 수행한다. 옛
> `YNGN02AnalysisV1` Webhook과 `yongin-analysis` 컨테이너는 중지했다.
> 아래의 `localhost:8090` 분석 서비스 설명은 이전 구현 기록이다.

## 검색 CSV 확장 진행 (2026-11-05)

`용인`·`용인시` 포털 파일데이터 검색의 CSV 표시 자료를 재조사했다. 용인시 제공 신규 자료 중 186개 데이터셋 190,068행을 검증 후 DB에 추가했다. 원본·검증 통과 후 대기·보류 내역과 DB 용량에 따른 다음 단계는 [`docs/BULK_CSV_EXPANSION.md`](docs/BULK_CSV_EXPANSION.md)를 참고한다. 대형 파일 전체 적재는 아직 완료하지 않았다.

## CSV 우선 적재 현황 (2026-11-05)

용인시·3개 구 제공 생활여가·문화·체육 파일을 포털 상세 페이지별로 확인해
`csv_allowlist.py`에 60개 ID를 명시했다. 실제 CSV 원본 54건과 ZIP 원본 5건,
ZIP 내부 CSV 11건을 보존했다. 품질 검사를 통과한 57개 데이터셋 71,924행을
Supabase `collector` 스키마에 기준 데이터로 적재했다. 기존 기흥구 이벤트
781행과 승인된 자동차 등록현황 42행도 유지한다. 새 데이터셋은 자동 예약
수집 예약 대상에 포함했다. 채팅에서 자료별 전체 적재 건수와 원본 행 최대 10건을 조회할 수 있다.

깨진 CSV 1건은 실패로 기록했다. 중복 행, 식별키 결함 또는 날짜 형식 오류가
있는 CSV 8건과 ZIP 내부의 고유키 중복 CSV 1건은 원본만 보존했다. 상세 현황은
[`docs/COLLECTOR_STATUS.md`](docs/COLLECTOR_STATUS.md)에 있다. 포털 검색
결과 전체를 자동 수집하지 않으며, 추가 후보는 제공기관·분야·파일 형식과
실제 원본 구조를 검토한 뒤 허용 목록을 확장한다.

```powershell
.\.venv\Scripts\python.exe scripts/register_reviewed_csv.py
.\.venv\Scripts\python.exe scripts/register_reviewed_csv.py --apply
```

## 채팅 분석 서비스 (2026-11-05)

<http://localhost:8090/>의 대화창에서 기흥구 행사 CSV, 용인시 자동차 등록현황
CSV, 용인시 공공시설 API 자료를 질문할 수 있습니다. 행사 건수·월별 추이·목록,
자동차 대수·구별 비교·읍면동 순위·용도/차종 구성, 시설 건수·구별 비교·검색을
사전 정의된 읽기 전용 SQL로 처리합니다. 답변에는 표, 가능한 경우 막대그래프,
공식 출처와 데이터 기준일을 표시합니다. 최근 대화 6개 메시지는 브라우저에서
요청마다 전달하며 서버에 질문 원문을 별도 저장하지 않습니다.

추가된 CSV 57종은 자료명이나 주제를 지정하면 전체 적재 건수 또는 원본 행
최대 10건을 조회합니다. `검색어 '유아 클레이 특강'`처럼 명시한 텍스트로
원본 값 검색도 가능합니다. 자료가 모호하면 후보를 제시하고, 기간·지역 필터나
비교 계산은 검증된 컬럼별 분석 계약이 마련될 때까지 명확히 제한합니다.

분석 컨테이너 전용 비밀 파일 `.runtime/analysis.env`에 `OPENAI_API_KEY`와
`OPENAI_MODEL`을 설정했습니다. OpenAI Responses API는 자유형 CSV 질문을
허용된 데이터셋 ID와 조회 계획으로만 변환합니다. 대표 MVP 질문은 불필요한
모델 왕복 없이 규칙으로 처리합니다. LLM은 SQL을 생성하거나 수집기 인증키에
접근하지 않습니다. 숲체험일정 질문의 구조화 계획과 Supabase 조회를 실제로
검증했습니다. 설정을 바꾼 뒤에는 분석 컨테이너를 재생성하세요.

```powershell
docker compose -f compose.collector.yaml up -d --no-deps --force-recreate yongin-analysis
```

분석 n8n 워크플로는 질문·대화 ID·최근 메시지를 분석 서비스로 전달합니다.
LLM 질문 해석과 DB 조회는 분석 서비스에서 수행합니다. 공공시설 API 키는
수집 컨테이너 전용 `.runtime/collector.env`에만 둡니다.

## 초기 질문·분석 MVP 기록 (2026-11-04)

현재 실제 적재된 기흥구 이벤트 781건에 대해 전체 건수, 연도별 건수,
연도 내 월별 건수를 질문할 수 있습니다. 외부 질문 화면은
<http://localhost:8090/>입니다. 브라우저 요청은 별도 n8n 워크플로
`YONGIN_02_생활여가_질문분석`을 거쳐 미리 정의된 읽기 전용 SQL로 계산됩니다.
질문·계산·출처와 검증 범위는 [`docs/ANALYSIS_SERVICE.md`](docs/ANALYSIS_SERVICE.md)에
기록했습니다. 아래 설명은 초기 기흥구 전용 MVP의 기록이며 현재 채팅 분석
범위는 위의 2026-11-05 항목을 따릅니다.

허용 목록의 CSV 두 종은 운영 DB에 적재돼 있습니다: 기흥구 이벤트 781행,
사용자가 승인한 교통 확장인 자동차 등록현황 42행. 자동차 자료는
`analytics.vehicle_registrations` 읽기 뷰에서도 조회할 수 있습니다.
도서관 신간도서는 XLSX, 수지구 프로그램은 HTML이므로 CSV 적재 대상이
아닙니다. 공공시설 API는 원본 수집과 운영 DB 적재를 검증했습니다.

```powershell
.\.venv\Scripts\python.exe scripts/apply_migrations.py --apply
.\.venv\Scripts\python.exe scripts/provision_runtime_roles.py
docker compose -f compose.collector.yaml up -d --build
```

기존 n8n 2.31.7의 `n8n_default` 네트워크가 필요합니다. 분석 워크플로 편집:
<http://localhost:5678/workflow/YNGN02AnalysisV1>. 수집 워크플로 편집:
<http://localhost:5678/workflow/YNGN01CollectWk1>. 두 워크플로는 별도입니다.
수집과 분석은 `.runtime/`의 별도 PostgreSQL 로그인으로 실행합니다. 이 폴더는
Git과 Docker 이미지·볼륨에서 제외됩니다. 서버 이전 시 `.runtime/`도 별도로
안전하게 백업해야 합니다. 공공시설 API도 운영 DB에 적재됐고 수집 n8n의
활성 대상입니다. 첫 실제 예약 실행은 아직 관찰하지 못했습니다.

API 활용신청이 승인되면 인증키를 로컬 CLI와 Docker 수집 서비스가 함께 읽는
`.runtime/collector.env`의 `DATA_GO_KR_SERVICE_KEY`에 입력하고 수집 컨테이너를
재시작해야 합니다. 분석 컨테이너에는 이 키를 전달하지 않습니다.
공공시설 API의 원본·DB 적재와 재실행은 실제 응답으로 검증했습니다.

승인된 `public_facilities` 활용신청 상세의 키는 로컬 브라우저에서 읽어
`.runtime/collector.env`에 저장할 수 있습니다. 로그인과 신청 확정은 포털에서
직접 수행합니다.

직접 입력도 가능합니다. 포털에서 **디코딩 인증키**를 복사한 뒤 아래 명령에
붙여넣으세요. 입력값은 터미널에 표시되지 않고 명령 기록에도 남지 않습니다.
`.runtime/collector.env`의 다른 DB 설정은 유지됩니다.

```powershell
.\.venv\Scripts\python.exe scripts/configure_public_data_key.py
docker compose -f compose.collector.yaml up -d --no-deps --force-recreate yongin-collector
```

n8n 워크플로 `YONGIN_01_공공데이터_수집갱신`에는 키를 넣지 않습니다. n8n은
`http://yongin-collector:8080`의 수집 서비스를 호출하고, 이 서비스만 로컬
비밀 파일에서 키를 읽습니다. 포털 인증키를 여러 API에 재사용할 수 있어도
**각 API의 활용신청 승인과 실제 응답 검증은 별개**입니다. 공공시설 API는
공공시설은 원본·DB 검증 후 자동 수집 대상으로 활성화했습니다.

```powershell
.\.venv\Scripts\python.exe -m pip install -e ".[portal]"
.\.venv\Scripts\python.exe scripts/sync_portal_application.py --source public_facilities
```

스크립트가 새 Chrome 창을 열면 **로그인만 직접 완료**하세요. 이후 승인 목록에서
`전국공공시설개방정보표준데이터`를 찾아 상세 화면으로 이동하고, 데이터명·승인
상태·End Point·인증키를 검사합니다. 후보 키로 API 응답을 먼저 확인한 뒤
`.runtime/collector.env`에 저장합니다. 다른 API나 호출 실패 시 기존 키를
유지합니다. 키·쿠키는 출력하거나 n8n에 넣지 않습니다. 결과 상태는 Git에서
제외된 `.runtime/portal_application_status.json`에 기록합니다. 저장 후에는
위의 `docker compose ... --force-recreate` 명령으로 수집 컨테이너를 다시 만들어
새 키를 적용합니다. 실제 로그인 화면 흐름은 아직 실행 검증하지 않았습니다.

기존 [`yongin-public-data-ai`](https://github.com/brian180099/yongin-public-data-ai)의 독립 수집 프로젝트입니다. 용인시 생활여가·문화·체육 MVP 대상만 수집합니다. [공공데이터포털 용인시 검색 결과](https://www.data.go.kr/tcs/dss/selectDataSetList.do?keyword=%EC%9A%A9%EC%9D%B8%EC%8B%9C&conditionType=search&org=&orgFilter=&orgFullName=)의 전체 351건은 수집 대상이 아닙니다.

기본 실행 대상은 명시적으로 허용한 다섯 소스입니다. 검색 결과 전체를
수집하지 않으며, 자동차 등록현황은 사용자가 승인한 교통 데이터 확장입니다.

| ID | 출처 | 방식 | 상태 |
|---|---|---|---|
| `giheung_events` | [기흥구 이벤트 정보](https://www.data.go.kr/data/15136583/fileData.do) | 포털 공식 CSV 다운로드 | 실행 검증 |
| `library_new_books` | [용인시 도서관 신간도서](https://www.data.go.kr/data/3038399/fileData.do) | 포털의 공식 XLSX 다운로드 요청 | 실행 검증 |
| `public_facilities` | [공공시설개방정보](https://www.data.go.kr/data/15013117/standard.do) | 인증키가 필요한 Open API JSON | 원본 8페이지·운영 DB 용인시 97건 적재, n8n 수동 경로 검증 |
| `vehicle_registrations` | [자동차 등록현황](https://www.data.go.kr/data/3035912/fileData.do) | 포털 공식 CSV 다운로드 | DB 42행 적재·재실행 검증 |
| `vehicle_registrations_api` | [자동차 등록현황 Open API](https://www.data.go.kr/data/3035912/fileData.do) | 활용신청 후 ODCLOUD JSON | 승인 키 필요 |

자동차 Open API 활용신청 보조 브라우저는 신청 폼과 별도의 공공데이터포털
계정 탭을 열어 대기 중 60초마다 새로고침한다. 폼 입력값은 유지하며 포털이
강제로 로그아웃하거나 CAPTCHA를 다시 요청하면 자동 제출하지 않고 중단한다.

```powershell
.\scripts\run_vehicle_api_selenium.ps1
```

기본 간격은 60초다. 직접 실행할 때만 `--keepalive-seconds`로 바꿀 수 있으며
포털 과부하를 막기 위해 30초 미만은 허용하지 않는다.

창 없이 세션 유지 기능을 실행하려면 먼저 위 명령으로 화면 표시 모드에서
CAPTCHA 로그인을 완료하고 Chrome을 정상 종료한 다음 아래 명령을 실행한다.

```powershell
.\scripts\run_vehicle_api_selenium.ps1 -Headless
```

headless 실행 중에는 CAPTCHA를 입력할 수 없다. 저장된 포털 세션이 없거나
만료되었으면 `HEADLESS_LOGIN_REQUIRED`로 종료하므로 화면 표시 모드에서 다시
로그인해야 한다. 동일한 Selenium 프로필을 동시에 두 Chrome 프로세스에서 열 수
없으므로 화면 표시 Chrome을 닫은 뒤 headless 모드를 시작한다.

추가 후보 `suji_programs`는 `--source suji_programs`로 실행할 수 있습니다. 현재 포털에서 CSV 파일 버튼 대신 기관 페이지 바로가기를 제공하므로 HTML 원본으로 저장하며 CSV라고 표시하지 않습니다. 기존 분석 프로젝트의 데이터셋 목록과 수집기의 MVP 기본 목록은 아직 다릅니다. 최종 3종을 확정할 때 두 저장소의 목록을 맞춰야 합니다.

현재 차이와 상세 파일 식별자, 요청변수, 갱신일 및 저장 규격은
[`docs/DATA_SOURCES.md`](docs/DATA_SOURCES.md)에 기록합니다. 분석 저장소의
선정 목록은 `suji_programs`, `public_facilities`, `city_parks`이고 이 저장소와
공통인 항목은 `public_facilities` 하나입니다.

## 실행

PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
Copy-Item .env.example .env
python -m yongin_collector backfill
python -m yongin_collector daily
python -m yongin_collector status
pytest
```

`.runtime/collector.env`에 공공데이터포털의 Decoding 인증키를 넣고 해당 API의 활용신청을 완료해야 `public_facilities` 실호출을 검증할 수 있습니다. 키를 Git에 커밋하거나 로그에 출력하지 마세요. 키가 없으면 파일과 웹페이지 수집은 계속하고 API 실패를 기록하며 명령은 종료 코드 1을 반환합니다.

단일 소스 실행:

```powershell
python -m yongin_collector backfill --source library_new_books
python -m yongin_collector daily --source public_facilities
python -m yongin_collector backfill --source vehicle_registrations
python -m yongin_collector apply --source vehicle_registrations_api --open
python -m yongin_collector daily --source vehicle_registrations_api
```

`apply`는 공공데이터포털 상세 페이지를 열며, **오픈 API → 활용신청**을
선택할 수 있습니다. 로그인, 서비스키 선택과 약관 확인은 사용자가 직접
완료해야 하며 수집기는 신청 완료를 가장하지
않습니다. 승인 후 Decoding 인증키를 로컬 `.env`의
`DATA_GO_KR_SERVICE_KEY`에 설정하면 API 원본을 수집합니다. API 주소는 현재
파일 UDDI와 공식 Swagger 문서를 매 실행마다 대조해 갱신합니다.

`backfill`은 등록된 원본 파일을 확인하고 처음 한 번 저장합니다. `daily`는 파일을 다시 받아 해시를 비교하고, 새 파일 또는 내용이 달라진 파일만 저장합니다. 포털이 변경 시각이나 ETag를 안정적으로 제공하지 않아 다운로드 트래픽은 매일 발생합니다. 파일 개수 상한은 현재 데이터셋당 20개입니다.

## 저장 규격

`data/raw/<source_id>/`에 원본 바이트를 SHA-256 파일명으로 보존하고 옆에 `*.metadata.json`을 둡니다. `data/state/<source_id>.json`은 마지막 확인, 현재 정상 파일별 해시, 성공·실패 실행 이력을 기록합니다. 수집일(`collected_at`)과 데이터 기준일(`reference_date`)은 별도 필드입니다. 파일명에서 기준일을 추론할 수 없으면 `null`입니다. API 메타데이터에는 HTTP 상태, 페이지·전체 건수, 필드 구조와 기준일 목록도 기록합니다. 파일과 이력은 Git에서 제외됩니다.

현재 운영 경로에서는 품질 검사를 통과한 기흥구 CSV의 정제·변경 비교와
`collector` 스키마 반영을 Python 수집 서비스가 수행합니다. 분석 서비스는
`analytics` 뷰를 읽습니다. 원본은 로컬 `data/raw` 볼륨에 보존합니다.
서버 이전 시 `data/`와 n8n의 기존 볼륨·암호화 키를 함께 백업해야 합니다.
저장 규격과 권한은 `docs/DATA_CONTRACT.md`를 따릅니다.

## n8n

`workflows/n8n/daily-collector.json`은 예전 self-hosted Linux n8n용
가져오기 템플릿입니다. 현재 로컬 n8n에는 별도의
`workflows/n8n/yongin-weekly-collector.json`과
`workflows/n8n/yongin-analysis-v1.json`을 등록했습니다.
예전 템플릿을 현재 인스턴스에 중복 등록하지 마세요. 분석 워크플로는
Webhook으로 실행 검증했고, 수집 워크플로는 전체 수동 실행에서 781건
`no_change`를 확인한 뒤 매주 월요일 09:00(Asia/Seoul)으로 게시했습니다.

self-hosted n8n에서는 저장소와 가상환경을 준비한 뒤 UI의 **Import from
File**로 템플릿을 가져오거나 지원되는 버전에서 아래처럼 가져옵니다.

```bash
n8n import:workflow --input=workflows/n8n/daily-collector.json
```

가져온 후 비활성 상태에서 Execute Command 노드를 수동 실행해 종료 코드와
실패 출력을 확인하고, 성공한 뒤에만 워크플로를 활성화합니다. 인증키는 n8n
JSON에 넣지 않고 실행 계정이 읽을 수 있는 저장소의 로컬 `.env`로만 제공합니다.
