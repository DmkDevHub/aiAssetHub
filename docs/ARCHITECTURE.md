# ARCHITECTURE — 기술 및 실행 구조

## 기준 구조
```text
[Windows 사용자]
       ↓
[Tauri 2 앱] ─ Vue 3 / TypeScript / Dark UI
       │ Tauri 명령·프로세스 수명주기·파일 선택
       ↓
[Python Core Engine — App Sidecar / 단일 쓰기 주체]
       ├─ Library / File Scanner / Thumbnail / Tag Service
       ├─ SQLite + FTS5 / Embedding Search
       ├─ Analysis Queue / Provider Adapter / Model Registry
       ├─ MCP Command Broker / Unity Operation Broker
       └─ Audit / Cost / Settings / Backup
             │                    │
      SQLite + 원본 참조    로컬 IPC (loopback)
                                  ↑
  [Codex 등 MCP Host] ↔ [MCP stdio bridge] ↔ [Python Core]
                                  ↕
                         [Unity Editor Connector]
                                  ↓
                           [Unity 프로젝트]
```

## 주요 프로세스 분리
1. **Tauri 앱 프로세스:** Window/UI, 로컬 파일 선택, Core Sidecar 시작·정상 종료, OS 권한.
2. **Python Core Sidecar:** 에셋과 분석의 단일 비즈니스 계층, DB 마이그레이션 및 쓰기 책임.
3. **MCP stdio Bridge:** Codex 등 Host가 기동. Core에 접근해 툴 결과 반환하며 자체 DB 직접 쓰기 금지.
4. **Unity Editor Connector:** 설치된 Unity Editor에서 명령 수신, Unity API로 임포트·배치, 결과 반환.

## 로컬 통신 권장안 (설계 선택)
- Tauri ↔ Python: 로컬 IPC 또는 `127.0.0.1` 동적 포트, 애플리케이션 범위 토큰으로 인증. 공개 인터페이스 노출 금지.
- MCP: 호환 클라이언트를 위해 **stdio**를 초기 전송으로 채택; Bridge가 Core로 전달.
- Unity: Editor 패키지가 로컬 Broker에 연결(예: 제한된 폴링), 요청 ID별로 실행/결과를 기록.
- Core는 기본적으로 앱 실행 시 기동. **앱이 종료된 경우 MCP Bridge는 명확한 연결 불가 오류** 반환(상시 백그라운드 서버 비목표).
- 로컬 통신 설계의 실제 인증·프로세스 경로는 구현 전에 Windows 개발/설치본에서 검증한다.

## Core 계층화
| 계층 | 책임 | 금지 |
|---|---|---|
| Presentation | Vue 검색·갤러리·설정·작업 상태 | 직접 SQLite/외부 AI 호출 |
| Tauri Desktop | 파일 대화상자·Sidecar 수명주기·권한 | AI 분석 비즈니스 로직 |
| Application | 스캔, 분석 큐, 검색, Unity 작업 유스케이스 | UI 마크업 처리 |
| Domain | Asset, AnalysisRun, AnalysisResult, Job, Model | OS/플러그인 특정 코드 |
| Infrastructure | SQLite, FTS5, 파일 접근, 공급업체 SDK | UI 상태관리 |
| MCP/Connector | 외부 호출 ↔ 유스케이스 계약 | DB 우회 변경 |

## 실패 처리
- 엔진 시작 실패: 앱은 죽지 않고 오류·재시도 및 로그 위치 제공.
- DB 마이그레이션 실패: 쓰기 작업 중지, 백업·오류 안내, 데이터 덮어쓰기 금지.
- Sidecar 비정상 종료: UI 연결 끊김 표시 후 제한적 재시작; 실행 중 작업 복구 상태 기록.
- Unity 미연결: 검색/분석은 사용 가능; Unity 쓰기 명령만 실행 불가로 응답.
- 파일 누락: 분석 결과를 삭제하지 않고 가용 상태 표시 후 복구/경로 재등록 유도.

## 장기 확장
- Unity를 첫 번째 Connector로 구현하되, `TargetToolConnector` 계약(준비·실행·검증·취소)을 통해 이후 Godot/Unreal 등 확대.
- Python과 Vue, SQLite 및 MCP는 기존 선택 유지. LangChain/LangGraph를 추가하지 않는다.

## 현재 Core 진입점 구현 범위 (R02-01)

- `python-core/ai_asset_hub_core`에 외부 의존성 없는 `CoreApplication`과 일회성 개발 CLI를 둔다. 명령 처리와 콘솔 진입점을 분리해 향후 인증된 Tauri 통신에서도 같은 health 유스케이스를 호출할 수 있다.
- 현재 허용 명령은 읽기 전용 `health.get` 하나이며 자신의 PID·버전·가동 시간을 측정한다. DB·원본 에셋·네트워크·AI·MCP·Unity를 초기화하지 않는다. DB는 `not_configured`로 반환한다.
- 이 단계는 Core 개발 프로세스 자체의 실측 검증이다. 앱에 연결 상태를 표시하거나 Sidecar를 기동하지 않는다. 실제 로컬 전송·세션 인증·프로세스 수명주기는 R02-02에서 구현하고 검증한 뒤 연결한다.

## 데스크톱 Core 통신 (R02-02)

- Tauri가 직접 생성하고 소유한 Python 자식의 비공개 stdin/stdout을 사용한다. 다른 프로세스가 접속할 네트워크 포트·탐색 파일·공유 토큰이 없으며 OS가 상속한 파이프 핸들이 통신 권한이다. 향후 MCP/Unity 채널은 별도 인증 설계가 필요하다.
- JSON 줄 프레임은 16KiB 이하이며 요청 UUID·실제 자식 PID·제품 버전을 확인한다. 응답 3초 초과·잘못된 프레임은 세션을 종료한다. UI는 health/재연결만 호출할 수 있고 실행 파일·경로·임의 Core 명령은 전달하지 못한다.
- 시작 시 한 세션을 만들고 실제 health 결과를 표시한다. 정상 종료는 stdin EOF 후 대기·필요 시 kill/wait로 수거한다. 실패해도 셸을 유지하고 사용자가 다시 연결할 수 있다. stderr/내부 예외·경로는 UI로 전달하지 않는다.

## Core 종료·복구 (R02-06)

- 연결된 동안 5초마다 health를 확인한다. 요청은 하나씩 수행하며 화면 해제 시 타이머·늦은 응답을 정리한다. Core 종료/응답 지연/프로토콜 오류는 연결 끊김과 고정 원인 문구를 표시한다.
- DB 오류는 Core 프로세스 준비와 구분한다. 다른 앱의 잠금·환경 혼용·호환되지 않는 스키마·읽기 실패는 데이터 보존 안내를 제공하며 자동 초기화/복구를 하지 않는다.
- 실패한 세션은 수거하고 원인 코드를 유지한다. 폴링은 실패 후 중단하고 사용자 `다시 연결`만 새 프로세스를 만든다. 분석/임베딩/원본 정리/Unity 작업은 생성·자동 재개하지 않는다.
