# UNITY_INTEGRATION — Unity Editor 자동 개발 연동

## 성공의 의미
MCP가 검색 결과를 말해주는 것에서 끝나지 않는다. **Unity Editor에서 실제 프로젝트 파일 임포트와 씬 오브젝트 생성/배치를 실행하고 결과를 다시 전달**해야 한다.

## 구성과 역할
- AI Asset Hub: 적합 에셋 검색, 원본 경로/파일 관계, 실행 계획 생성, 작업 추적.
- Unity Editor Connector(C# Editor 전용 패키지): 프로젝트 식별, 대상 경로 검사, Unity `AssetDatabase` 임포트, 프리팹/오브젝트 생성, 씬 배치 및 결과 보고.
- AI Host(Codex 등): 사용자 자연어 명령 해석, MCP 도구 계획·호출.
- 새 Unity 프로젝트 열기/닫기, 편집기 플레이 상태, 씬 저장 여부를 실제로 검사한다.

## P0 1차 실제 동작 범위
1. **PNG 이미지** 1개를 Unity Editor 프로젝트 `Assets/AIAssetHub/`의 고유 경로로 복사하고 임포트.
2. Unity 프로젝트에서 `AssetDatabase`로 임포트 결과 확인.
3. 배치 가능한 2D Sprite 형태로 설정해 GameObject 생성, 현재 테스트 씬에 배치.
4. 작업 결과를 프로젝트 경로·Unity asset path·객체 식별자·씬 경로와 함께 반환.
5. 다음 단계에서 다중 PNG, 텍스처, FBX/OBJ, 프리팹 등 지원 확대.

## 핵심 동작 순서
```text
Codex: '숲 배경에 사용할 에셋 배치'
    ↓ search_assets / get_asset
AI Asset Hub: asset_id + 실제 파일 + 분석 설명
    ↓ preview_unity_import / placement
사용자/호스트: 대상 Unity 프로젝트 및 수행 승인
    ↓ import_assets_to_unity
Unity Editor Connector: 파일 경로 안전 검증 → 복사 → AssetDatabase.ImportAsset
    ↓ place_assets_in_unity
Unity Editor: 객체 생성 → 위치/회전/크기 설정 → 씬 변경 확인
    ↓ get_operation_status
Codex: 실제 임포트된 파일 / 생성된 오브젝트 / 실패 항목 보고
```

## 세부 계약
- Unity 프로젝트 인식: Editor에서 현재 열린 프로젝트만 기본 허용, 버전·프로젝트 경로·씬 식별.
- 임포트: 프로젝트 내부 `Assets/AIAssetHub` 등 허용 영역. 같은 이름은 자동 덮어쓰지 않고 고유 파일명 또는 확인 후 처리.
- 파일 의존성: 3D 모델 재질/텍스처 등 관련 파일 분석 후 누락 경고, 지원 범위를 벗어나면 실패 이유.
- 배치: 생성 타입, transform 위치/회전/스케일, 씬 경로, 부모 오브젝트, 이름 지정.
- 씬 저장: 사용자 변경 사항과 충돌 방지, 자동 저장 정책은 별도 설정/명시적 승인.
- Undo/복구: Unity의 Undo 가능한 작업 활용, 원본 파일을 임의 덮어쓰지 않음, 실패 시 부분 임포트 흔적 보고.
- Unity Editor가 연결되지 않거나 플레이 중이며 작업 불가하면 명확하게 오류 반환.

## 확장 포인트

### R08H-03 — 읽기 전용 계획 메타데이터 계약 (2026-11-04)
`unity-planning.v1`은 Editor 실행과 분리된 Core 내부 계약이다. `get_asset(schema_version=2).unityPlanning`은 실제 assetId, compatibility(status=unknown/declaredEngine/editorVerified=false), rights(permission=unknown/reviewRequired=true/공개 declarations), project(status=not-connected), executable=false, requiresExecutionApproval=true를 반환한다. 버전1에는 추가하지 않는다. 직접 에셋 및 활성 소속 패키지의 라이선스 ID/소유자/리비전/label/scope/reviewStatus만 공개하며 terms/attribution/note/출처/증빙은 제외한다. user_reviewed도 사용 허가나 법률 판정을 뜻하지 않는다. 상속 엔진 선언의 conflict를 보존하며 Unity 선언도 실제 호환 성공으로 승격하지 않는다. 라이선스20건 초과는 MCP_SEARCH_LIMIT로 실패한다.

`UnityMetadata(database, allowed_projects=()).preview({asset_id,project_path})`는 신뢰된 Core 호출자 전용이다. 기본 허용 목록은 비어 있으며 목록 대조 전에 입력 프로젝트를 탐색하지 않는다. 허용된 로컬 프로젝트의 전체 부모 리파스/링크·Assets 디렉터리·ProjectSettings/ProjectVersion.txt(최대512자/바이트, m_EditorVersion 선언)를 확인한다. source/dependency 역할의 실제 등록 파일에 대해 현재 가용성·저장 기술 stale·미선택/미해결 종속·목적지 Assets/AIAssetHub의 기존 파일/.meta/동일 이름 충돌·엔진 선언 상충을 표시한다. preview/evidence는 복사 대상에서 제외한다. 결과 project.status=filesystem-validated는 폴더 구조 확인이며 editorConnected=false를 유지한다. 디렉터리 생성/파일 복사/임포트/프로세스 실행/AI/DB 변경을 하지 않는다. 원문 예외 대신 INVALID_PARAMS/UNITY_PROJECT_NOT_ALLOWED/UNITY_PROJECT_UNAVAILABLE로 실패한다. 이 결과는 실행 승인 토큰이 아니며 재검증/실행 정책은 M09에서 구현한다.

프로젝트 경로·허용 목록을 받는 공개 MCP/Tauri 명령이나 새 도구는 추가하지 않았다. 실제 열린 Editor 대상/허용 목록 UI·프로젝트 식별/연결·작업 생성/실행은 R09-01 이후다. 신뢰된 allowlist 주입과 실제 임시 프로젝트/파일 fixture를 사용하는 내부 테스트로 이 계약을 검증하며 사용자 프로젝트/Editor 성공을 가정하지 않는다.

`TargetToolConnector` 인터페이스: `discover_targets()`, `plan_import()`, `execute_import()`, `plan_place()`, `execute_place()`, `get_status()`.

Unity를 1차 구현하고 Godot/Unreal/Blender 등은 **확장 가능성만 확보**한다. 지원한다고 선전하기 전에 실제 연결·임포트·결과 확인 테스트 필요.

## 실증 시나리오
- 실제 로컬 PNG가 분석·검색되며 Codex가 MCP로 선택 → 지정된 Unity 프로젝트에 임포트 → 씬에 배치 → Unity Editor UI에서 오브젝트 확인 → MCP 결과에 같은 파일과 오브젝트가 표시된다.

## M09 구현 계약 (D-035, 2026-11-06)

### 설치와 연결
Windows Unity6000.6.8f1에서 실제 검증하며 패키지의 최소 버전은 6000.6이다. 다른 Unity 버전·OS는 미검증이다. 설치본은 `unity-package/package.json`과 Editor 코드를 동봉한다. 앱 상단 **Unity 연결**에 표시한 실제 package.json을 Unity Package Manager의 **Add package from disk**로 등록하고 프로젝트를 연다. 앱에서 프로젝트 루트 경로를 입력해 **프로젝트 접근 허용**을 실행한다. 프로젝트나 패키지를 자동 설치·열기·수정하지 않는다. 연결 조회는 허용한 최대10개 프로젝트만 탐색하며 최근10초 이내 Editor heartbeat를 확인한다. 상태의 PID·버전·프로젝트·씬은 Editor가 게시한 실제 값이다.

`Library/AIAssetHub`의 디렉터리/각 JSON 파일은 현재 Windows 사용자와 SYSTEM만 허용한 보호 DACL을 사용한다. Editor 세션마다 새 UUID/256비트 토큰을 생성하며 Core는 허용 프로젝트·전체 부모의 리파스/링크·프로젝트 버전·DACL·시각/세션을 검증한다. 파일 이름은 실제 요청 UUID만 사용한다. request/result 최대16KiB, 요청 실행 기한60초, 메인 스레드 tick은0.1초 간격이다. 기존 결과/started 표식은 재실행하지 않는다. descriptor는 보호된 임시 파일을 MoveFileEx로 원자 교체해 ACL 병합 경합을 피한다. 네트워크 포트·Editor 프로세스 시작 API·외부 URL 접속은 없다. 같은 OS 사용자 권한으로 이미 실행되는 악성 프로그램을 격리하는 별도 보안 경계는 아니다.

### 임포트와 배치
미리보기는 최대20개의 **source 역할 파일이 하나인 단일 PNG 에셋**만 받는다. 다른 형식/다중 구성/의존성/애니메이션 PNG·프로젝트 내부 원본은 거부한다. 파일당16MiB·작업당64MiB·이미지16777216픽셀 한도다. 실제 fileId로 `Assets/AIAssetHub/<fileId>.png`를 구성하며 파일·`.meta`·디렉터리/리파스 충돌을 거부한다. 명시적 계획에서만 PNG를 읽어 검증·해시하고 카탈로그/원본/AI를 변경하지 않는다. 검토 계획은 Core settings에 최대20개, 5분간 보존한다. Core 응답 예상 크기가12KB를 넘으면 대상을 줄이도록 UNITY_LIMIT를 반환한다. 긴 씬 경로/이름의 다건 배치는 이 응답 한도로20개보다 적게 제한될 수 있다.

실행은 `confirmed`, `rights_confirmed`, `compatibility_confirmed`가 모두 true여야 한다. unknown 권리/호환을 허가/실제 성공으로 바꾸지 않는다. 세션·등록/구성·원본 해시·목적지를 재검사하고 하나의 계획은 한 번만 소비한다. 호출자 request_id 재사용은 같은 작업을 반환하며 다른 계획에 재사용할 수 없다. Core가 기존 unity_operations 테이블에 첫 에셋ID와 배치 전체 계획/결과 snapshot을 영속 기록한다. 새 DB 마이그레이션이나 Unity의 SQLite 쓰기는 없다. Editor는 원본을 다시 해시하고 FileMode.CreateNew로 복사한 뒤 AssetDatabase 동기 임포트·Sprite 모드 재임포트·실제 Sprite/GUID를 검증한다. 기존 파일/.meta를 덮어쓰거나 원본을 이동/삭제하지 않는다.

배치는 **현재 같은 Editor 세션에서 성공한 임포트 항목**만 사용한다. 미리보기 시 활성 씬 경로/handle/변경 revision을 묶고 실행 시 Core와 Editor 양쪽에서 확인한다. 플레이/컴파일/Prefab stage·씬 변경 시 거부한다. XYZ 위치/도 단위 Euler 회전/로컬 크기·객체 이름을 받고 현재 활성 씬 루트에 SpriteRenderer GameObject를 만든다. 부모 지정/프리팹/3D는 이 P0에 없다. Undo 그룹을 등록하고 씬을 dirty로 남긴다. **씬 저장은 구현하지 않으며 사용자가 Editor에서 저장한다.** 실제 `EntityId.ToULong`의 64비트 값을 손실 없는 문자열로 반환하며 `session:<uuid>:entity:<id>`는 해당 Editor 세션의 식별자다. 저장된 영구 씬 오브젝트 ID나 재시작 후 객체 존재 보장이 아니다. [Unity EntityId 이전 안내](https://docs.unity.com/en-us/engine/6000.6/manual/scripting/get-started/instanceid-to-entityid-migration).

### 상태·취소·재시작
MCP의 실제 이름/인자는 [MCP](MCP.md)의 표를 따른다. 갤러리에서 선택→Unity 대상 조회→미리보기→권리/호환 검토→실행, 결과 조회 후 Sprite 배치 미리보기/승인을 제공한다. Core의 `unity.*`는 Tauri main 창 고정 허용 목록으로 제한하고 MCP에는 프로젝트 등록/해제를 공개하지 않는다.

`queued`는 승인 요청 전달, `succeeded/failed/partial/cancelled`는 검증한 Editor 결과다. 항목별 복사 여부·실제 assetPath/GUID·객체ID/transform·고정 오류를 반환한다. 전송/프로세스 단절·기한 초과의 `unknown`은 이미 적용되었을 수 있으며 자동 재전송/재분석/삭제하지 않는다. `cancelRequested`는 다음 항목부터 중지하는 요청이며 실제 취소 성공과 구분한다. 이미 임포트/배치한 항목은 남고, 실패 복사 흔적은 `copied=true`와 경로로 보고한다. 에셋 파일 임포트 자체의 Undo 삭제는 하지 않으며 씬 배치는 Unity Undo를 지원한다.

앱 재시작 후 Unity 연결의 **작업 기록 조회**에서 실제 작업ID를 다시 조회한다. terminal 결과는 Core DB에서 보존하며 새 Core 세션에서도 읽을 수 있다. 진행 요청을 자동 재실행하지 않는다. Editor 종료/도메인 reload는 새 세션이므로 기존 미완료 요청 결과가 확인되지 않으면 unknown이다. 프로젝트 접근 해제는 신규 계획/실행/채널 접근을 차단하며 이미 승인·전달된 작업을 되돌리거나 자동 삭제하지 않는다. 해당 작업의 종료 결과를 먼저 조회하거나 취소한 뒤 해제해야 한다.

### 자동 검증 경계
`scripts/verify-unity.py`는 소스 Core+실제 batchmode Editor, `scripts/verify-unity-host.py`는 설치된 Core·stdio Bridge·공식 SDK reference Host·동봉 패키지·실제 batchmode Editor를 검사한다. 테스트 전용 harness만 격리 프로젝트에 복사하며 pause/finish 표식은 제품 코드에서 읽지 않는다. 합성 PNG 검색→명시 계획/승인→실제 임포트/GUID→Sprite/위치·회전·크기/dirty→Undo, 부분 실패/충돌 보존·다건 취소·Core 재시작/감사/원본 SHA256을 검증한다. [batchmode 공식 문서](https://docs.unity.com/en-us/engine/6000.6/manual/unity-editor/command-line-arguments/editor). 특정 Codex/Claude 제품의 개인 설정·LLM 추론·사용자 씬·GUI/OS 배치/다른 Unity 버전·대규모 성능은 검증하지 않는다. 위 과거 UI 실증 문구보다 D-019의 내부 자동화를 우선한다.
