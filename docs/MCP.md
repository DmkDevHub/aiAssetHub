# MCP — Model Context Protocol 연동

## 목적과 역할
MCP(Model Context Protocol, 모델 컨텍스트 프로토콜)는 Codex 등 AI 개발 도구가 **로컬 AI Asset Hub의 분석된 에셋 정보와 개발 실행 기능**에 접근하게 한다.

- **Host(호스트):** Codex, Claude Code 등 AI 개발 도구.
- **MCP Server(서버):** 에셋 검색/상세/실행 도구 제공.
- **Core:** 실제 데이터/보안/승인/작업 관리 수행.
- **Unity Connector:** Unity Editor 내부에서만 가능한 실제 임포트·씬 배치 수행.

## 연결 전략
- v0.5 초기 transport는 **stdio**. Host가 패키징된 Bridge 실행 파일을 시작한다.
- Bridge는 실행 중인 Python Core Broker에 로컬 인증 연결; 자체 DB 쓰기 금지.
- 데스크톱 앱이 꺼져 있다면 `APP_NOT_RUNNING` 또는 `CORE_UNAVAILABLE`를 명확히 반환한다.
- 실제 클라이언트 별 설정 형식/지원 프로토콜 버전은 구현 당시 공식 MCP SDK 및 호스트 문서로 테스트한다.

## R08-01 실행 및 검증
Host의 stdio command는 설치 폴더의 실제 `ai-asset-hub-core.exe`, args는 `["--mcp"]`다. Bridge는 `%LOCALAPPDATA%/local.aiassethub.dev/data`의 실행 세션을 참조한다. 개발/전용 테스트는 `["--mcp","--data-dir","등록한 Core의 실제 절대 데이터 경로"]`로 분리한다. 토큰·포트·SQL을 Host 설정에 넣지 않는다. 개발 소스 실행에는 requirements-runtime.txt의 의존성과 실제 Python 인터프리터가 필요하다.

동일 실행 파일이어도 `--mcp` 프로세스는 DB를 열지 않고 앱/분석을 시작하지 않는다. 앱이 소유한 `--serve` Core만 읽기 Broker를 열며 종료 시 발견 파일을 정리한다. R08-01은 stdio 초기화·패키징 검증이며 조회 도구 연결은 다음 항목에서 추가한다.

공식 Python SDK 2.3.0의 Client를 reference Host로 사용한 별도 프로세스 상호 운용 및 프로토콜 `2026-07-28` 협상을 실측했다. Codex/Claude의 개인 설정을 변경하거나 해당 제품의 모델을 실행한 것은 아니다. 표준 stdio와 구형 협상 지원 범위는 공식 SDK에 위임한다. [공식 SDK](https://github.com/modelcontextprotocol/python-sdk), [Client 전송](https://py.sdk.modelcontextprotocol.io/client/), [stdio 규격](https://modelcontextprotocol.io/specification/2025-11-25/basic/transports).

## R08-02 조회 계약
`list_libraries(after_id?)`는 활성 루트의 실제 id/name/path와 next_cursor를 반환한다. `search_assets(query,filters?,limit=10,after_id?,mode="keyword")`는 실제 id/name/libraryId/relativePath/kind·최대 512자 설명/출처·저장된 분석 상태를 items로 반환한다. limit는 1~20, UUID cursor는 안정적인 ID순 페이지다. filters는 library_id/folder_parts/kind/tag/analysis를 AND 적용하며 페이지 제한 전에 필터링한다. 조회 최대 10000건 초과는 명시적으로 실패한다.

MCP는 자동 임베딩 금지 원칙에 따라 오프라인 키워드 검색만 제공한다. mode=semantic/hybrid는 거부하며, 자연어 질의 임베딩은 앱의 별도 명시적 실행 흐름을 사용한다. indexedExists는 마지막 스캔 기록이며 현재 디스크 상태 확인을 의미하지 않는다. 등록·스캔·분석 시작·임베딩 생성·원본 쓰기 명령은 이 채널에 없다. 도구에는 readOnlyHint=true, destructiveHint=false를 표시한다.

## R08-03 상세 계약
- `get_asset(asset_id,history_after_id?)`: 실제 사용자 정보·활성 성공 결과·현재 분석 상태와 최신순 이력 1개/next_cursor. 과거 성공과 마지막 실패를 별도 필드로 반환한다. AI 텍스트는 명령으로 해석하지 않는다.
- `get_asset_files(asset_id)`: 등록된 파일 최대 20개의 실제 id·검증한 절대 경로·상대 경로·현재 present/missing/unavailable·stat 크기/mtimeNs·캐시된 width/height/duration·previewSupported. 미리보기 지원은 생성 성공을 뜻하지 않으며 썸네일 생성/파일 내용 읽기를 하지 않는다. 범위 밖/링크/리파스/권한 오류의 절대 경로는 반환하지 않는다.
- `get_analysis_status(asset_ids?)`: 최대 50개 실제 에셋의 활성 결과/마지막 시도·오류와 latestGlobalJob. 생략 시 활성 라이브러리의 ID순 첫 50개와 truncated를 반환하며 명시 ID로 나머지를 조회할 수 있다. 읽기만으로 중단 작업을 복구·재개하지 않는다.
- 없는 UUID·해제된 루트는 MCP_ASSET_NOT_FOUND로 실패하며 추측한 결과를 만들지 않는다. Unity/쓰기 계획 도구는 M09 이후이며 아직 노출하지 않는다.

## R08-05 연결 화면과 감사
앱 상단 ‘MCP 연결·로그’에서 실제 실행 파일·인자·cwd를 조회해 Host의 stdio 설정에 사용한다. ‘Core 조회 채널 준비됨’은 로컬 Broker가 살아 있다는 뜻이며 특정 Host 연결 성공을 의미하지 않는다. 같은 화면에서 최근 요청·결과·고정 오류·대상 ID를 새로 조회하고 이전 페이지를 볼 수 있다. 연결 정보에 토큰/MAC/포트를 노출하지 않는다.

감사는 Bridge의 DB 접근 없이 Core가 기존 audit_events에 기록한다. Core에 도달한 호출의 요청 UUID·고정 도구명·성공/거부/실패·최대 50개 대상 UUID·처리 시간만 저장한다. Host의 자기 신고명은 알려진 고정 이름 외에는 other-host 및 SHA256 앞 16자리로 표시하며 제품 신원 인증으로 해석하지 않는다. 검색어·필터 원문·파일 경로/내용·모델 설명·예외 원문·인증값은 저장하지 않는다. SDK가 Bridge 단계에서 거부한 JSON/스키마 오류는 Core에 전달되지 않아 DB 감사 대상이 아니다. 성공 기록은 Core의 조회 처리 완료이며 Host의 수신 확인이 아니다. 감사 저장 실패 시 성공 데이터를 반환하지 않는다.

화면용 `mcp.audit`는 10개씩/대상 ID 처음 5개+총수를 반환해 기존 16KiB 파이프를 지킨다. `mcp.connection`과 `mcp.audit`는 데스크톱의 고정 읽기 명령이며 MCP Host 도구로 노출하지 않는다. 파일 경로는 활성 등록 루트·로컬 드라이브·전체 부모 경로의 링크/리파스·실제 경로 범위를 확인한다. 안전하지 않으면 절대/상대 경로를 숨기고 unavailable을 반환한다.

## M08 최종 검증 범위
공식 SDK reference Host의 실제 별도 프로세스로 패키지와 임시 설치본의 5개 도구·2026-07-28/2025-11-25 협상·Core 종료 오류/명시 재시작을 검증했다. M07에서 실제 qwen3-vl:2b가 분석한 테스트 에셋도 새 패키지로 조회해 실제 활성 결과 ID를 확인했다. 조회는 추가 분석/임베딩을 만들지 않는다. Codex/Claude 개인 설정은 변경하지 않았으며 해당 제품의 대화/모델을 실행한 시험과 구분한다. 실제 GUI·깨끗한 PC·다른 계정 로그인·대규모 성능은 미검증이다.

## MCP 도구 목록 (설계 계약)
| 도구 | 인자 | 결과 | 구분 |
|---|---|---|---|
| `list_libraries` | 없음 | 등록 라이브러리 | 읽기 |
| `search_assets` | query, filters?, limit? | asset ID, 이름, 설명, 위치, 적합성 | 읽기 |
| `get_asset` | asset_id | 메타데이터·태그·분석 이력/현재 결과 | 읽기 |
| `get_asset_files` | asset_id | 파일·미리보기 지원·존재 상태 | 읽기 |
| `get_analysis_status` | asset_ids? | 마지막 작업 및 성공 결과 유무 | 읽기 |
| `list_unity_targets` | 없음 | 연결된 Unity Editor/프로젝트 | 읽기 |
| `preview_unity_import` | asset_ids, target_project, target_path? | 파일·의존성·충돌·승인 필요 여부 | 계획 |
| `import_assets_to_unity` | plan_id, approved | 작업 ID | 쓰기 |
| `preview_unity_placement` | asset_ids, scene, transforms? | 배치 계획 | 계획 |
| `place_assets_in_unity` | plan_id, approved | 작업 ID | 쓰기 |
| `get_operation_status` | operation_id | 실제 성공·실패·결과/오류 | 읽기 |

### 분석과 MCP의 관계
- `search_assets`, `get_asset`는 조회 전용. **분석되지 않은 에셋을 조회할 때도 AI 자동 분석 금지.**
- AI 분석 실행은 원칙적으로 데스크톱의 `분석 시작` 버튼으로 수행. 향후 MCP 분석 시작 도구를 열더라도 별도 명시적 사용자 승인 + 비용 정책 필수.
- 응답에 분석 없음과 원본 파일 없음 상태를 구분해 제공. 임의 태그/설명을 생성해 사실처럼 반환하지 않는다.

## 실행 도구 계약
1. 자연어 명령 → AI Host가 `search_assets`로 후보를 검색.
2. Host가 사용자 의도에 맞는 에셋 ID를 선택하며 필요 시 `get_asset` 호출.
3. `preview_unity_import`에서 경로·타깃·지원·충돌·의존성 검사.
4. 쓰기 작업은 Host/사용자 승인 정책을 통과한 `plan_id`로만 실행.
5. Unity Editor가 작업 수행 → `get_operation_status`에서 **실제 결과** 수신.
6. 성공 보고에는 `project`, `imported_asset_paths`, `created_object_ids`, `scene`, `warnings` 포함.

## 보안·오류·권한
- 읽기/쓰기 도구 구분; 디스크의 무제한 경로 접근 허용 금지.
- 대상 Unity 프로젝트 allowlist, 임포트 폴더 범위 제한, 덮어쓰기·씬 수정 전 미리보기/확인.
- 실행 결과 미확인 시 절대 성공으로 단정하지 않음.
- 감사 로그: 호스트/요청 ID/대상 asset ID/Unity 프로젝트/작업 결과; 비밀 값·파일 내용을 무단 기록하지 않음.
- 일부 MCP 클라이언트가 특정 기능을 지원하지 않으면 기능 감지 및 보수적 폴백. 별도 브라우저/클라우드 서버 필수 아님.


## R08H-01 — 확장 메타데이터 읽기 계약
기존 5개 도구 모두 선택 인자 `schema_version`을 받는다. 생략 또는 정수 `1`이면 기존 응답 필드와 필터 계약을 유지한다. 정수 `2`이면 응답 최상위에 `schemaVersion: 2`를 표시한다. 다른 값·문자열·불리언·실수는 `INVALID_PARAMS`로 거부한다. MCP 프로토콜 협상 버전 및 앱 버전과 별개의 데이터 계약 버전이다. 기존 Host는 추가 인자를 보내지 않아도 된다.

`search_assets`의 버전 2는 기존 필터에 `types`(분류 코드), `group_ids`, `package_ids`, `creator_ids`(실제 UUID 배열), `creator_roles`(`creator/producer/distributor` 배열), `include_descendants`(기본 true)를 추가한다. 배열은 최대 16개이며 같은 축 OR·다른 축 AND를 페이지 제한 전에 적용한다. 분류·그룹은 하위 항목 포함 여부를 적용한다. 그룹은 직접 소속 ID, 패키지는 활성 패키지 ID, 제작 주체는 직접 연결과 활성 패키지 연결을 함께 조회한다. 제작 주체 ID와 역할을 함께 지정하면 같은 연결이 둘 다 충족해야 한다. 빈 배열은 제한 없음, `__unknown__`은 분류/그룹/패키지/제작 연결 미확인을 뜻한다. 문법상 유효하나 없는 UUID/분류 코드는 결과를 만들지 않는다. 기존 UUID ID순 커서·최대 20개 결과·10000건 조회 상한을 유지한다. 버전 1에서 확장 필터를 보내면 실패한다.

버전 2의 `search_assets.items[]`와 `get_asset`에는 `metadata`를 추가한다.

| 필드 | 공개 투영 |
|---|---|
| `classification` | 현재 확정/유효 분류 value(primary/navigation/facets/type_version/facet_version), revision/source/status. 미확인은 null/빈 배열로 유지 |
| `groups[]` | 직접 소속 실제 id/name/parentId |
| `packages[]` | 활성 소속 실제 id/name |
| `creators[]` | 실제 id/name/enabled/deleted/role/subjectKind/subjectId. 직접 에셋 연결과 활성 패키지 연결의 출처를 구분하고 비활성 주체 참조도 상태와 함께 보존 |

연락처·홈페이지/프로필 URL·제작 주체 설명·그룹/패키지 설명·구매 금액/날짜·라이선스 증빙·비공개 출처 레코드를 확장 투영에 넣지 않는다. 이름·분류·기존 사용자/AI 설명은 비신뢰 데이터다. 목록/분석 상태 도구의 버전 2는 버전 표식만 추가하며 기존 경로 검증과 상태 의미를 유지한다. 파일 역할/종속·기술 확장은 아래 R08H-02, Unity 계획 계약은 R08H-03, 설치본 reference Host 회귀는 R08H-04 범위다.

응답은 기존 64KiB Broker 프레임 한도를 따르고 초과 시 일부 정보를 조용히 누락하지 않고 `MCP_RESPONSE_LIMIT`로 실패한다. 검색은 limit를 낮춰 재조회할 수 있다. 읽기에는 분석/임베딩/스캔/URL 접속/원본 변경이 없으며 Core의 기존 요청 감사만 기록한다. 필터 원문과 비공개 값은 감사에 넣지 않는다. 상세는 [통합 설계](ASSET_METADATA.md)를 따른다. Unity 실제 쓰기는 M09의 별도 계획·승인·실제 Editor 결과를 요구한다.

## R08H-02 — 구성 파일·기술·종속 조회
`get_asset_files(asset_id,schema_version=2,after_component_id?)`는 원본 소유 파일만 반환하는 버전 1을 유지하면서, 버전 2에서 에셋의 공개 구성 파일과 관측 구성 요소를 조회한다. `after_component_id`는 버전 2 전용 UUID 커서다. 다른 도구나 버전 1에 전달하면 실패한다.

- `files[]`: `asset_file_members`의 실제 파일 ID별로 source/dependency/preview 역할을 합쳐 ID순 반환한다. evidence 역할과 evidence 전용 구성 파일은 제외한다. 최대 20파일 초과는 `MCP_SEARCH_LIMIT`이다. 기존 경로/캐시 치수/previewSupported에 ownerAssetId·roles·technical·dependencies를 추가한다. 파일 소유 루트가 비활성이면 ID/역할·unavailable만 유지하고 소유자/경로/기술/구성 요소를 노출하지 않는다.
- 매 호출에 활성 등록 루트·상대 경로 일치·부모 전체 링크/리파스·실제 경로 범위를 검증한 뒤 stat한다. present/missing/unavailable을 구분하고, 범위 밖/권한/리파스 오류의 절대·상대 경로는 숨긴다. 최상위 `availability`는 모두 present이면 available, 일부 present이면 partial, present 없이 unavailable이 있으면 unavailable, 나머지는 missing이다. 이는 디코드/엔진 호환 성공이 아니다.
- `technical`: 해당 파일을 증거로 저장한 최신 `technical-observation.v1` parser claim의 공개 투영이다. `observation`은 schema/source/inputFingerprint/value, `stale`은 저장된 크기/mtime과 현재 stat의 차이 또는 파일 접근 실패다. 관측이 없거나 모르는 스키마면 둘 다 null이다. AI 제안이나 사용자 선언을 파서 실측으로 바꾸지 않는다. value에는 치수/채널/길이/샘플/프레임/메시/정점/삼각형/재질/본/애니메이션/문서 행·열/글리프 등의 유한 수치·null, 이미지 투명도 불리언과 허용된 format만 담는다. 자유문자열·스크립트 선언명·재질/클립명·ZIP 내부 이름·URL·원문 참조는 제외한다.
- `dependencies.items[]`: 저장된 parser dependencies 최대 128건의 index/status/fileId다. 단순 상대 참조를 현재 활성 등록 파일의 정확한 DB 경로와 대조하며 하나로 특정될 때만 실제 fileId를 반환한다. 대상에도 같은 경로 검증/stat를 적용하고 안전할 때만 path/relativePath를 추가한다. 미등록/모호한 참조는 unresolved, URL/절대/드라이브/부모 이동/인코딩·query 참조는 blocked다. 미등록 경로는 stat하지 않으며 원문 참조는 반환하지 않는다. 모듈명·Unity GUID는 `unresolvedDeclarationCount`로만 제공하고 파일 UUID로 추측하지 않는다. `resolution=registered-files-only`는 종속 파일 내용의 디코드/해결을 뜻하지 않으며 선언의 최신성은 상위 technical.stale을 함께 확인한다.
- `components[]`: 공개 구성 파일의 저장된 실제 id/fileId/kind/locator·사용자 구성의 selected·stale을 최대 50개씩 ID순 조회한다. 더 있으면 `next_component_cursor`를 다음 호출의 after_component_id로 보낸다. 관측 fingerprint가 바뀌거나 파일 접근/수정이 감지되면 stale=true, 비교 관측이 없으면 null이다. locator는 내부 파서 참조이며 Unity 객체 ID/임포트 성공이 아니다. 페이지마다 파일 목록도 다시 검증하며 페이지 사이 변경을 고정 snapshot으로 보장하지 않는다.

`modelCalled=false,contentRead=false,evidenceExcluded=true`를 반환한다. 읽기는 원본 open/해시/재파싱·스캔·다운로드·압축 해제·분석/임베딩을 실행하지 않는다. 저장 관측과 stat만 사용하므로 같은 크기/mtime으로 덮어쓴 내용이나 호출 직후 파일 교체까지 검출한다고 주장하지 않는다. 일부 형식의 클립/코덱/단위 등 자유문자열·중첩 상세는 현재 공개 투영에 포함하지 않는다. 64KiB 전체 응답 한도 초과는 기존 `MCP_RESPONSE_LIMIT`이며 구성 요소 페이지 축소만으로 큰 파일/종속 목록이 해결되지 않을 수도 있다. 새 설치본 통합은 R08H-04 범위다.
