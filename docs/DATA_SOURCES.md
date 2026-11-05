# 데이터 출처와 원본 전달 계약

2026-11-05 추가: 용인시·3개 구의 생활여가·문화·체육 CSV 확대 목록은
`src/yongin_collector/csv_allowlist.py`가 소유한다. 60개 ID 중 직접 CSV 54건과
ZIP 원본 5건을 보존하고 57개 데이터셋 71,924행을 DB에 적재했다. 실패·보류 원인은
`docs/COLLECTOR_STATUS.md`의 최신 항목에 기록한다. 아래 내용은 이전
소수 MVP 출처의 상세 기록이다.

기준일: 2026-11-03

공공데이터포털의 용인시 검색 결과 전체가 아니라 아래 명시적 허용 목록만
처리한다. 자동차 등록현황은 사용자가 승인한 교통 데이터 확장이고,
`suji_programs`는 추가 후보이며 기본 실행에서 제외한다.

## 현재 출처

### `giheung_events`

- 상세 페이지: <https://www.data.go.kr/data/15136583/fileData.do>
- 포털 ID: `15136583`
- 현재 파일 상세 ID: `uddi:96d2ce59-52f8-4a16-b507-d047ca388a20`
- 파일 번호/이력 번호: `1` / `1`
- 다운로드 방식: 상세 페이지의 `fn_fileDataDown` 인자를 읽고
  `selectFileDataDownload.do` 승인 확인, `check-limit.json` CAPTCHA 확인 후
  `fileDownload.do`에서 원본을 받는다.
- 현재 원본명: `경기도 용인시_기흥구 이벤트 정보_20260910.csv`
- 등록일/수정일: 2026-09-10 / 2026-09-14
- 데이터 기준일: 파일명 기준 2026-09-10
- 갱신주기: 연간

### `library_new_books`

- 상세 페이지: <https://www.data.go.kr/data/3038399/fileData.do>
- 포털 ID: `3038399`
- 현재 파일 상세 ID: `uddi:23606e4f-8447-4243-bd69-93a555ef51fe`
- 파일 번호/이력 번호: `1` / `1`
- 다운로드 방식: `giheung_events`와 같은 포털 공식 다운로드 요청을 사용한다.
- 현재 원본명: `경기도 용인시_도서관 신간도서 정보_20260510.xlsx`
- 등록일/수정일: 2026-05-11 / 2026-09-15
- 데이터 기준일: 파일명 기준 2026-05-10
- 갱신주기: 반기

파일 상세 ID와 파일 번호가 같아도 `daily`는 원본을 다시 내려받는다. 응답이
비어 있거나, 확장자 서명과 맞지 않거나, CSV 대신 HTML이 오거나, CAPTCHA가
요구되면 해당 실행은 실패한다. 모든 후보가 검증된 다음에만 manifest를 한 번에
갱신하고 SHA-256이 같은 원본은 다시 저장하지 않는다.

### `public_facilities`

- 상세 페이지: <https://www.data.go.kr/data/15013117/standard.do>
- 요청 주소: <https://api.data.go.kr/openapi/tn_pubr_public_pblfclt_opn_info_api>
- 포털 ID: `15013117`
- 수정일/갱신주기: 2026-09-10 / 분기
- 공통 요청변수: `serviceKey`, `pageNo`, `numOfRows`, `type`
- 서버 측 `rdnmadr` 조건은 `경기도 용인시` 부분 검색으로 동작하지 않았다
  (응답 코드 `03`). 전체 8페이지를 확인한 후 `rdnmadr` 또는 `lnmadr`에
  `용인시`가 포함된 항목만 로컬에서 선별한다.
- 주요 응답 필드: `openFcltyNm`, `openLcNm`, `openFcltyType`, 운영시간,
  요금·수용인원, `rdnmadr`, `lnmadr`, 관리기관·연락처, 위경도,
  `referenceDate`, 제공기관 코드·명

2026-11-04 실호출에서 전체 7,333건 중 용인시 주소 97건을 확인했다.
이 97건의 응답 `referenceDate` 최신값은 2026-09-30이며 수집일과 구분한다.
API 응답은 최상위 `header`·`body` 구조이며 `items.item`에 행이 담긴다.
수집기는 응답 코드, 전체 페이지 수·건수, 필드 집합, 용인시 주소와
`referenceDate`를 검증한다. 서버가 도시 부분 검색을 지원하지 않아
전국 응답 8페이지를 **원본 바이트 그대로** 로컬에 보존하고, 페이지별
용인시 건수를 sidecar 메타데이터에 구분해 기록한다. 운영 DB에는 아직
`collector.dataset_records`에 적재했고 `analytics.public_facilities` 읽기
뷰에서 97건을 확인했다. 질문 분석 서비스의 시설 의도에는 아직 연결하지 않았다.

### 추가 후보 `suji_programs`

- 포털 안내: <https://www.data.go.kr/data/15136680/fileData.do>
- 공식 페이지: <https://www.sujigu.go.kr/lmth/04life0703.asp>
- 현재 상태: 포털 상세 페이지에 다운로드 후보가 없고 공식 페이지 바로가지만
  있다. 따라서 공식 HTML만 원본으로 저장하고 CSV 수집 완료로 표시하지 않는다.

### `vehicle_registrations` / `vehicle_registrations_api`

- 상세 페이지: <https://www.data.go.kr/data/3035912/fileData.do>
- 포털 ID: `3035912`
- 현재 파일 상세 ID: `uddi:2310ae65-f196-4e39-8235-906b9bb69cb7`
- 현재 원본명: `경기도 용인시_자동차 등록현황_20251231.csv`
- 현재 원본: 2,999바이트, UTF-8 CSV, 42행, 10컬럼
- 파일명 날짜: 2025-12-31. 실제 CSV `데이터기준일자`: 2026-04-02
- 등록일/수정일: 2026-04-02 / 2026-09-22
- 갱신주기: 연간
- API OAS: <https://infuser.odcloud.kr/oas/docs?namespace=3035912/v1>

CSV는 다른 포털 파일과 같은 공식 다운로드 절차와 SHA-256 변경 판정을
사용한다. API는 `python -m yongin_collector apply --source
vehicle_registrations_api --open`으로 상세 페이지를 연 뒤 **오픈 API →
활용신청**을 선택한다. 로그인과 신청 확정은 사용자가 수행한다. 승인 후
수집기는 현재 파일 UDDI를 OAS와 대조하고
ODCLOUD API를 페이지 단위로 호출한다. 인증키는 URL이 아닌 `Authorization`
헤더로 전달하며 원본·메타데이터·오류 기록에 남기지 않는다.

CSV 42행의 고유키는 `시군구`·`읍면동` 조합이며 중복·결측이 없다.
7개 차량 수량 컬럼은 모두 음수가 아닌 정수이고, 각 행에서 용도별 합계와
차종별 합계가 일치한다. 현재 레코드 42행을 `collector.dataset_records`에
적재했으며 읽기 뷰는 `analytics.vehicle_registrations`이다. 최초 적재는
기준 데이터이고 신규 등록 차량 수를 뜻하지 않는다.

## 기존 분석 저장소와의 차이

분석 저장소 `yongin-public-data-ai`의 main
(`edc7fb3ff6f5c96edea7b54136439774f8e5612a`)은 `suji_programs`,
`public_facilities`, `city_parks` 세 종을 선정한다. 이 수집 저장소의 기본 세
종은 `giheung_events`, `library_new_books`, `public_facilities`이다. 공통 항목은
`public_facilities` 하나뿐이다. 최종 세 종이 확정될 때까지 분석 저장소의
목록이나 코드를 임의로 바꾸지 않는다.

## 원본·메타데이터·실행 이력 규격

```text
data/
  raw/<source_id>/<sha256>.<확장자>
  raw/<source_id>/<sha256>.metadata.json
  state/<source_id>.json
```

- 원본 파일명은 내용 SHA-256으로 정하며 응답 바이트를 변환하지 않는다.
- sidecar에는 출처 URL, 원본 파일명, 수집시각, 데이터 기준일, Content-Type,
  HTTP 상태, 바이트 수, SHA-256과 출처 fingerprint를 기록한다.
- API sidecar에는 페이지 번호, 페이지/전체 건수, 필드명과 기준일 목록을 더한다.
- state manifest는 현재 정상 item과 성공/실패 점검 이력을 보관한다. 실패 시 기존
  item을 교체하지 않고 인증키나 인증 오류 원문을 기록하지 않는다.
- `data/raw`와 `data/state`, `.env`는 Git 대상이 아니다.

분석 서비스와 공유할 운영 저장 경로는 아직 정해지지 않았다. 운영 전에는
수집기 호스트의 `data/`를 지속 볼륨에 두고, 분석 서비스가 같은 볼륨을 최소
읽기 전용으로 마운트할 경로·권한·보존 정책을 정해야 한다. 분석 측은 sidecar와
manifest를 통해 정상 원본만 선택해야 하며, 수집기는 통계 계산이나 운영 DB
적재를 하지 않는다.
