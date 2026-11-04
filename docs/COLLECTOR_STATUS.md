# 수집·n8n 구축 상태

기준일: 2026-11-04 (Asia/Seoul)

## 2026-11-04 실제 실행 갱신

- Supabase `001`~`003` 마이그레이션 적용. `analytics.giheung_events` 활성
  781행, 원본 기준일 2026-09-10. 기흥구 이벤트 시작일은 2017~2024년.
- 최초 기준 적재 781행과 동일 CSV 재수집 `no_change` 781행 확인.
  오류 진단 중 실패 실행은 이력에서 삭제하지 않았다.
- `yongin-collector` 컨테이너 건강 상태 정상. n8n 컨테이너에서 내부 DNS
  `yongin-collector:8080` 조회 및 수집 API `no_change` 응답 확인.
- 수집 워크플로 `YNGN01CollectWk1` 등록, 16노드·19연결, 비활성.
  첫 UI 실행은 HTTP 연결 중단 오류였다. 이후 내부 요청은 정상 응답했으나
  n8n 수집 워크플로 전체 수동 실행의 성공 상태는 확인하지 못했다.
- 별도 분석 워크플로 `YNGN02AnalysisV1`은 게시 후 Webhook 실제 호출
  성공. 외부 화면 `http://localhost:8090/ask` → n8n → 분석 서비스 →
  Supabase 경로에서 781건·2024년 105건·월별 합계 105건 검증.
- 시설 API는 키/활용신청 없이 미수집이며 `public_facilities` 비활성.
  `library_new_books`도 운영 DB 적재 전이라 비활성.
- `yongin_analysis_reader`의 `analytics` 읽기 성공, `collector` 스키마
  사용 권한 없음 확인. 별도 로그인 DSN 분리는 아직 미완료.

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
| 데이터 계약 | 작성 완료 | `docs/DATA_CONTRACT.md` v1.1.0 |
| DB 마이그레이션 | 실행 검증 | `001`~`003` Supabase 적용 |
| CSV 수집 | 실행 검증 | 기흥 이벤트 781행, 키 결측·중복 0 |
| API 수집 | 미검증 | 공공데이터 인증키·활용신청 필요 |
| 변경 판별·품질 차단 | 구현·테스트 | 기준 적재·재수집 검증; 대량 삭제는 단위 테스트 |
| Python HTTP 서비스 | 실행 검증 | 수집·분석 별도 컨테이너, 내부 연결 확인 |
| n8n JSON | 실행 검증 | 수집 16노드, 분석 Webhook 4노드 |
| n8n 실제 등록 | 등록 완료 | `YNGN01CollectWk1`, `YNGN02AnalysisV1`; 수집 전체 수동 실행은 미확인 |
| 주간 활성화 | 비활성 | DB·서비스·워크플로 수동 검증 후 활성화 |
| Supabase Storage | 미연결 | 서버용 Storage 자격증명 없음; 로컬 원본 유지 |
| 역할별 로그인 권한 | 일부 검증 | 읽기 전용 그룹 권한 확인; 별도 로그인 DSN은 미설정 |

## 운영 조건

- 기본 스케줄: 매주 월요일 09:00, `Asia/Seoul`.
- 공식 갱신주기가 연간인 자료는 `next_check_at`으로 불필요한 실행을 건너뛴다.
- PC가 종료되거나 절전 상태면 로컬 n8n 예약 작업은 실행되지 않는다.
- 기존 n8n 암호화 키·볼륨·계정·자격증명·수업용 워크플로우는 변경하지 않는다.
- 비밀정보는 `.env` 또는 n8n 자격증명/환경에만 두고 워크플로우 JSON에 넣지
  않는다.

## 소유권

이 저장소가 `collector` 스키마, 마이그레이션, 데이터셋 등록 정보와 수집 변경
판별 규칙을 소유한다. 분석 에이전트는 `analytics` 뷰를 읽으며 공통 스키마를
직접 변경하지 않는다.
