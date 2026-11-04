# 용인 생활여가 수집·분석 데이터 계약

- 계약 버전: `1.2.0`
- 기준일: 2026-11-04 (Asia/Seoul)
- 스키마 소유자: `yongin-public-data-collector`
- 적용 범위: 용인시 생활여가·문화·체육 MVP와 승인된 자동차 등록현황 확장

분석 에이전트는 이 문서와 `migrations/`를 읽어야 하며 `collector` 스키마,
마이그레이션 또는 데이터셋 등록 정보를 임의로 변경하지 않는다. 변경이 필요하면
이 저장소에서 계약 버전과 마이그레이션을 먼저 갱신한다.

## 권한과 스키마

| 역할/스키마 | 용도 | 권한 |
|---|---|---|
| `collector` | 원본 메타데이터, 실행, 현재 레코드, 변경 이력 | 수집 서비스 전용 쓰기 |
| `analytics` | 분석용 현재 데이터 뷰 | 분석 서비스 읽기 전용 |
| `yongin_collector_writer` | 수집 서비스 그룹 역할(NOLOGIN) | `collector` 읽기·쓰기 |
| `yongin_analysis_reader` | 분석 서비스 그룹 역할(NOLOGIN) | `analytics` 읽기 |

두 그룹 역할 자체에는 비밀번호가 없다. 로컬 운영에서는
`scripts/provision_runtime_roles.py`가 `yongin_collector_login`과
`yongin_analysis_login`을 만들고 각 그룹 역할만 부여했다. 비밀정보는 Git에서
제외된 `.runtime/collector.env`, `.runtime/analysis.env`에 각각 저장한다.
Supabase `postgres` 계정은 마이그레이션·역할 프로비저닝에만 사용하며
일상 수집이나 분석 서비스의 런타임 계정으로 사용하지 않는다.

## 테이블

### `collector.datasets`

| 컬럼 | 자료형 | 의미 |
|---|---|---|
| `dataset_id` | `text` PK | 코드와 n8n이 공유하는 안정 ID |
| `display_name` | `text` | 공식 데이터셋명 |
| `domain` | `text` | `생활여가`, `문화`, `체육`, `교통` 중 하나. `교통`은 승인된 별도 확장 |
| `provider` | `text` | 공식 제공기관 |
| `portal_url` | `text` | 사람이 확인하는 소개·상세 페이지 |
| `access_method` | `text` | `file`, `api`, `page` |
| `source_url` | `text` | 실제 파일/API 요청의 기준 URL |
| `update_frequency` | `text` | 공식 갱신 주기 또는 `확인하지 못함` |
| `full_snapshot` | `boolean` | 응답이 전체 스냅샷인지 여부 |
| `active` | `boolean` | n8n 자동 수집 대상 여부 |
| `unique_key_columns` | `text[]` | 안정 고유키 구성 컬럼 |
| `required_columns` | `text[]` | 품질 검사 필수 컬럼 |
| `reference_date_column` | `text` nullable | 공식 데이터 기준일 컬럼 |
| `next_check_at` | `timestamptz` | 다음 확인 예정 시각 |
| `last_success_at` | `timestamptz` nullable | 마지막 정상 갱신 완료 시각 |
| `metadata` | `jsonb` | 공간·시간 단위, 이용 조건 등 부가정보 |

### `collector.collection_runs`

| 컬럼 | 자료형 | 의미 |
|---|---|---|
| `run_id` | `uuid` PK | 실행 ID |
| `dataset_id` | `text` FK | 대상 데이터셋 |
| `trigger_type` | `text` | `manual`, `schedule`, `retry` |
| `status` | `text` | `running`, `success`, `no_change`, `failed`, `blocked` |
| `is_baseline` | `boolean` | 최초 정상 적재 여부 |
| `started_at`, `finished_at` | `timestamptz` | 실행 시작·종료 |
| `collected_at` | `timestamptz` | 원본을 받은 시각 |
| `reference_date` | `date` nullable | 원본의 공식 데이터 기준일 |
| `source_record_count` | `integer` | 검증된 원본 행 수 |
| `baseline_count` | `integer` | 최초 기준 데이터 행 수 |
| `added_count` | `integer` | 이전 정상본에 없던 키 수(최초 적재 제외) |
| `modified_count` | `integer` | 같은 키에서 내용 해시가 바뀐 수 |
| `deleted_candidate_count` | `integer` | 전체 스냅샷에서 사라진 키 수 |
| `unchanged_count` | `integer` | 동일 키·동일 내용 수 |
| `raw_sha256` | `char(64)` nullable | 원본 바이트 SHA-256 |
| `raw_path` | `text` nullable | 로컬 원본 경로 또는 Storage 객체 경로 |
| `quality_summary` | `jsonb` | 중복·결측·대량 삭제 검사 결과 |
| `change_examples` | `jsonb` | n8n 표시용 최대 5개 예시 |
| `error_code`, `error_message` | `text` nullable | 비밀정보를 제거한 실패 분류·설명 |

### `collector.raw_artifacts`

원본 파일/API 응답의 해시, 바이트 수, MIME 형식, 공식 원본명, 로컬 경로,
Supabase 비공개 Storage 버킷·객체 경로를 기록한다. 원본 바이트 자체는 수정하지
않는다. 같은 데이터셋과 SHA-256 조합은 한 번만 등록한다.

### `collector.dataset_records`

| 컬럼 | 자료형 | 의미 |
|---|---|---|
| `dataset_id`, `record_key` | 복합 PK | 데이터셋별 안정 고유키 |
| `payload` | `jsonb` | 정제된 현재 행. 빈 문자열은 `null` |
| `payload_hash` | `char(64)` | 키 정렬 JSON의 SHA-256; 행 순서와 무관 |
| `reference_date` | `date` nullable | 행 또는 스냅샷의 기준일 |
| `active` | `boolean` | 현재 원본 스냅샷에 존재하는지 여부 |
| `first_seen_run_id` | `uuid` | 최초 관측 실행 |
| `last_changed_run_id` | `uuid` | 마지막 내용 변경 실행 |
| `last_seen_run_id` | `uuid` | 마지막 정상 전체 수집 실행 |

`active=false`는 원본에서 사라졌다는 뜻일 뿐 시설 폐업·행사 취소를 의미하지
않는다.

### `collector.change_history`

`run_id`, `dataset_id`, `record_key`, `change_type`, `old_payload`,
`new_payload`, `changed_at`을 저장한다. `change_type`은 `baseline`, `added`,
`modified`, `delete_candidate` 중 하나다. 전체 이력은 DB에 저장하고 n8n에는
건수와 최대 5개 예시만 반환한다.

## 분석용 뷰

- `analytics.current_dataset_records`: 모든 활성 현재 레코드와 데이터셋·출처
- `analytics.giheung_events`: 기흥구 이벤트의 관리번호, 제목, 시작일, 종료일,
  데이터 기준일, 수집 기준 출처
- `analytics.vehicle_registrations`: 자동차 등록현황의 `record_key`, `district`,
  `town`, 용도별 `government_count`, `private_count`, `commercial_count`,
  차종별 `passenger_count`, `van_count`, `truck_count`, `special_count` 정수,
  `reference_date`, `source_url`, `last_success_at`
- `analytics.dataset_sources`: 데이터셋명, 제공기관, 원본 상세 URL, 데이터 기준일,
  최근 정상 수집일과 마지막 정상 갱신일. 분석 응답의 출처 표시용.

분석 서비스는 `analytics`만 읽는다. 응답에는 `dataset_id`, `portal_url`,
`reference_date`, `last_success_at`을 함께 사용해 출처와 최신성을 표시한다.

## 정제·비교 규칙

- 지역: 공식 용인시 자료만 등록한다. 주소 기반 API는 `용인시` 포함 여부를
  수집 단계에서 재검증한다.
- 날짜: 원본 ISO 날짜는 PostgreSQL `date`; 변환 불가능한 값은 품질 실패다.
- 좌표: 원본이 제공할 때만 숫자로 보존한다. 좌표 추정이나 지오코딩은 수집기
  범위가 아니다.
- 결측: 빈 문자열과 공백만 있는 값은 JSON `null`; 필수 컬럼의 결측은 반영을
  차단한다.
- 고유키: 앞뒤 공백을 제거한 키 컬럼을 단위 구분자로 결합한다. 키 결측·중복은
  반영을 차단한다.
- 비교: 키 정렬 JSON 해시를 사용하므로 행 순서 변경은 수정이 아니다.
- 삭제: 전체 스냅샷의 완전성이 확인된 경우만 `delete_candidate`; 폐업·운영 종료로
  해석하지 않는다.
- 대량 삭제: 기존 활성 행의 30%를 초과하고 5건을 넘으면 반영을 차단한다.
- 실패: 이전 정상 `dataset_records`와 `last_success_at`을 유지한다.
- 동시 실행: 데이터셋 ID의 PostgreSQL advisory transaction lock으로 차단한다.
- 트랜잭션: 운영 데이터, 변경 이력, 성공 상태는 같은 트랜잭션에서 반영한다.

## 날짜의 의미

- `reference_date`: 제공기관이 원본에 기록한 데이터 기준일.
- `collected_at`: 수집기가 실제로 원본을 받은 시각.
- `last_success_at`: 품질 검사와 DB 트랜잭션까지 성공한 마지막 시각.
- `started_at`/`finished_at`: 개별 수집 실행의 경계.

## 현재 확보 데이터와 분석 가능 범위

### `giheung_events` — 최초 연동 대상(CSV)

- 공식명: 경기도 용인시_기흥구 이벤트 정보
- 제공기관: 경기도 용인시
- 원본: CSV 781행, 5컬럼
- 기준일: 2026-09-10
- 고유키: `관리번호`(결측 0, 중복 0)
- 필수 컬럼: 관리번호, 제목, 시작일, 종료일, 데이터기준일자
- 지원 분석: 행사 목록, 기간 필터, 기준일 표시
- 확인 불가: 실제 개최·취소 여부, 참여 인원, 운영 상태

### `public_facilities` — 최초 API 대상

- 공식명: 전국공공시설개방정보표준데이터
- 용인 범위: 도로명 또는 지번 주소에 `용인시`가 있는 레코드
- 접근: 공공데이터포털 활용신청·인증키 필요
- 현재 상태: 원본 API 8페이지 확보, 용인시 주소 97건. 운영 DB 적재와
  안정 고유키 검증은 아직 완료되지 않음
- 지원 분석: 운영 DB 품질 검증 후 확정

### 후속 후보

- `vehicle_registrations`: 승인된 교통 확장 CSV 42행을 현재 레코드로 적재.
  고유키는 `시군구`+`읍면동`, 기준일은 CSV 내부의 2026-04-02이다.
  파일명 날짜 2025-12-31과 달라 파일명으로 기준일을 추정하지 않는다.
  숫자 형식과 행별 용도·차종 합계 일치를 검증한다. 최초 적재 42행은
  신규 등록 차량 수가 아니다.
- `library_new_books`: XLSX 원본 확보, 10,312,734바이트. 고유키·결측 검사는
  아직 운영 계약에 포함하지 않음.
- `suji_programs`: 공식 HTML만 확인. CSV 연동 완료가 아님.

## 원본 저장

Supabase 비공개 Storage를 우선 목표로 한다. 현재는 Storage 서버 키가 없으므로
로컬 `data/raw`를 사용한다. 서버 이전 시 이 디렉터리와 `data/state`를 함께
백업하고 SHA-256을 재검증한다. Storage 연결 전에는 로컬 원본을 삭제하지 않는다.

## 변경 이력

- `1.0.0` (2026-11-04): 초기 스키마, 권한 분리, 기흥 이벤트 계약 및
  공공시설 API 미검증 상태 정의.
- `1.1.0` (2026-11-04): 분석 응답의 출처 뷰와 정의된 행사 건수 조회 계약 추가.
  실제 질문·SQL·제한은 `docs/ANALYSIS_SERVICE.md` 참조.
- `1.1.1` (2026-11-04): 런타임 로그인 분리와 비밀정보 파일 경로를 명시.
- `1.2.0` (2026-11-04): 승인된 교통 CSV 확장을 `collector`에 등록하고
  `analytics.vehicle_registrations` 읽기 뷰, 키·기준일·품질 규칙을 추가.
