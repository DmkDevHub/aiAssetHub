# METADATA_SCHEMA — R08A-04 통합 저장 계약

## 현재 구조 보존
현재 asset_files.asset_id는 수집 시 생성한 원래 소유 에셋이다. 이 FK/UUID와 기존 분석/태그/FTS를 바꾸지 않는다. 다중 파일은 별도 asset_file_members에서 논리 에셋과 물리 파일을 연결한다. 기존 수집 파일은 migration 시 자기 에셋의 source 멤버로 연결한다. 스캔·이름·동일 해시만 보고 묶거나 기존 Asset을 병합하지 않는다. 신규 스캔 파일의 자기 에셋 source 연결은 v4 트리거로 동기화한다. 다중 파일 편집 API/UI는 M08B-03 범위다.

## R08A-05의 가산 테이블
| 테이블 | 제약/목적 |
|---|---|
| classification_dictionaries | version PK, kind(type/facet), JSON 스냅샷. 같은 버전 수정/삭제 금지 |
| classification_terms | version/axis/code PK, 부모 같은 버전/축 FK, dictionary FK. 코드/버전 불변 |
| asset_classification_selections | asset PK/FK, type_version와 대표 코드 FK. 대표 1개 또는 null |
| asset_classification_links | 에셋/버전/축/코드 PK·실제 사전 term FK, 복수 탐색/독립 축 연결 |
| asset_file_members | 에셋/파일/역할 PK, 실제 asset_files FK. 원본 이동/삭제 없음 |
| asset_components | 내부 UUID, 파일/입력 SHA256/종류/locator/식별 버전. 동일 내용/위치의 구성 요소 유일 |
| metadata_claims | 실제 에셋/필드·출처(file/parser/ai)·JSON 값·근거 파일/성공 결과 FK·스키마 버전. 추가만 허용 |
| metadata_decisions | 에셋/필드 PK, 사용자 set/clear/adopt·값/선택 claim·단조 revision. 제안과 분리 |
| metadata_decision_history | 사용자 결정의 이전/새 값·revision·시간. 추가만 허용 |

그룹/패키지/제작 주체/권리 테이블은 M08C/D에서 별도 추가한다. 기존 tags/asset_tags와 analysis_jobs/items/runs/results/active 포인터를 재사용한다. 과거 category 문자열은 보존하되 새 분류를 추측해 연결하지 않는다. 필드별 JSON 스키마/민감 값 필터와 사용자 편집 UI는 M08B/E/F에 연결한다.

## 내부 구성 식별
asset_composition.component는 실제 파서가 읽은 file UUID·입력 SHA256·종류·상대 내부 locator를 받아 내부 카탈로그 UUID를 결정적으로 만든다. 경로/파일명이나 Unity 성공 ID를 추측하지 않는다. 파일 지문이 달라지면 다른 구성 ID이며 과거 구성은 원본 버전 참조로 보존한다. 활성 파일의 지문과 맞지 않는 구성은 사용 시 stale로 취급한다. 이 계약 자체는 파서를 구현하거나 클립 존재를 증명하지 않는다.

## 영속성·마이그레이션
001~003 SQL을 편집하지 않고 004로 추가한다. 기존 DB backup API·단일 트랜잭션·체크섬·실패 롤백을 유지한다. 기본 사전만 넣고 에셋의 분류/AI 제안/사용자 결정을 자동 생성하지 않는다. 스키마 v3→v4 보존 검사에는 실제 fixture UUID·사용자 태그·불변 성공/실패 이력·활성 결과·FTS 문서/무결성·모델 Job/벡터 수·원본 해시를 포함한다.

Core 내부 저장 서비스만 새 테이블을 쓴다. 아직 Vue/MCP에 임의 JSON 쓰기 API를 열지 않으며 모델·파일 변경·광범위 재분석을 호출하지 않는다. 사용 중 term 비활성은 새 버전에만 기록하고 참조된 과거 버전은 삭제하지 않는다. 전체 정책/사용자 영향 적용 UI는 후속 관리 작업이다.


## R08A-05 구현
SQLite v4의 004_metadata_foundation.sql로 위 9개 테이블과 사전 스냅샷/용어 103개를 추가했다. 기존 001~003 및 에셋/파일/태그/불변 분석/FTS/벡터는 변경하지 않는다. 사전 2개와 코드만 초기화하고 에셋 분류/제안/결정을 자동 생성하지 않는다.

MetadataStore는 Core 내부 전용이다. propose는 실제 에셋·멤버 파일 또는 같은 에셋의 성공 결과 FK를 검증하고, decide는 명시 승인·기대 revision 일치·set/clear/adopt를 한 트랜잭션으로 적용한다. 관측·AI 제안과 사용자 결정이 분리되며 SQL 트리거가 이전/새 결정과 최초 관측 근거를 이력으로 남긴다. classify는 저장된 사전 버전을 로드해 정규화한 대표/탐색/독립 축과 사용자 이력을 함께 저장한다. 일반 JSON 필드 저장은 형식별 UI 편집 API가 아니며 공개 API의 필드 스키마·개인정보/노출 정책은 M08B/E/F에서 연결한다.

retire_facet은 실제 링크의 사용 에셋 수를 조회해 사용 중이면 승인·같은 축의 활성 대체값을 요구한다. 새 불변 사전 버전만 등록하고 구버전 참조를 바꾸지 않는다. 새 버전의 비활성 값은 선택할 수 없으며 새 버전 재지정은 별도 classify 호출이 필요하다. 현재 기본 버전은 v1이며 전역 기본값 전환/사용자 사전 관리 UI는 후속 범위다.

사전 용어는 JSON 스냅샷과 SQL 행이 일치해야 하며 버전/용어/제안/구성/이력의 수정·삭제는 차단한다. 타입과 다른 축 FK 혼합·비활성·대표/탐색 계층 중복을 거부한다. 결정 revision 단조 증가·명시 clear·adopt 실제 값 일치도 DB에서 검증한다. 메타데이터 변경 이력은 값을 보관하는 업무 데이터이며 레드랙션된 감사 로그와 별개다. 이력/제안 테이블을 MCP에 그대로 노출하지 않는다.

구성 요소 테이블은 식별·보존 기반이며 실제 파서/현재 지문과의 신선도 평가·편집·검색 투영은 후속 M08B/E/F다. 현재 앱/MCP의 분류 지정·메타데이터 편집 동작이 추가된 것은 아니다.
