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
`TargetToolConnector` 인터페이스: `discover_targets()`, `plan_import()`, `execute_import()`, `plan_place()`, `execute_place()`, `get_status()`.

Unity를 1차 구현하고 Godot/Unreal/Blender 등은 **확장 가능성만 확보**한다. 지원한다고 선전하기 전에 실제 연결·임포트·결과 확인 테스트 필요.

## 실증 시나리오
- 실제 로컬 PNG가 분석·검색되며 Codex가 MCP로 선택 → 지정된 Unity 프로젝트에 임포트 → 씬에 배치 → Unity Editor UI에서 오브젝트 확인 → MCP 결과에 같은 파일과 오브젝트가 표시된다.
