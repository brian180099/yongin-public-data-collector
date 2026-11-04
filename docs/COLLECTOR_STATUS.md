# 수집·n8n 구축 상태

기준일: 2026-11-04 (Asia/Seoul)

## 2026-11-04 추가 검증 및 활성화

- n8n 2.31.7 공식 CLI를 별도 내부 Task Broker 포트로 실행해 수집 워크플로
  전체 경로를 검증했다. 마지막 `전체 결과 취합`은 `success`, 대상 1개,
  기흥구 이벤트 `no_change` 781건, 실패 0건이었다.
- `YNGN01CollectWk1`을 게시하고 기존 n8n을 재시작한 뒤 `active=true`,
  `Asia/Seoul`, 매주 월요일 09:00 설정을 내보내기 결과로 재확인했다.
  다음 실제 월요일 예약 실행은 아직 관찰하지 못했다. 연간 자료의 현재
  `next_check_at` 때문에 이번 주간 조회 대상은 0개다.
- `yongin_collector_login`과 `yongin_analysis_login`을 별도 생성해 실제
  DB 접속·스키마 권한을 검증했다. 컨테이너는 각 전용 DSN만 받고
  `.runtime/` 비밀정보 파일은 볼륨으로 마운트하지 않는다.
- 공공시설 API 키·활용신청, LLM 키는 현재 로컬 환경에 없다. API 실수집과
  LLM 분류를 완료로 표시하지 않는다.

## 2026-11-04 실제 실행 갱신

- Supabase `001`~`003` 마이그레이션 적용. `analytics.giheung_events` 활성
  781행, 원본 기준일 2026-09-10. 기흥구 이벤트 시작일은 2017~2024년.
- 최초 기준 적재 781행과 동일 CSV 재수집 `no_change` 781행 확인.
  오류 진단 중 실패 실행은 이력에서 삭제하지 않았다.
- `yongin-collector` 컨테이너 건강 상태 정상. n8n 컨테이너에서 내부 DNS
  `yongin-collector:8080` 조회 및 수집 API `no_change` 응답 확인.
- 수집 워크플로 `YNGN01CollectWk1` 등록, 16노드·19연결.
  첫 UI 실행은 HTTP 연결 중단 오류였다. 이후 별도 Task Broker 포트로
  전체 수동 실행을 성공 검증하고 주간 스케줄을 게시했다.
- 별도 분석 워크플로 `YNGN02AnalysisV1`은 게시 후 Webhook 실제 호출
  성공. 외부 화면 `http://localhost:8090/ask` → n8n → 분석 서비스 →
  Supabase 경로에서 781건·2024년 105건·월별 합계 105건 검증.
- 시설 API는 키/활용신청 없이 미수집이며 `public_facilities` 비활성.
  `library_new_books`도 운영 DB 적재 전이라 비활성.
- `yongin_analysis_reader`의 `analytics` 읽기 성공, `collector` 스키마
  사용 권한 없음 확인. 이후 전용 로그인 DSN을 만들고 컨테이너를 분리했다.

## 환경 확인

- 저장소: `main`, origin과 동기화된 상태에서 작업 시작
- starter: `yongin-n8n-starter` 없음
- 기존 n8n: 재사용
  - URL: <http://localhost:5678>
  - 버전: `2.31.7`
  - 컨테이너: `n8n`, `n8n-runners`
  - Compose: `C:\n8n\compose.yaml`
  - 네트워크: `n8n_default`
  - DB: SQLite
  - 데이터 볼륨: `n8n_n8n_new_data`
- 기존 워크플로우: 8개 확인. 수정하지 않음.
- n8n Public API 키: 미설정
- 공식 CLI: `import:workflow`, `export:workflow`, `list:workflow` 지원 확인
- Supabase PostgreSQL: 인증·읽기 전용 조회 성공, PostgreSQL 17

## 단계별 상태

| 단계 | 상태 | 근거/남은 작업 |
|---|---|---|
| 환경 조사 | 실행 검증 | Docker, n8n 버전·볼륨·네트워크·CLI 확인 |
| 데이터 계약 | 작성 완료 | `docs/DATA_CONTRACT.md` v1.1.1 |
| DB 마이그레이션 | 실행 검증 | `001`~`003` Supabase 적용 |
| CSV 수집 | 실행 검증 | 기흥 이벤트 781행, 키 결측·중복 0 |
| API 수집 | 미검증 | 공공데이터 인증키·활용신청 필요 |
| 변경 판별·품질 차단 | 구현·테스트 | 기준 적재·재수집 검증; 대량 삭제는 단위 테스트 |
| Python HTTP 서비스 | 실행 검증 | 수집·분석 별도 컨테이너, 내부 연결 확인 |
| n8n JSON | 실행 검증 | 수집 16노드, 분석 Webhook 4노드 |
| n8n 실제 등록 | 실행 검증 | `YNGN01CollectWk1` 전체 수동 실행, `YNGN02AnalysisV1` Webhook 호출 |
| 주간 활성화 | 게시됨 | 월요일 09:00 Asia/Seoul; 첫 실제 예약 실행은 미관찰 |
| Supabase Storage | 미연결 | 서버용 Storage 자격증명 없음; 로컬 원본 유지 |
| 역할별 로그인 권한 | 실행 검증 | 별도 writer/reader 로그인과 컨테이너 환경 분리 확인 |

## 운영 조건

- 기본 스케줄: 매주 월요일 09:00, `Asia/Seoul`.
- 공식 갱신주기가 연간인 자료는 `next_check_at`으로 불필요한 실행을 건너뛴다.
- PC가 종료되거나 절전 상태면 로컬 n8n 예약 작업은 실행되지 않는다.
- 기존 n8n 암호화 키·볼륨·계정·자격증명·수업용 워크플로우는 변경하지 않는다.
- 비밀정보는 로컬 `.env`·`.runtime/` 또는 n8n 자격증명/환경에만 두고 워크플로우 JSON에 넣지
  않는다.

## 소유권

이 저장소가 `collector` 스키마, 마이그레이션, 데이터셋 등록 정보와 수집 변경
판별 규칙을 소유한다. 분석 에이전트는 `analytics` 뷰를 읽으며 공통 스키마를
직접 변경하지 않는다.
