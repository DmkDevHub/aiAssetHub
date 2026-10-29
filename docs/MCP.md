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
