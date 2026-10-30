# API_CONTRACTS — 내부 유스케이스 계약 초안

> 이 표는 아직 배포된 엔드포인트가 아닌 **구현 대상 인터페이스 계약**이다. UI/Tauri/Sidecar 통신은 설치본의 보안과 호환성에 맞춰 실제 전송 형태를 확정한다.

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
| `creator.get` | `creator_id` | 실제 주체의 전체 정보 |
| `creator.create` | `value` | 새 UUID·전체 정보·enabled=true·revision=1 |
| `creator.update` | `creator_id,value,expected_revision` | 같은 UUID의 갱신된 정보·revision+1 |
| `creator.set_enabled` | `creator_id,enabled,expected_revision` | 비활성/복원된 정보·revision+1; 동일 상태는 revision/감사 추가 없이 반환 |

입력 객체의 키는 표와 정확히 일치해야 한다. value는 `name,kind,brand,homepageUrl,profileUrl,contact,country,description` 8개 필드를 모두 받으며 선택 정보는 빈 문자열이다. 상세 값 계약은 METADATA_SCHEMA의 R08D-01 절을 따른다. 목록은 `id,name,kind,brand,country,enabled,revision`만 반환하고 연락처·URL·설명을 포함하지 않는다. 전체 정보는 명시적인 get/쓰기 응답으로만 제공한다. 비활성 주체도 get으로 조회·수정·복원 가능하며 삭제 API는 없다.

커서는 실제 존재하는 UUID여야 하며 UUID 오름차순 keyset이다. 같은 이름의 서로 다른 주체는 별도 UUID로 보존한다. 잘못된 필드/UUID/유형/URL은 INVALID_PARAMS, 오래된 revision은 METADATA_CONFLICT, SQL 오류는 비밀 없는 DB_UNAVAILABLE이다. 쓰기·레드랙션 감사 기록은 같은 BEGIN IMMEDIATE 트랜잭션이며 한쪽 실패 시 전체 롤백한다. 조회·저장·활성 변경으로 URL 접속·스캔·AI/임베딩·외부 과금을 시작하지 않는다.
