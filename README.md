# 용인 공공데이터 원본 수집기

## 질문·분석 MVP (2026-11-04)

현재 실제 적재된 기흥구 이벤트 781건에 대해 전체 건수, 연도별 건수,
연도 내 월별 건수를 질문할 수 있습니다. 외부 질문 화면은
<http://localhost:8090/>입니다. 브라우저 요청은 별도 n8n 워크플로
`YONGIN_02_생활여가_질문분석`을 거쳐 미리 정의된 읽기 전용 SQL로 계산됩니다.
질문·계산·출처와 검증 범위는 [`docs/ANALYSIS_SERVICE.md`](docs/ANALYSIS_SERVICE.md)에
기록했습니다. 공공시설 API와 다른 구 자료는 아직 적재되지 않아 시설 검색과
구별 비교를 지원하지 않습니다. LLM 연결은 아직 없으며 현재 의도 분류는
규칙 기반입니다.

```powershell
.\.venv\Scripts\python.exe scripts/apply_migrations.py --apply
docker compose -f compose.collector.yaml up -d --build
```

기존 n8n 2.31.7의 `n8n_default` 네트워크가 필요합니다. 분석 워크플로 편집:
<http://localhost:5678/workflow/YNGN02AnalysisV1>. 수집 워크플로 편집:
<http://localhost:5678/workflow/YNGN01CollectWk1>. 두 워크플로는 별도입니다.
현재 인증키 없는 공공시설 API와 전용 분석 로그인 분리는 남은 운영 작업입니다.

기존 [`yongin-public-data-ai`](https://github.com/brian180099/yongin-public-data-ai)의 독립 수집 프로젝트입니다. 용인시 생활여가·문화·체육 MVP 대상만 수집합니다. [공공데이터포털 용인시 검색 결과](https://www.data.go.kr/tcs/dss/selectDataSetList.do?keyword=%EC%9A%A9%EC%9D%B8%EC%8B%9C&conditionType=search&org=&orgFilter=&orgFullName=)의 전체 351건은 수집 대상이 아닙니다.

기본 실행 대상은 명시적으로 허용한 다섯 소스입니다. 검색 결과 전체를
수집하지 않으며, 자동차 등록현황은 사용자가 승인한 교통 데이터 확장입니다.

| ID | 출처 | 방식 | 상태 |
|---|---|---|---|
| `giheung_events` | [기흥구 이벤트 정보](https://www.data.go.kr/data/15136583/fileData.do) | 포털 공식 CSV 다운로드 | 실행 검증 |
| `library_new_books` | [용인시 도서관 신간도서](https://www.data.go.kr/data/3038399/fileData.do) | 포털의 공식 XLSX 다운로드 요청 | 실행 검증 |
| `public_facilities` | [공공시설개방정보](https://www.data.go.kr/data/15013117/standard.do) | 인증키가 필요한 Open API JSON | 키 없어 실호출 미검증 |
| `vehicle_registrations` | [자동차 등록현황](https://www.data.go.kr/data/3035912/fileData.do) | 포털 공식 CSV 다운로드 | 실행 검증 |
| `vehicle_registrations_api` | [자동차 등록현황 Open API](https://www.data.go.kr/data/3035912/fileData.do) | 활용신청 후 ODCLOUD JSON | 승인 키 필요 |

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

`.env`에 공공데이터포털의 Decoding 인증키를 넣고 해당 API의 활용신청을 완료해야 `public_facilities`가 실행됩니다. 키를 Git에 커밋하거나 로그에 출력하지 마세요. 키가 없으면 파일과 웹페이지 수집은 계속하고 API 실패를 기록하며 명령은 종료 코드 1을 반환합니다.

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
Webhook으로 실행 검증했으며, 수집 워크플로의 예약 실행은 비활성 상태입니다.

self-hosted n8n에서는 저장소와 가상환경을 준비한 뒤 UI의 **Import from
File**로 템플릿을 가져오거나 지원되는 버전에서 아래처럼 가져옵니다.

```bash
n8n import:workflow --input=workflows/n8n/daily-collector.json
```

가져온 후 비활성 상태에서 Execute Command 노드를 수동 실행해 종료 코드와
실패 출력을 확인하고, 성공한 뒤에만 워크플로를 활성화합니다. 인증키는 n8n
JSON에 넣지 않고 실행 계정이 읽을 수 있는 저장소의 로컬 `.env`로만 제공합니다.
