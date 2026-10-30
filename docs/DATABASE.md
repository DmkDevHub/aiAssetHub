# DATABASE — SQLite v0.5 데이터 설계

## 기본 정책
- 운영 DB: Windows 사용자별 **AppData** 하위 전용 디렉터리. 개발 DB와 별도.
- `db/migrations/`에 버전별 스키마 변경 기록, 마이그레이션 전에 백업.
- `PRAGMA foreign_keys=ON`; WAL(Write-Ahead Logging, 선기록 로그) 적용 여부를 설치본에서 실제 검증하고 잠금·busy timeout 설정.
- 사용자 에셋 원본은 DB로 복사하지 않음. 경로·메타데이터·태그·분석 결과만 보유.
- 마이그레이션/DB 쓰기는 Python Core 한 프로세스가 전담. MCP Bridge는 직접 DB 열기/쓰기 금지.

## 논리 테이블 (구현 시 마이그레이션으로 확정)
| 테이블 | 주요 필드 | 의미 |
|---|---|---|
| `schema_migrations` | version, applied_at | 마이그레이션 이력 |
| `library_roots` | id, display_name, absolute_path, created_at, enabled | 등록된 사용자 폴더 |
| `assets` | id, library_root_id, display_name, category, created_at, updated_at | 논리 에셋 |
| `asset_files` | id, asset_id, relative_path, absolute_path, extension, size_bytes, mtime_ns, sha256?, exists_flag | 물리 파일 |
| `asset_observations` | asset_file_id, width?, height?, duration_ms?, metadata_json, scanned_at | 기본 메타데이터 |
| `tags` | id, label, normalized_label | 사용자/AI 태그 사전 |
| `asset_tags` | asset_id, tag_id, source(user/ai), analysis_result_id? | 출처 구분된 태그 |
| `asset_user_annotations` | asset_id, title_override?, description_override?, updated_at | 사용자 보정 우선 보존 |
| `model_providers` | id, name, kind(local/external) | 공급자 정보 |
| `model_registry` | id, provider_id, model_id, modalities_json, capabilities_json, cost_json?, enabled | 모델 카탈로그 |
| `analysis_jobs` | id, scope_json, model_snapshot_json, requested_count, status, created_at, started_at?, ended_at?, initiated_by, cost_limit? | 사용자 승인 작업 |
| `analysis_job_items` | job_id, asset_id, status, attempts, error_code?, started_at?, ended_at? | 에셋 단위 실행 상태 |
| `analysis_runs` | id, job_id, asset_id, model_snapshot_json, input_fingerprint, status, usage_json?, error_json?, created_at | 각 분석 시도 |
| `analysis_results` | id, run_id, asset_id, description, category, tags_json, features_json, confidence?, created_at | 성공 결과의 불변 스냅샷 |
| `asset_active_results` | asset_id, analysis_result_id, selected_at | 현재 표시·검색할 성공 결과 |
| `search_documents` | asset_id, searchable_text, version, updated_at | 검색 투영 결과 |
| `asset_embeddings` | asset_id, result_id?, embedding_model, dimension, vector_blob, input_fingerprint, created_at | 선택적 벡터 데이터 |
| `unity_operations` | id, request_id, asset_id, project_path, action, status, result_json, created_at | 실제 Editor 작업 및 결과 |
| `audit_events` | id, actor, action, target_type, target_id, outcome, created_at, details_redacted_json | 추적 로그 |
| `settings` | key, value_json, updated_at | 비밀키 제외한 설정 |

## 분석 상태 (서로 다른 두 축)
**A. 마지막 작업 상태**: `not_started → queued → running → completed | failed | canceled`.

**B. 유효한 성공 결과 보유 여부**: `has_successful_result` 참/거짓. 재분석 중 실패해도 기존 `asset_active_results`는 유지된다.

**검색·필터 정의**
- `미분석`: 사용 가능한 성공 결과가 없는 에셋(분석 시도한 적 없거나 실패·취소 포함), 단 실패 전용 필터에서는 마지막 실패 항목을 따로 노출.
- `분석 완료`: 현재 성공 결과가 존재하는 에셋. 마지막 재분석이 실패해도 완료 결과 보유 표시 유지.
- `분석 실패`: 마지막 시도/작업 항목이 failed인 에셋. 성공 결과 보유 에셋과 중복 가능.
- `전체`: 현재 선택 범위에 속하는 모든 등록 에셋(원본 미존재 시 실행 시 제외/오류 안내 정책).
- UI 상태 집계는 중복될 수 있는 `분석 실패`와 `분석 완료`를 단순 합산하지 않는다.

## 키 및 무결성
- ID는 UUID/ULID 등 충돌 적은 안정 식별자 중 하나로 통일. 파일명/경로만을 비즈니스 ID로 쓰지 않음.
- `asset_active_results.analysis_result_id`는 반드시 성공 `analysis_results`를 참조하며 실패 시 변경하지 않는다.
- 모델 스냅샷은 등록 모델이 수정되더라도 당시 실행 조건을 보존한다.
- 하나의 배치 요청에 `request_id`를 부여하여 중복 제출/재시작 중복 실행을 막는다.
- 검색/임베딩 인덱스는 원본 분석 결과에서 재구축할 수 있어야 한다.

## 스키마 수용 테스트
1. 앱 재실행 후 등록 폴더·태그·분석 결과 영속화.
2. 분석 실패/취소 후 이전 성공 결과 조회 유지.
3. 잘못된 마이그레이션 실패 시 기존 DB 및 백업 유지.
4. 한 번의 재스캔 후 사용자 보정 태그 손실 없음.
5. Core와 MCP의 동시 접근에서 DB 직접 경합 없음.

## 현재 초기 스키마 (R02-03)

- `db/migrations/001_initial.sql`과 Python `Database`가 스키마 버전 1을 소유한다. 19개 도메인 테이블과 `schema_migrations` 1개이며 초기 도메인 데이터는 모두 비어 있다. FTS/임베딩 생성·분석 작업은 시작하지 않는다.
- 각 연결에 FK·busy timeout 3000ms를 적용하고 WAL·quick_check를 확인한다. 마이그레이션 파일은 버전 순서·개행 정규화 SHA-256으로 검증하며 알 수 없는/미래 스키마·변경된 적용 파일은 거부한다.
- 기존 DB 업그레이드 전에 SQLite backup API로 `backups/pre-migration-UUID.sqlite`를 만들고 전체 적용을 하나의 BEGIN IMMEDIATE 트랜잭션으로 처리한다. 실패 시 롤백하고 백업을 보존한다. 손상/다른 용도의 DB를 초기화하거나 자동 교체하지 않는다.
- 성공 결과는 완료 run에만 생성하고 UPDATE를 차단한다. 활성 결과/AI 태그/임베딩은 같은 에셋의 결과만 참조한다. 모델은 기본 disabled이며 사용자 보정은 별도 테이블이다.
- health는 실제 연결의 스키마·SQLite 버전·journal mode를 반환하며 닫혔거나 실패한 연결은 error다. 실제 개발/운영 경로·앱 연결은 R02-04에서 적용한다.

## 실행 데이터 분리 (R02-04)

- debug 앱은 프로젝트 `.artifacts/data/development`, release는 Tauri `app_local_data_dir()/data`를 사용한다. 프런트엔드는 경로를 지정할 수 없고 DB 파일을 직접 열지 않는다.
- Python은 절대 경로·환경을 받아 `.ai-asset-hub.json`의 application/environment/layout_version을 확인한다. 다른 환경·알 수 없는 기존 내용·손상 표식·DB는 자동 복구/덮어쓰기하지 않고 오류로 반환한다.
- `.core.lock`은 Windows 비차단 바이트 잠금(다른 OS는 flock)을 사용한다. 동시에 한 Core만 쓰기 소유권을 가지며 EOF·정상 종료·프로세스 사망 시 OS가 잠금을 해제한다. lock 파일은 남겨도 정상이며 PID/비밀키를 저장하지 않는다.

## 라이브러리 저장 (R03-02)

기존 스키마 버전 1의 `library_roots`를 사용하며 마이그레이션은 추가하지 않는다. Python이 실제 UUID·폴더명·정규화 절대 경로를 저장하고 활성 중첩을 거부한다. 중복·비활성 경로 재등록은 같은 ID를 사용한다. 해제는 enabled만 0으로 바꾸며 원본 파일과 DB의 하위 에셋/보정/이력을 삭제하지 않는다. 쿼리는 값 바인딩을 사용하고 목록은 활성 ID 순서의 커서 페이지로 반환한다. 이 단계의 쓰기는 에셋/분석/임베딩 테이블을 변경하지 않는다.

## M04 DB v2 검색 인덱스
`002_search.sql`은 v1 원문을 수정하지 않고 파생 검색 뷰·FTS5 및 동기화 트리거를 추가한다. 업그레이드 전체 롤백/백업 정책을 유지하며 기존 자료를 재색인한다. `search_normalize` SQL 함수는 Python Core 연결에서만 등록하고 NFKC·casefold·공백 정규화를 담당한다. 다른 프로세스는 이 DB를 직접 쓰지 않는다.

## M06 DB v3 불변 이력
003_analysis_history.sql은 기존 데이터/FTS를 보존한 채 결과 삭제·run 삭제·터미널 run 수정 및 Job/run 식별/스냅샷 변경을 거부한다. 실행 중 run만 실제 입력 해시·상태·사용량/오류로 마감할 수 있다. 기존 v1/v2 DB는 백업 후 하나의 트랜잭션으로 v3까지 업그레이드한다. 실패한 재분석·취소·명시적 중단 정리는 활성 성공 결과를 변경하지 않는다.


## D-029 신규 DB 설계 경계
현행 DB v3와 001~003 마이그레이션은 이번 문서 변경에서 수정하지 않는다. 새 분류/그룹/패키지/제작/출처/권리/메타데이터 이력은 가산 마이그레이션 작업에서 확정한다. 원문 asset_tags/asset_tag_links는 현행 tags/asset_tags를 재사용하고, asset_analysis_history는 현행 분석 테이블군을 재사용한다. 다중 파일과 사용자 확정/AI 제안 분리·공유 정보 상속·불변 이력·백업/롤백의 설계 기준은 [통합 매핑](ASSET_METADATA.md#5-논리-db와-기존-구조-통합-ddl-아님)을 따른다. 이 항목은 DDL/기능 구현 완료가 아니다.


R08A-04: [통합 저장 계약](METADATA_SCHEMA.md)을 확정했다. 기존 UUID/FK/태그/분석 테이블을 유지하고 사전/연결·다중 파일 멤버십·구성 요소·관측/제안·사용자 결정/이력만 가산한다. 그룹/제작/권리는 후속 범위다.


## R08A-05 — 스키마 v4 기반
004_metadata_foundation.sql은 분류 사전/연결·파일 멤버십/구성·메타데이터 제안/사용자 결정/이력의 9개 테이블을 가산한다. 기본 사전은 2개·용어 103개이며 에셋에 분류를 자동 지정하지 않는다. v4 당시 도메인/기반 테이블 수는 FTS shadow 포함 34개다. 기존 테이블·마이그레이션 001~003을 보존하고 Core의 기존 백업/원자 적용/실패 롤백을 사용한다. 저장 계약 및 내부 서비스 경계는 [METADATA_SCHEMA](METADATA_SCHEMA.md)를 따른다.

## M08C — 스키마 v6 도입
005_collections.sql(v5)은 논리 그룹/소속·에셋별 소속 버전·불변 collection_history의 4개 테이블을 추가한다. 006_packages.sql(v6)은 배포/구매 패키지·소속·불변 최초 소속 당시 구매 스냅샷의 3개 테이블을 추가한다. FTS shadow 포함 총 41개 테이블이며 기존 001~004는 변경하지 않는다. 기존 DB를 백업 후 가산 마이그레이션 전체를 하나의 트랜잭션으로 적용하고 실패 시 롤백한다.

그룹 계층/소속과 패키지 변경은 각 revision을 검사한다. 삭제는 원본/에셋/분석을 건드리지 않으며 소속 해제와 이력을 원자 저장한다. 그룹 자식은 최상위로 승격하고 패키지는 구매 당시 기록을 보존하기 위해 비활성 보관한다. 패키지 공유값은 참조 상속하며, 에셋별 예외는 기존 metadata_decisions/metadata_decision_history에 보존한다. 세부 계약은 [METADATA_SCHEMA](METADATA_SCHEMA.md)의 M08C 절을 따른다.

## R08D-01 — 스키마 v7 도입

`007_creators.sql`은 공유 제작 주체 사전 creators 1개 테이블과 활성 상태/UUID 인덱스를 가산한다. 총 42개 테이블(FTS shadow 포함)이다. 기존 001~006 SQL/체크섬은 유지한다. 주체 유형·텍스트 길이·활성 상태·양수 revision 제약을 DB에도 둔다. 개인/팀/회사와 브랜드/홈페이지/프로필/연락처/국가/설명을 저장하며 에셋·패키지 연결 FK는 R08D-02 범위다.

Core가 기존 DB를 백업한 뒤 v7을 적용한다. 사전 쓰기와 원문 없는 audit_events 기록은 한 트랜잭션이다. 활성 변경은 물리 삭제 없이 행을 보존한다. 전체 과거 원문 이력/삭제 영향 정책은 R08D-05에서 추가하며 이번 감사에는 revision과 변경 필드명만 기록한다. v6 fixture의 전체 기존 테이블/활성 분석/FTS/원본 보존과 v7 후반 SQL 실패 시 스키마·데이터 롤백을 내부 자동화로 확인한다. 실제 사용자 DB나 기존 개발 데이터 디렉터리에는 이번 작업으로 접근하지 않는다.

## M08D — 현재 스키마 v11

008은 asset_creator_links/package_creator_links와 독립 revision 2개·불변 provenance_history, 009는 asset/package FK를 가진 provenance_sources, 010은 provenance_licenses와 license_evidence를 가산했다. licence의 source_id는 JSON의 generated column/FK와 소유 범위 트리거로 같은 대상의 실제 출처만 참조한다. 증빙은 asset_files FK와 대상 구성/패키지 멤버 범위 트리거를 사용한다. 총 테이블 수는 FTS shadow 포함 50개다. 011은 creators.deleted와 삭제/소유자/증빙 변경 보호 트리거를 추가했다. 기존 001~007 SQL은 변경하지 않는다.

모든 쓰기는 Core가 BEGIN IMMEDIATE 안에서 현재 revision/참조를 확인하고 기록·불변 전후 이력·원문 없는 감사를 함께 커밋한다. 삭제는 행/참조/이력 보존 정책이며 원본 파일에 작용하지 않는다. provenance_history의 before/after JSON은 민감 정보도 포함하는 로컬 원문 기록이다. 일반 API/내보내기/MCP는 공개 투영만 사용하며 원문 조회는 명시 승인한다. 새로운 원문 이력은 실제 변경부터 기록하고 과거 audit에 없던 원문은 추측하지 않는다. v7 fixture의 기존 모든 컬럼·행/활성 분석/FTS/원본과 v7 백업을 보존했고, 011 후반 실패 시 008~011 전체가 롤백되어 v7/기존 행·creators 컬럼이 유지됨을 검증했다.
