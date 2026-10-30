# API_CONTRACTS — 내부 유스케이스 계약 초안

> 앞부분 표는 최초 논리 설계이며 작업별 구현 계약은 뒤의 절을 따른다. M08E까지의 실제 UI 경계는 아래 catalog/metadata_request 절에 기록한다.

## Core 명령 (논리 API)
| 명령 | 주요 입력 | 출력/부작용 |
|---|---|---|
| `health.get` | 없음 | Core/DB/버전 실측 상태 |
| `library.register` | `path` | 실제 library ID와 등록 상태 저장. 현재 R03-02에서는 스캔/AI 작업 미생성; 스캔은 R03-03 |
| `library.unregister` | `library_id` | 등록 비활성화; 원본/에셋/태그/이력 보존 |
| `library.scan` | `library_id` | 명시적 재귀 수집 결과 processed/new/changed/missing/errors/complete; AI 미호출 |
| `library.list` | `after_id?` | 활성 등록 폴더 페이지와 다음 커서 |
| `asset.list` | `after_id?` | 활성 루트의 실제 파일 인덱스 1개/페이지와 다음 UUID 커서; 현재 폴더/정렬은 UI에서 결합 |
| `asset.get` | `asset_id` | 현재 파일 경로/바이트/수정시각·지원 해상도·present/missing/unavailable. 사용자/분석 상세는 후속 |
| `asset.thumbnail` | `asset_id` | PNG/JPEG 원본 불변 캐시 data URL 또는 missing/unsupported/too_large/unavailable |
| `asset.update_metadata` | `asset_id`, `tags`, `description?` | 보정 저장; 원본 파일 불변 |
| `analysis.preview` | `scope`, `mode`, `model_id` | 대상 ID/수, 전송 내용, 예상 비용 |
| `analysis.start` | `preview_token?`, `scope`, `mode`, `model_id`, `approval` | 작업 ID; **명시적 실행 요청 필수** |
| `analysis.cancel` | `job_id` | 취소 요청 수락 상태 |
| `analysis.jobs` | `job_id?` | 실측 진행률·에러 |
| `model.list` | 없음 | 사용 가능한 모델과 능력 |
| `model.test` | `model_id` | 연결 테스트 결과(유료 호출 여부 고지) |
| `search.assets` | `query`, `mode`, `filters`, `limit` | 결과/출처; 암묵적 분석 금지 |
| `unity.preview_operation` | `asset_ids`, `target`, `action`, `options` | 계획/경로 충돌/확인 필요 여부 |
| `unity.execute_operation` | `plan_id`, `approved` | 작업 ID; 승인 정책 검증 |
| `unity.get_operation` | `operation_id` | 에디터 실측 결과 |

## 공통 응답
```json
{
  "request_id": "request-uuid",
  "ok": true,
  "data": {},
  "error": null,
  "timestamp": "ISO-8601"
}
```
에러 시 `ok=false`, `error={"code":"...","message":"...","retryable":false}`를 사용한다. 요청 ID는 중복 실행 방지·로그 연결에 사용.

## 계약 기본 규칙
- 입력 ID, 허용 폴더 경로, 파일 확장자/타입, 모델 지원 기능, 단일 요청 크기를 검증.
- 폴더 등록·검색은 분석을 트리거하지 않음; `analysis.start`만 명시적으로 분석 생성.
- UI 진행 상태는 직접 상태 조회/이벤트로 전파; 예상값·더미 성공 데이터를 표시하지 않음.
- MCP 서버는 위 유스케이스를 호출하되 Core DB와 도메인 규칙을 우회하지 않음.
- 취소/타임아웃/부분 성공을 응답 스키마에 정직하게 반영.

## 현재 Core health 계약 (R02-01)

- `CoreApplication.handle`은 `{request_id: UUID, method: "health.get", params?: {}}`만 처리한다. 알 수 없는 필드·입력 매개변수·미지원 명령은 거부하며 동적 메서드 실행을 하지 않는다.
- 성공 응답의 `data.core`는 `status: "ready"`, `version`, `pid`, `python_version`, `uptime_ms`다. PID·가동 시간은 현재 실행 프로세스의 실측이며 `ready`는 이 명령 처리기의 준비 상태다. 앱/Tauri·DB·모델 연결 성공을 뜻하지 않는다.
- `data.database`는 `{status: "not_configured"}`다. DB 연결·마이그레이션 전에는 성공 상태·가짜 버전·데이터 경로를 생성하지 않는다.
- 응답은 기존 공통 envelope를 사용한다. 잘못된 요청 ID는 원문을 반사하지 않고 `request_id: null`, 오류는 고정 `INVALID_REQUEST`/`INVALID_PARAMS`/`METHOD_NOT_FOUND`/`INTERNAL_ERROR` 문구로 반환한다. 예외 메시지·인자·환경·경로·비밀정보는 출력하지 않는다.
- `python -B -m ai_asset_hub_core health.get`은 개발용 일회성 조회다. `--request-id UUID`를 생략하면 상관 UUID를 생성한다. 성공 0, 요청 오류 2, 내부 오류 1로 종료한다. 네트워크 서버·Tauri IPC·MCP 전송 구현이 아니며 안전한 앱 통신은 R02-02에서 연결한다.

### 데스크톱 health 확장 (M02)

- Tauri 시작 인자 `--serve --data-dir <백엔드 경로> --environment development|production`는 비공개 파이프 서비스와 DB를 초기화한다. 초기화 실패는 Core를 준비된 DB로 위장하지 않고 `database.status: error`와 고정 error_code로 반환한다.
- 연결된 DB의 health는 `status: ready`, `schema_version`, `sqlite_version`, `journal_mode: wal`이다. 경로 없이 실행한 CLI만 `not_configured`다. DB가 준비되었다는 것은 라이브러리 수집/AI/모델이 준비되었다는 뜻이 아니다.
- Core 연결 관찰과 재연결은 Vue의 `core_health`/`core_reconnect`를 사용한다. Tauri는 실행 중 자식의 UUID/PID/제품 버전을 대조한 후 응답하며 실패하면 안전한 CORE_* 코드만 반환한다. UI도 envelope·PID/가동 시간·DB 스키마 형식을 검증한다.
- 5초 health 관찰은 읽기 전용이며 실패 시 자동 재시작하지 않는다. 수동 재연결도 Core/DB 준비만 수행하며 분석 작업을 생성·재개하지 않는다.

## 데스크톱 폴더 선택 (R03-01)

- `select_library_folder`는 main 창 전용 Tauri 명령이며 프런트엔드 입력 인자를 받지 않는다. 실제 OS 선택기의 단일 폴더 결과만 검증해 `{path: string}`으로 반환하고 취소는 `null`이다. 임의 경로·필터·명령 실행 API를 노출하지 않는다.
- `FOLDER_PICKER_BUSY`, `FOLDER_LOCAL_ONLY`, `FOLDER_ROOT_NOT_ALLOWED`, `FOLDER_UNAVAILABLE`, `FOLDER_PICK_FAILED`는 고정 코드이며 예외/경로 원문을 오류에 반사하지 않는다. 선택된 경로 자체는 사용자가 확인할 UI에만 표시한다.
- 이 명령은 Core의 `library.register`가 아니며 등록·DB·스캔·분석 작업을 생성하지 않는다. frontend dialog/fs 범용 권한도 부여하지 않는다. [Tauri dialog Rust API](https://v2.tauri.app/plugin/dialog/)를 사용한다.

## 등록/해제와 활성 목록 (R03-02)

- Tauri `register_library({path})`는 마지막 네이티브 선택 경로와 대조한 후 Core `library.register({path})`만 호출한다. 성공은 `{library: {id, name, path}, created: boolean}`이며 Python DB의 실제 UUID다. 중복/비활성 재등록은 기존 ID를 반환한다.
- `unregister_library({libraryId})` → `library.unregister({library_id})`는 `{library_id, enabled: false}`를 반환한다. 같은 ID의 해제 재요청은 안전하며 물리 파일·하위 DB 이력을 지우지 않는다. 없거나 잘못된 ID는 성공으로 위장하지 않는다.
- `list_libraries({afterId: null|UUID})` → `library.list({after_id})`는 `{libraries: [{id,name,path}], next_cursor: UUID|null}`다. 활성 ID 순서이며 페이지는 최대 50개/레코드 합계 12KB다. 한 레코드 6KB를 넘는 경로는 명확히 거부해 기존 16KiB 프레임 한도를 지킨다. UI는 반복/잘못된 커서를 거부하고 최대 200페이지를 읽는다.
- 사업 규칙 오류는 공통 envelope의 `ok:false`와 고정 코드/문구로 반환하며 정상 Core 세션을 종료하지 않는다. 실제 통신 실패는 기존 세션 수거 정책을 사용한다. 초과 요청은 전송하지 않으며 세션을 유지한다.
- 등록/해제는 자동 재시도하지 않는다. 응답 불명확 시 UI는 확인된 목록을 유지하고 새로고침을 안내한다. 현재 등록/조회/해제는 파일 스캔·분석 작업을 생성하지 않는다.

## M01 UI 작업 이벤트 수신 계약 (R01-06)

`src/stores/operations.ts`의 `receiveOperation(event)`는 UI 메모리 표시 전용이며 명령·재시도·분석을 실행하지 않는다. Core 통신 방식/DB 스키마는 변경하지 않는다.

| 필드 | 규칙 |
|---|---|
| `id` | 실제 명령/작업의 상관 ID, 비어 있지 않은 200자 이내 문자열. UI/로그에는 표시하지 않음 |
| `kind` | `appearance.change`, `gallery.view`, `library.scan`, `analysis.run`, `unity.apply` |
| `state` | `running`, `succeeded`, `failed`, `cancelled` |
| `progress?` | 실측 `processed`/`total` 안전한 정수, `0 ≤ processed ≤ total`. 같은 작업의 총수 변경·역행 거부. 성공 이벤트는 전체 완료 건수를 명시 |
| `errorCode?` | `PERMISSION_DENIED`, `CORE_UNAVAILABLE`, 그 외는 고정 `COMMAND_FAILED`로 정규화. 원문 메시지/경로/비밀정보를 전달하지 않음 |

- 수신 성공은 `true`, 잘못된 입력·종료 상태에 대한 후속 갱신·용량 부족은 `false`다. 어댑터는 실패 반환을 처리해야 한다. 실행 중/미확인 오류를 덮어쓰지 않으며 최대 20개 상태를 보존한다.
- 0/0건 완료는 허용하며 추정 백분율을 생성하지 않는다. 제공하지 않은 진행 수는 생성하지 않는다. 종료 이벤트는 실제 실행 결과에 근거해 전달하며 성공·실패를 추측하지 않는다.
- `executeUiCommand`는 현재 로컬 테마/보기 변경 콜백만 감싸고 `ui-command-*` 상관 ID를 만든다. 이것은 에셋/모델/백엔드 작업 ID가 아니다. 콜백 종료 후 성공, 예외 시 안전한 실패 문구를 기록하며 자동 재시도하지 않는다. 이력 공간이 없으면 콜백을 실행하지 않고 `false`를 반환한다.
- 실제 Core/스캔/분석/Unity 송수신 연결은 후속 마일스톤이며 현재 테스트 fixture가 그 성공을 보증하지 않는다.

## M04 사용자 메타데이터·검색 명령
모두 고정 Tauri 명령→Python allowlist만 통과한다. 활성 등록 폴더의 실제 asset UUID만 허용한다. 오류는 고정 INVALID_PARAMS/DB_UNAVAILABLE이며 원문 예외를 반환하지 않는다.
| Tauri | Core | 입력/출력 |
|---|---|---|
| asset_annotations | asset.annotations | assetId→asset_id / tags,title,description |
| edit_asset_tags | asset.tags | assetId,add,remove / 저장된 사용자 정보 |
| save_asset_annotation | asset.annotate | assetId,title,description / 저장된 사용자 정보 |
| batch_asset_tags | asset.tags.batch | assetIds→asset_ids,add,remove / updated |
| search_assets | asset.search | query,afterId→after_id / ids,next_cursor |

태그는 NFKC·casefold 중복 제거, 각 64자·에셋당 32개/합계 512자. 표시명 128자·설명 1024자, 빈 값은 override 해제. 사용자 태그만 변경하며 AI 이력은 보존한다. 일괄 최대 100개, 전체 대상 검증 및 원자적 반영. add/remove가 겹치면 추가를 우선한다. asset.list의 name은 사용자 표시명 우선이며 userTags는 사용자 태그만 포함한다. 검색 query는 최대 256자/16단어, ID순 200개 페이지다. 전체 파이프 응답은 UTF-8 JSON을 사용한다. 원본·AI 호출·과금·분석 작업은 발생하지 않는다.

## R04-06 분석 상태 조회
`asset.list`는 `hasActiveResult`(boolean), `lastAttemptState`(마지막 run 상태 또는 null), `lastAnalysisAt`(활성 결과 생성 시각 또는 null)을 반환한다. 시도 순서는 created_at·rowid 역순이며 실패한 재분석은 활성 성공 결과를 교체하지 않는다. 필터/정렬은 이 실제 DB 값과 파일 수정 시각을 사용한다.

## M05 고정 모델 명령
모든 명령은 Tauri 고정 wrapper와 Python allowlist를 통과한다. 모델/공급자는 실제 SQLite UUID와 입력한 모델 ID를 저장하며 등록·목록·정책·선택으로 네트워크나 분석 작업을 생성하지 않는다.
| Tauri | Core | 입력/출력 |
|---|---|---|
| register_model | model.register | providerName→provider_name,kind,modelId→model_id,modalities / id,created |
| list_models | model.list | afterId→after_id / items,next_cursor (최대 10개·12KB 페이지) |
| inspect_model | model.inspect | id,allowExternal→allow_external / status,modalities,checkedAt,verified,inferenceCalled,metadataRequestAttempted 등 |
| model_credential | model.credential | id,action(save/delete/test),key?,allowExternal→allow_external / 고정 status,inferenceCalled |
| configure_model | model.policy | policy:{id,enabled,allow_external,allow_paid,budget_usd,max_requests} / enabled,policy |
| validate_model | model.validate | id,modality / compatible,reason 또는 비밀 없는 snapshot,inferenceCalled |
| select_model | model.select | id,modality / selected,profileVersion,inferenceCalled |

목록에 hasCredential(bool), inspection, policy, selected를 포함하며 키/원문 응답/예외를 반환하지 않는다. API 키는 ASCII 1~1024자·공백/제어문자 금지. 모델 ID 160자·공급자 80자, 등록 유형은 text/image/audio. 잘못된 입력은 INVALID_PARAMS, 조건 미충족은 MODEL_POLICY_DENIED/MODEL_UNAVAILABLE/MODEL_CAPABILITY_MISMATCH/BUDGET_EXCEEDED 고정 오류다. 아직 분석 실행 API는 제공하지 않는다.

## M06 분석 명령
| Tauri | Core | 입력/출력 |
|---|---|---|
| preview_analysis | analysis.preview | plan:{mode,scope,library_id,folder_parts,selected_ids,model_id} / targetCount,eligibleCount,unsupportedCount,overLimitCount,formats,missingCount,planToken,estimatedUpperBoundUsd,externalTransfer,paid,snapshot,inferenceCalled:false |
| start_analysis | analysis.start | request:{plan,plan_token,request_id,confirmed:true,confirm_external,confirm_paid} / 실제 jobId,reused |
| analysis_status | analysis.status | jobId→job_id / status,total,processed,succeeded,failed,canceled,active,needsRecovery,errors(처음 10개 고정 코드) |
| analysis_jobs | analysis.jobs | 인자 없음 / 최근 20개 실제 Job |
| cancel_analysis | analysis.cancel | jobId→job_id / cancelRequested,status |
| retry_analysis_plan | analysis.retry_plan | jobId→job_id / 과거 plan,requiresReview:true(새 Job 생성 없음) |
| asset_analysis | asset.analysis | assetId→asset_id / 활성 성공 결과·요청/실제 응답 모델·원본 해시·공급자 보고 비용 또는 null |
| asset_analysis_history | asset.analysis.history | assetId→asset_id,afterId→after_id / 최신순 run 1개,다음 cursor(UUID) |

mode는 all/unanalyzed/completed/failed/selected, scope는 folder/library/all이다. all 범위는 library_id=null·folder_parts=[], library 범위는 실제 활성 루트 UUID·빈 parts, folder는 실제 루트와 디렉터리 구성요소를 사용한다. selected_ids는 최대 200개 실제 활성 UUID이며 선택 범위와 교차한다. 범위 대상은 최대 1000개다. eligibleCount는 실제 stat·확장자·파일 크기를 통과한 이미지 후보 수이며 디코드 성공 보장이 아니다. missingCount는 권한/경로 포함 원본 확인 실패 수다.

미리보기 토큰은 실제 대상 stat/모델·한도·가격 상한을 결합한다. 승인된 동일 request_id·동일 payload 재전송은 기존 Job을 반환하고 예약·추론을 추가하지 않는다. 중단된 Job은 needsRecovery로 표시하며 조회/재연결만으로 재개하지 않는다. 정상 입력 준비를 마치지 못해 해시를 확정하지 않은 경우 inputFingerprint는 빈 값이며 해시를 추측하지 않는다. 토큰은 추정 결과와 승인 조건을 일치시키기 위한 값이고 사용자 인증을 대체하지 않는다.

## M07 임베딩 고정 명령
| Tauri | Core | 입력/출력 |
|---|---|---|
| embedding_configure | embedding.configure | modelName→model_name,prefixScheme→prefix_scheme(plain/embeddinggemma) / profile,inferenceCalled:false |
| embedding_status | embedding.status | 인자 없음 / profile,readyCount,inferenceCalled:false |
| embedding_start | embedding.start | selected:[{asset_id,result_id}],confirmed:true / jobId |
| embedding_query | embedding.query | query,mode(semantic/hybrid),confirmed:true,criteria / jobId |
| embedding_rebuild | embedding.rebuild | confirmed:true / jobId |
| embedding_work | embedding.work | jobId→job_id / id,kind,status,total,processed,failed,errors,error,results |

criteria는 library_id(UUID/null),folder_parts(구성요소 배열),kind(대문자 확장자),tag(사용자 태그),analysis(빈 값/unanalyzed/completed/failed)다. 생략 필드는 기본값을 사용한다. 결과는 실제 id,score,reason(semantic/keyword/hybrid),semanticScore와 선택적 keywordScore만 반환하며 벡터/원문 오류/질의 원문을 반환하지 않는다. 작업은 queued/running/completed/failed/canceled/interrupted이며 재시작 후 중단 상태를 조회만으로 재개하지 않는다. 생성·재구축·질의는 공유 임베딩 작업 슬롯 하나를 사용하며 경합 시 EMBEDDING_BUSY로 실패한다.

## M08 데스크톱 관리 명령
| Tauri | Core | 입력/출력 |
|---|---|---|
| mcp_connection | mcp.connection | 인자 없음 / brokerReady,transport,readOnly,configuration:{command,args,cwd} |
| mcp_audit | mcp.audit | afterId→after_id / 최근 10개 items,next_cursor |

이 두 명령은 Host에 노출하지 않는다. Host 도구 5개의 인자·반환값은 MCP.md에 정의하며 Core의 별도 고정 읽기 dispatch를 통과한다. 조회 결과 외의 DB 변경은 Core 감사 기록만 허용한다. Host 도구는 SQL/임의 Core 명령·AI 실행·임의 원본 파일 경로 인자를 받지 않는다. Bridge 실행 설정의 data-dir는 별도 세션 발견 경로다.


## R08B-01 기본 텍스트 편집 확장
- asset.annotations 결과에 aliases(string[]), originalName(string), revision(int)을 추가한다. 원본 이름은 스캔으로 기록한 assets.display_name으로 읽기 전용이다. 표시명 override와 별개이며 파일명 변경 명령은 없다.
- Tauri save_asset_annotation의 aliases/expectedRevision을 Core asset.annotate의 aliases/expected_revision으로 함께 보낸다. 표시명 128자·설명 1024자. 별칭은 최대 16개·각 64자·중복 제거 후 합계 512자, NFKC/양끝 공백 정리·casefold 중복 제거(첫 표기 보존), 제어문자/서로게이트 거부다. 빈 배열은 명시적 비움이다.
- v4 metadata_decisions의 basic_text 필드에 title/description/aliases 객체와 revision·이력을 저장하고 기존 주석/표시명·설명 FTS 투영을 같은 트랜잭션으로 갱신한다. 충돌은 고정 METADATA_CONFLICT로 전체 롤백한다. UI는 초안을 유지하며 명시적 ‘초안을 버리고 다시 불러오기’ 전에는 재저장을 막는다.
- 기존 3필드 요청은 별칭을 보존하며 현재 revision으로 저장한다. 구형 호출에는 낙관적 충돌 검사가 없고 새 UI는 항상 기대 revision을 보낸다. 메타데이터 전반의 충돌/이력 UI는 R08B-05 범위다.
- 별칭 검색 색인/필터는 M08E 범위. 벡터 입력은 기존 AI 결과만 사용하며 편집으로 벡터를 생성/변경하지 않는다. 기존 MCP get_asset.user에는 기본 정보의 추가 필드가 포함되며 쓰기 도구/내부 결정 이력을 노출하지 않는다.
# M08B 사용자 메타데이터 고정 명령

모두 기존 Core 요청/응답 봉투를 사용하며 MCP 읽기 도구에 쓰기를 노출하지 않는다. 등록·스캔·조회·메타데이터 저장은 AI/임베딩 작업을 생성하지 않는다. Tauri 인자는 camelCase, Core 인자는 snake_case다.

| Tauri 명령 | Core 메서드 | Core 입력 |
| --- | --- | --- |
| get_asset_management / save_asset_management | asset.management / asset.management.save | asset_id / asset_id,value,expected_revision |
| get_asset_composition / save_asset_composition | asset.composition / asset.composition.save | asset_id / asset_id,value,expected_revision |
| get_asset_relations / save_asset_relations | asset.relations / asset.relations.save | asset_id / asset_id,value,expected_revision |
| asset_link_candidates | asset.link.candidates | asset_id,kind(file/component/asset/incoming),after_id(UUID 또는 null) |
| asset_metadata_history | asset.metadata.history | asset_id,before_id(해당 에셋의 이력 정수 ID 또는 null) |

각 저장은 해당 필드의 revision을 비교하고 성공 시 value/revision을 반환한다. 불일치는 METADATA_CONFLICT이며 투영·결정·이력을 모두 보존한다. 값 계약은 METADATA_SCHEMA.md의 R08B 절을 따른다. 후보는 2개, 이력은 1개씩 실제 ID 커서로 페이지 처리한다. 이력은 field/revision/action/actor(user)/createdAt/before/after를 반환하며 각 값의 직렬화가 6,000바이트를 넘으면 truncated/preview를 명시한다. DB 원문은 유지한다.

asset.annotations는 tagsRevision도 반환한다. asset.tags는 expected_revision을 선택적으로 받으며 현재 UI는 반드시 전달한다. 기존 호출의 명시적 add/remove 및 batch 명령은 쓰기 잠금 안에서 최신 태그에 적용되고 각 에셋의 user_tags 이력을 기록한다. 이전 기본 텍스트 API의 레거시 호환 경로는 유지한다. 새로운 편집 UI는 읽은 revision을 항상 전달하며 충돌 시 초안을 유지하고 명시적 다시 불러오기를 제공한다.
## M08C 그룹·패키지 고정 명령

Tauri 인자는 camelCase, Core 인자는 snake_case이며 기존 안전 응답 봉투를 사용한다. 임의 함수 호출/SQL 실행 또는 MCP 쓰기 도구를 추가하지 않는다.

| Tauri | Core | 입력 |
| --- | --- | --- |
| group_list | asset.groups.list | after_id |
| group_create / group_update | asset.groups.create / update | value / group_id,value,expected_revision |
| group_delete / group_move | asset.groups.delete / move | group_id,expected_revision / group_id,parent_id,expected_revision |
| group_membership / group_assign | asset.groups.membership / assign | asset_id / asset_id,group_ids,expected_revision |
| group_query | asset.groups.query | group_id,query,criteria,after_id |
| group_batch_preview | asset.groups.batch_preview | asset_ids,add,remove,after_id |
| group_batch_apply | asset.groups.batch_apply | plan,confirmed=true |
| package_list | asset.packages.list | after_id |
| package_create / package_update | asset.packages.create / update | value / package_id,value,expected_revision |
| package_delete | asset.packages.delete | package_id,expected_revision |
| package_membership / package_assign | asset.packages.membership / assign | asset_id / asset_id,package_ids,expected_revision |
| package_defaults | asset.packages.defaults | package_id,value,expected_revision |
| package_effective / package_override | asset.packages.effective / override | asset_id / asset_id,value,expected_revision,expected_packages |

그룹/패키지 목록은 2개씩 UUID 커서, 그룹 검색은 필터 적용 후 200개씩 UUID 커서다. 전체 그룹/패키지 목록 로드 실패 시 확인되지 않은 항목을 빈 목록으로 저장하지 않는다. 소속 조회는 아직 목록에서 로드하지 않은 ID도 포함하고 클라이언트는 이를 보존한다. 요약 이름은 64자로 줄여 전송 크기를 제한한다.

일괄 검토는 최대 100개 실제 활성 에셋의 소속 버전과 추가/해제 그룹 버전을 포함하는 plan, 이전/이후 소속 2개씩, next_cursor를 반환한다. 검토만으로 기록을 변경하지 않는다. 적용 시 plan을 DB 현재 상태에서 다시 계산해 전체 일치해야 하며, 하나라도 충돌/실패하면 전체 롤백한다. 기본 값 계약·불변 구매 당시 기록·다중 패키지 충돌 규칙은 METADATA_SCHEMA.md를 따른다. 선언된 금액/통화/라이선스명은 검증된 구매·권리 증명으로 표시하지 않는다.

## R08D-01 제작 주체 사전 Core API

개인/팀/회사는 공유 주체의 유형이며 제작자/제작사/배포사 역할 연결은 R08D-02에서 제공한다. 아래 명령은 Core 안전 응답 봉투와 Rust 내부 명령 허용 목록에 추가했다. Tauri UI 명령/관리 화면·MCP 쓰기 도구는 추가하지 않는다.

| Core | 입력 | 응답 data |
| --- | --- | --- |
| `creator.list` | `after_id`: null/실제 UUID, `include_disabled`: bool | items(최대 2개), next_cursor |
| `creator.get` | `creator_id,include_private?,confirmed?` | 공개 요약 / 승인한 private 원문 |
| `creator.create` | `value` | 새 UUID·전체 정보·enabled=true·revision=1 |
| `creator.update` | `creator_id,value,expected_revision` | 같은 UUID의 갱신된 정보·revision+1 |
| `creator.set_enabled` | `creator_id,enabled,expected_revision` | 비활성/복원된 정보·revision+1; 동일 상태는 revision/감사 추가 없이 반환 |

입력 객체의 키는 표와 정확히 일치해야 한다. value는 `name,kind,brand,homepageUrl,profileUrl,contact,country,description` 8개 필드를 모두 받으며 선택 정보는 빈 문자열이다. 상세 값 계약은 METADATA_SCHEMA의 R08D-01 절을 따른다. 목록은 `id,name,kind,brand,country,enabled,revision`만 반환하고 연락처·URL·설명을 포함하지 않는다. 민감 정보는 R08D-05의 승인된 private get에서만 제공하고 쓰기 응답도 공개 요약이다. 비활성 주체도 get으로 조회·수정·복원 가능하며 삭제 API는 없다.

커서는 실제 존재하는 UUID여야 하며 UUID 오름차순 keyset이다. 같은 이름의 서로 다른 주체는 별도 UUID로 보존한다. 잘못된 필드/UUID/유형/URL은 INVALID_PARAMS, 오래된 revision은 METADATA_CONFLICT, SQL 오류는 비밀 없는 DB_UNAVAILABLE이다. 쓰기·레드랙션 감사 기록은 같은 BEGIN IMMEDIATE 트랜잭션이며 한쪽 실패 시 전체 롤백한다. 조회·저장·활성 변경으로 URL 접속·스캔·AI/임베딩·외부 과금을 시작하지 않는다.

## R08D-02 주체 역할 연결 (v8)
`creator.links {subject}`와 `creator.links.save {subject,links,expected_revision}`를 Core/Rust 내부 허용 목록에 추가한다. subject는 `{kind:asset|package,id:실제 UUID}`, links는 최대 16개 `{creator_id,role}`이며 role은 creator(제작자)/producer(제작사)/distributor(배포사)다. 중복 역할 쌍·미지 주체·새 비활성 주체 연결은 거부하며 이미 연결된 비활성 주체는 유지/해제할 수 있다. 응답은 링크 버전과 현재 주체의 공개 요약이며 이름/브랜드는 64자 요약이다. 연락처/URL을 반환하지 않는다. 공유 정보 수정은 live 조회에 반영하고 구매 스냅샷/AI/원본은 변경하지 않는다. 링크·버전·불변 provenance_history·원문 없는 감사는 한 트랜잭션이다. UI는 M08E, Rust/설치 통합 회귀는 M08D 최종 검증에서 수행한다.

## R08D-03 출처·상품·구매 기록 (v9)
`source.list/get/create/update/delete`를 Core/Rust 내부 경로로 제공한다. create는 `{subject,value}`, update는 `{record_id,value,expected_revision}`, delete는 `{record_id,expected_revision,confirmed:true}`다. get은 `{record_id,include_private?:bool,confirmed?:bool}`, list는 `{subject,after_id}`(최대 2개)다. 삭제는 행/이력을 보존하는 비활성화다.
value는 `site,productName,originalUrl,productUrl,downloadUrl,purchase:{amount,currency,purchasedOn,downloadedOn}`다. site 128자, 상품명 256자, URL 각 512자, ISO 날짜/최대 정수 12자리·소수 4자리의 음수 없는 금액 문자열을 받는다. 미확인 금액은 null, 무료는 문자열 0이며 금액 지정 시 대문자 3자리 통화가 필요하다. 빈 날짜는 미확인이다. URL은 HTTPS/호스트/포트/userinfo·제어문자 검증 후 저장만 하며 서명 쿼리를 포함할 수 있다. 기본 응답/목록은 사이트·상품명만 공개한다. URL·구매 정보와 private 응답의 priceState(unknown/free/paid)는 `include_private:true,confirmed:true`인 명시 get에서만 제공한다. 이것은 구매/권리 확인 증명이 아니다. 기존 패키지 구매 스냅샷은 소급 변경하지 않는다.

## R08D-04 라이선스·증빙 (v10)
`license.list/get/create/update/delete`는 source API와 같은 소유 범위/커서/레코드 버전을 사용한다. 생성/수정에는 `confirmed:true`가 필수다. value는 `label(128),terms(1024),attribution(256),reviewStatus(unknown|needs_review|user_reviewed),scope(128),note(256),source_id(null 또는 같은 소유 범위의 실제 출처 UUID)`다. 조건/표시문/메모는 줄바꿈·탭을 허용하고 다른 제어문자는 거부한다. reviewStatus는 사용자의 선언이며 응답 permission은 항상 unknown, declaredBy는 user다. AI/추론으로 확정하는 API는 없다.
`license.evidence.save {record_id,files:[{file_id,label}],expected_revision,confirmed:true}`는 최대 8개의 실제 등록 파일(증빙 표시명 64자)을 명시 연결한다. 대상 에셋의 연결 파일 또는 패키지 멤버 에셋의 연결 파일이어야 하고 활성 라이브러리/루트 내부 경로·리파스/링크·현재 파일 존재를 재검증한다. URL/임의 경로로 증빙을 받거나 파일을 읽어 추출·복사·수정하지 않는다. 기본 응답에는 조건/메모/출처·증빙 참조를 제외하고 개수만 표시한다. 명시 승인 private get에서 조건/표시문·증빙 ID/표시명/가용성을 제공하며 절대 경로는 반환하지 않는다. 연결 해제/파일 누락 뒤 기존 증빙은 unavailable로 보존하고 FK가 참조 삭제를 막는다.

## R08D-05 최종 개인정보·이력·삭제 계약 (v11, 앞선 사전 계약의 보안 강화)

`creator.get`은 기본 공개 요약으로 바뀌며 연락처/홈페이지/프로필/설명은 `include_private:true,confirmed:true`인 get만 반환한다. creator 생성/수정/활성 변경 응답도 공개 요약이다. source/license get도 동일한 private 승인 규칙을 따른다. 원문은 일반 감사/오류/MCP에 복제하지 않는다.

- `provenance.history {subject,after_id,include_private?,confirmed?}`: asset/package/creator 실제 ID의 append-only 변경 전후 값, entityId/필드/revision/행위/actor=user/시각을 1개씩 반환한다. 기본은 공개 필드 투영이다. 각 승인된 원문 스냅샷이 4,000 UTF-8 바이트를 넘으면 truncated/byteLength/256자 preview를 명시하며 DB 원문은 보존한다. 과거에 기록하지 않은 원문 이력을 마이그레이션으로 만들어내지 않는다.
- `provenance.export {subject,kind:creators|sources|licenses,after_id,include_private?,confirmed?}`: schemaVersion=1의 **읽기 전용 JSON 투영**을 1개씩 반환한다. 기본 연락처/URL/금액/구매일·다운로드일/라이선스 메모·조건/증빙 참조 제외. private 선택은 명시 승인 필수다. 파일 내보내기·CSV/가져오기는 M08G 범위이며 이 API가 파일 쓰기·URL 접속·AI를 실행하지 않는다.
- `creator.delete.preview {creator_id}` → `{creator_id,revision,assetLinks,packageLinks,canDelete}`; `creator.delete {plan,confirmed:true}`는 같은 트랜잭션에서 현재 plan을 재계산한다. 참조가 있으면 거부하고 없으면 행/이력을 보존하는 deleted tombstone이다. 원본/에셋/패키지/분석을 삭제하지 않고 tombstone은 복원/수정하지 않는다. 비활성화/복원과 구분한다. 비활성 패키지·라이브러리의 기존 링크도 보존하며 명시 save로 기존 연결의 제거만 허용한다(새 연결 금지).
- `source.delete.preview` / `license.delete.preview {record_id}`: revision/참조 수·참조 보존·원본 변경 없음 반환. delete는 기존 인자에 `expected_references`를 받으며 기본 0이다. 참조가 있으면 preview에서 확인한 수를 명시해야 하고 변경됐으면 METADATA_CONFLICT다. 승인된 삭제는 비활성 처리하며 licence→source FK와 증빙 파일 ID/이력은 유지한다. 원본 파일은 삭제하지 않는다.

v11은 제작 주체의 참조 있는 삭제/물리 삭제/tombstone 수정, 출처·라이선스 물리 삭제/소유자 변경, 증빙 행의 직접 UPDATE를 DB 트리거로 막는다. 이력 원문·연락처/서명 URL은 로컬 DB와 백업에 일반 데이터로 남으며 자격 증명 저장소/암호화 비밀 저장소를 제공한다는 뜻은 아니다. 기존 API 키는 기존 Credential Manager 정책을 따른다. 신규 UI/Tauri 화면 명령·MCP 쓰기는 추가하지 않았다.

## M08E — 통합 탐색·편집·검색 (R08E-01~06)

Tauri `metadata_request {method,params}`는 main 창과 고정 메타데이터 명령만 허용한다. Core도 별도 고정 목록으로 검증한다. 임의 SQL·모델 호출·스캔을 이 명령으로 전달할 수 없다. 기존 creator/source/license/provenance API를 사용하며, 원문 get/history는 기존 include_private+confirmed 정책을 유지한다. 편집은 명시 저장/취소·기대 revision/실제 영향 plan으로 처리하고 충돌 시 초안을 보존한다.

| Core 명령 | 입력 | 응답/한도 |
| --- | --- | --- |
| catalog.options | kind,after_id,version?,include_inactive? | groups/packages/creators/tags/types/facets/formats/license_labels 공개 선택값 20개/페이지. 분류는 지정 불변 버전 또는 최신 버전. 비활성은 기본 제외 |
| catalog.scope | kind(groups/packages/types),id,after_id | 실제 소속/하위 분류 에셋 UUID 200개/페이지 |
| catalog.classification | asset_id | 대표/탐색/독립 축·type/facet 버전·revision·source/status |
| catalog.classification.save | asset_id,value,expected_revision,confirmed | 실제 사전 FK와 사용자 확정/명시 clear, 원자 이력·색인 갱신 |
| catalog.evidence_candidates | subject,after_id | 대상 에셋/패키지에 이미 연결된 파일 ID/이름 20개. 원본 경로/스캔 없음 |
| catalog.term.get | kind(type/facet),code | 최신 base_version/value/usedAssets |
| catalog.term.save | kind,base_version,value,expected_usage,confirmed | 불변 새 사전 버전. value=code/axis/ko/en/aliases/active/replacement. 이름·별칭 한도64, alias 최대8. 사용 중 facet 비활성은 동일 축 활성 대체값 필수 |
| catalog.tag.get | tag_id | label/enabled/revision과 userAssets(asset_id/revision)/aiReferences/canDelete plan |
| catalog.tag.save | tag_id(null=신규),value(label/enabled),plan,confirmed | 공유 사용자 태그 결정/revision·이력/색인을 함께 갱신. AI 결과 보존. 사용자 영향 최대100개 |
| catalog.tag.delete | plan,confirmed | 사용자/AI 참조 없는 실제 태그만 삭제. 참조가 있으면 거부 |
| catalog.query | query,criteria,after_id,sort? | 아래 조건·정렬 적용 후 ids 최대200개, next_cursor, inferenceCalled=false |
| catalog.order | asset_ids,sort | 활성 루트의 실제 ID 최대100개를 정렬. 중복/없는 ID 거부. source/relevance는 전달 순위 보존. 모델 호출 없음 |

`catalog.query`는 활성 에셋 최대10,000개를 대상으로 공개 catalog_documents의 NFKC/casefold literal 단어 AND 검색과 복합 조건을 수행한다. 10,000개를 넘으면 CATALOG_LIMIT으로 실패하며 일부 결과를 전체 결과처럼 반환하지 않는다. query 최대256자/16단어, 조건 배열은 각각 최대16개다. 한 축 OR·축 사이 AND이며 **필터와 정렬 후** 페이지를 자른다. 빈 query는 조건/정렬 조회다. sort 기본 source(UUID)이며 name/kind/modified/analysis/size/size_desc/registered/registered_asc/creator/relevance를 허용한다.

criteria는 기존 library_id/folder_parts/kind/tag/analysis/group_id와 group_ids/package_ids/types/creator_ids/creator_roles/roles/styles/genres/views/dimensions/engines/tags/formats/license_labels/license_status/management_states/purchase_status, purchase_currency, include_descendants, favorite, availability를 지원한다. group/package/creator/tag 배열은 실제 UUID이며 `__unknown__`은 소속/값 없음 선택이다. 유형은 대표+탐색 분류와 계층을 조회한다. creator_roles는 creator/producer/distributor, license_status는 unknown/needs_review/user_reviewed, 관리 상태는 unreviewed/reviewing/approved/archived, 구매 상태는 unknown/free/paid다. 구매 상태와 대문자3자리 통화는 **같은 현재 선언 기록**에 적용한다. 에셋/활성 공유 패키지 출처와 현재 package 구매 선언을 조회하며 과거 구매 스냅샷이나 비활성 출처는 조건에 포함하지 않는다. 조건 응답/커서/FTS에 구매 금액·날짜·URL 원문을 노출하지 않는다. 엔진/권리/구매 필터는 사용자 선언에 대한 조회이며 호환성·사용 권한 판정이 아니다.

수치 조건 min_/max_ size/rating/width/height/duration은 정수·안전 범위와 최솟값≤최댓값을 검사한다. rating은1~5다. size_unknown/rating_unknown/technical_unknown은 범위와 함께 미확인을 OR 포함하고, 범위가 없으면 미확인만 선택한다. 기술은 가용한 연결 파일의 관측값 최댓값이며 재추출/파일 접근은 없다. availability=available/partial/missing은 인덱스의 존재 상태다. size는 가용한 **고유 file ID** 합계이며 여러 역할로 연결되어도 중복 합산하지 않는다. 일부 누락이면 가용분 합계, 전부 누락/집계 불가면 null로0과 구분한다.

등록일은 assets.created_at, 수정일은 구성 파일의 실제 인덱스 mtime_ns·에셋/주석/결정/공개 색인·직접/공유 provenance 변경시각의 최댓값이다. 파일시각은 정수 ns로 비교한다. 제작사는 연결된 producer 이름 우선, 없으면 다른 제작 역할 이름의 정규화 최솟값을 사용한다. 미확인은 양방향 모두 마지막, 동일 키는 UUID 오름차순이다. 키워드 relevance는 공개 텍스트의 literal 단어 빈도이고 확률이 아니다. 의미 검색은 기존 **명시 실행**과 조건 선적용을 유지하며, 추가 정렬은 반환된 상위50개 안에서만 한다. 정렬 변경은 임베딩을 생성하지 않는다.

catalog.query 커서는 query/정규화 조건/sort 해시·DB 변경 stamp·마지막 UUID를 담은 최대512자 불투명 값이다. 조회 문맥·DB 변경/프로세스 재시작 후 재사용은 METADATA_CONFLICT이며 처음부터 다시 조회해야 한다. 조회는 DB를 쓰지 않는다. UI는 전 페이지 성공 후 원자 반영하고 잘못된/반복 커서·중복 ID·조회 오류에는 결과 범위를 넓히지 않는다. 선택은 실제 ID로 유지하며 정렬 변경 시 첫 페이지, 결과 갱신 시 유효 페이지로 보정한다. 필터/정렬/탐색 선택은 같은 앱 세션 내 복원한다. 앱 재시작 영속 환경설정은 추가하지 않았다.

공개 FTS는 이름/별칭/설명/사용자 태그/활성 AI 텍스트·유형/선조/독립 축·그룹 선조·패키지명/버전·주체 이름/브랜드/역할을 포함한다. 연락처·URL·구매·라이선스 조건/메모·증빙은 포함하지 않는다. 일반 FTS는 기존 SearchService, 복합 query는 같은 공개 projection을 사용한다. MCP 신규 확장 메타데이터 필터/쓰기 도구는 제공하지 않으며 M08H 범위로 남긴다.

## M08F — 명시적 다중 형식 분석·기술 수집

- `analysis.preview`의 선택적 `input_kind`: image(기존 기본), audio, threeD, animation, text. 원래 mode/scope/selected_ids 경계와 승인/비용 토큰은 유지한다. threeD/animation은 image 모델, audio는 OpenRouter audio 모델만 지원한다. 후보 개수는 실행 시 디코드 성공을 보증하지 않는다.
- snapshot.analysisContract는 버전·유형 행렬·사전/스키마/프롬프트/검토 입력 지문·전송/한도를 가진다. 실제 실행은 원본 바이트 SHA-256을 별도로 기록한다. `analysis.status.partialSuccess`는 성공과 실패/취소가 혼재할 때 true다.
- `asset.technical({asset_id})` → observation/stale/inferenceCalled(false). 조회는 파일을 읽어 파싱하거나 작업을 생성하지 않고 저장 관측과 현재 stat만 확인한다.
- `asset.technical.collect({asset_id,confirmed:true})` → 같은 응답. 명시 기술 파서만 수행하며 원본 무변경·AI/임베딩 호출0. 미지원/잘못된 형식은 고정 오류 코드이며 claim/수치/구성 요소는 원자 저장한다.
- `asset.analysis`는 기존 응답에 features(technical/suggestions/audioSuggestions/suggestionStatus/schema), contractVersion을 추가한다. 기존 결과에 features가 없으면 기존 표시를 유지한다.
- `analysis.review({asset_id,result_id})` → 실제 결과 기반 before/after/expectedRevision/planToken/hasChanges. 조회만 수행한다. `analysis.review.apply({asset_id,result_id,expected_revision,plan_token,confirmed:true})`는 검토한 대표 분류/역할/스타일만 사용자 값으로 확정한다. conflict는 재검토가 필요하다. 실제 저장 결과 없는 ID를 추측·합성하지 않는다.
- `embedding.status.staleCount`: 현재 프로필의 저장 벡터 중 현재 공개 문서 지문/유효성에 맞지 않는 개수. 자동 생성/재구축/삭제를 하지 않는다.

새 기술/확정 명령은 데스크톱 main 창의 고정 IPC 허용 목록에만 추가하며 MCP 도구/쓰기 권한을 확장하지 않는다. 지원 행렬과 payload 경계는 [ANALYSIS_SUPPORT](ANALYSIS_SUPPORT.md)를 따른다.

## M08G — 일괄·교환·해시
`bulk.preview/apply`, `exchange.export/preview/apply`, `duplicates.start/list/status/cancel/candidates`는 main 창 metadata_request와 Core 고정 허용 목록에만 추가했다. 요청 키·버전/토큰·페이지/상한·원자성·개인정보·중단 복구는 [BATCH_METADATA](BATCH_METADATA.md)를 따른다. 모델/임베딩/원본 쓰기·경로 등록·외부 URL 접속을 호출하지 않고 MCP 권한은 확장하지 않는다.
