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
