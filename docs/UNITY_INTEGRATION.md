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
