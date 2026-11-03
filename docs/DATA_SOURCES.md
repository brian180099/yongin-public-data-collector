# 데이터 출처와 원본 전달 계약

기준일: 2026-11-03

공공데이터포털의 용인시 검색 결과 전체가 아니라 아래 MVP 허용 목록만
처리한다. `suji_programs`는 추가 후보이며 기본 실행에서 제외한다.

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
- 서버 측 범위 요청변수: `rdnmadr=경기도 용인시`
- 주요 응답 필드: `openFcltyNm`, `openLcNm`, `openFcltyType`, 운영시간,
  요금·수용인원, `rdnmadr`, `lnmadr`, 관리기관·연락처, 위경도,
  `referenceDate`, 제공기관 코드·명

수집기는 JSON 응답 코드, `totalCount`, 페이지별 건수, 필드 집합,
`referenceDate`, 도로명/지번 주소의 용인시 포함 여부를 검증한다. API 페이지의
원본 바이트를 그대로 저장하며 페이지 수, 총 건수, 필드명과 기준일 목록은
sidecar 메타데이터에 기록한다. `DATA_GO_KR_SERVICE_KEY`가 없거나 활용신청이
완료되지 않은 상태는 실패 이력이며 실수집 완료가 아니다.

### 추가 후보 `suji_programs`

- 포털 안내: <https://www.data.go.kr/data/15136680/fileData.do>
- 공식 페이지: <https://www.sujigu.go.kr/lmth/04life0703.asp>
- 현재 상태: 포털 상세 페이지에 다운로드 후보가 없고 공식 페이지 바로가지만
  있다. 따라서 공식 HTML만 원본으로 저장하고 CSV 수집 완료로 표시하지 않는다.

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
