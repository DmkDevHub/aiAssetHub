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
