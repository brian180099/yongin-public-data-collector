# 용인 공공데이터 원본 수집기

기존 [`yongin-public-data-ai`](https://github.com/brian180099/yongin-public-data-ai)의 독립 수집 프로젝트입니다. 용인시 생활여가·문화·체육 MVP 대상만 수집합니다. [공공데이터포털 용인시 검색 결과](https://www.data.go.kr/tcs/dss/selectDataSetList.do?keyword=%EC%9A%A9%EC%9D%B8%EC%8B%9C&conditionType=search&org=&orgFilter=&orgFullName=)의 전체 351건은 수집 대상이 아닙니다.

기본 MVP 대상은 세 소스입니다.

| ID | 출처 | 방식 | 상태 |
|---|---|---|---|
| `giheung_events` | [기흥구 이벤트 정보](https://www.data.go.kr/data/15136583/fileData.do) | 포털 공식 CSV 다운로드 | 실행 검증 |
| `library_new_books` | [용인시 도서관 신간도서](https://www.data.go.kr/data/3038399/fileData.do) | 포털의 공식 XLSX 다운로드 요청 | 실행 검증 |
| `public_facilities` | [공공시설개방정보](https://www.data.go.kr/data/15013117/standard.do) | 인증키가 필요한 Open API JSON | 키 없어 실호출 미검증 |

추가 후보 `suji_programs`는 `--source suji_programs`로 실행할 수 있습니다. 현재 포털에서 CSV 파일 버튼 대신 기관 페이지 바로가기를 제공하므로 HTML 원본으로 저장하며 CSV라고 표시하지 않습니다. 기존 분석 프로젝트의 데이터셋 목록과 수집기의 MVP 기본 목록은 아직 다릅니다. 최종 3종을 확정할 때 두 저장소의 목록을 맞춰야 합니다.

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
```

`backfill`은 등록된 원본 파일을 확인하고 처음 한 번 저장합니다. `daily`는 파일을 다시 받아 해시를 비교하고, 새 파일 또는 내용이 달라진 파일만 저장합니다. 포털이 변경 시각이나 ETag를 안정적으로 제공하지 않아 다운로드 트래픽은 매일 발생합니다. 파일 개수 상한은 현재 데이터셋당 20개입니다.

## 저장 규격

`data/raw/<source_id>/`에 원본 바이트를 SHA-256 파일명으로 보존하고 옆에 `*.metadata.json`을 둡니다. `data/state/<source_id>.json`은 마지막 확인과 파일별 해시·실패 원인을 기록합니다. 수집일(`collected_at`)과 데이터 기준일(`reference_date`)은 별도 필드입니다. 파일명에서 기준일을 추론할 수 없으면 `null`입니다. 파일과 이력은 Git에서 제외됩니다.

정제와 Supabase 적재는 분석 서비스의 책임입니다. 두 프로젝트는 원본 폴더와 메타데이터 규격을 통해 연결합니다. 실제 운영에서는 두 환경이 접근할 수 있는 저장소를 별도로 정해야 합니다.

## n8n

`workflows/n8n/daily-collector.json`은 self-hosted Linux n8n용 가져오기 템플릿입니다. `/opt/yongin-public-data-collector` 경로에 이 저장소와 Python 가상환경이 존재하도록 배치한 다음, n8n에서 워크플로를 가져와 실행 경로와 일정을 확인하세요. n8n Cloud에서는 Execute Command 노드가 제공되지 않을 수 있으므로 별도 실행 서버가 필요합니다. 실제 n8n 계정 연결·스케줄 실행은 아직 검증하지 않았습니다.
