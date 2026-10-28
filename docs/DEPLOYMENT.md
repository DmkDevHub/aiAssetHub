# DEPLOYMENT — Windows 실행·설치·업데이트

## 제공 방식
- 제품: **Windows x64 설치형 앱**. 초기 배포는 Tauri NSIS `*-setup.exe` 선호.
- 일반 사용자는 Python/SQLite 개발 환경을 별도로 설치하지 않는다.
- Tauri 앱 안에 Vue 정적 파일 + 패키징된 Python Core Sidecar를 포함.
- AI 모델 가중치는 크기/라이선스/하드웨어별 차이로 **설치본 기본 포함을 강제하지 않고**, 사용자 선택 다운로드/등록 방식을 적용한다.

## 현재 최소 앱 개발 실행 (R00-02~03)

Windows 개발 환경에 Node.js 22.12 이상, Rust stable MSVC, Microsoft C++ Build Tools의 `Desktop development with C++` 워크로드와 Windows SDK, WebView2가 필요하다. [Tauri 공식 사전 요구사항](https://v2.tauri.app/start/prerequisites/)을 참고한다.

```bash
npm ci
npm run build
npm run dev
```

- `npm run build`: Vue 화면·Vite 설정 타입 검사 후 프런트엔드 프로덕션 빌드.
- `npm run dev`: 개발 포트 사전 검사 후 `tauri dev -- --locked`로 Windows 창과 Vite를 함께 실행. Cargo/MSVC 설치 후 새 터미널에서 실행한다. 창을 닫으면 CLI와 Vite도 종료된다.
- `npm run dev:web`: 브라우저 전용 화면 확인용 `http://127.0.0.1:1420`. Windows 앱과의 검증 결과를 구분한다.
- 개발 포트 점유 시 `npm run dev`는 Tauri 실행 전에 오류 코드 1로 중단한다. 사전 검사 없이 직접 `npm run tauri dev`를 실행하면 Tauri가 기존 서버에 연결했다가 오류로 종료할 수 있으므로 기본 개발 명령을 사용한다.
- `npm test`: Node 내장 테스트 러너로 개발 포트 점유 거부·기존 서버 보존·검사 후 포트 반환을 검증한다.
- Tauri가 `beforeDevCommand`로 Vite를 시작하므로 브라우저 확인용 서버는 먼저 종료한다.
- 최소 앱은 다크 테마로 라이브러리 화면을 연다. `화면 설정`에서 다크/라이트를 선택하면 화면 이동 후에도 테마가 유지된다. 테마는 메모리 상태이므로 새로고침·재실행 시 다크로 돌아간다. Python·DB·AI·파일 선택 기능은 아직 연결하지 않는다.
- `local.aiassethub.dev`는 개발용 임시 식별자다. 배포 식별자·출판사명은 DECISIONS의 미정 사항으로 유지하며 설치본 번들은 아직 비활성화했다.
- Windows 실행 파일의 아이콘은 공식 Tauri 템플릿 기본값을 개발용으로 사용한다. 제품 아이콘은 아직 정하지 않았다.

최소 셸의 실행 파일만 빌드하려면 다음 명령을 사용한다. 결과는 `src-tauri/target/debug/ai-asset-hub.exe`이며 NSIS 설치본이 아니다.

```bash
npm run tauri build -- --debug --no-bundle -- --locked
```

2026-10-28 위 실행 파일을 Vite 서버 없이 실행해 제목·한국어 문구 표시와 정상 종료를 확인했다. 검사 범위와 결과는 [TEST_PLAN.md](TEST_PLAN.md)의 R00-02 기록을 참고한다.

## 이후 Core 통합 개발 실행 (미구현 예시)
```bash
npm install
npm run tauri dev
```
- 개발 시에는 Python 가상 환경/Core 모듈을 별도로 실행하거나 개발 스크립트로 함께 구동한다.
- 개발 DB는 프로젝트 `db/` 또는 별도 개발 데이터 경로; 실제 운영 DB와 공유 금지.

## 빌드 순서
1. Windows x64 타깃용 Python 의존성 설치·버전 고정.
2. PyInstaller 등으로 Python Core를 `.exe`로 패키징하고 직접 smoke test.
3. Sidecar 바이너리를 Tauri v2가 요구하는 target triple/`externalBin` 설정에 맞춰 배치.
4. Vue 프로덕션 빌드 → Tauri 번들 빌드.
5. Windows NSIS 설치본을 만들고 **개발 도구/Python 미설치 PC**에서 실제 실행 검증.
6. 설치본의 앱 시작/종료, 로컬 엔진, DB 저장, 폴더 선택, 검색, 분석, MCP, Unity 연동까지 단계별 검증.

```bash
npm run tauri build
```
> 위 명령은 Tauri 번들 예시일 뿐 Python Sidecar를 자동 패키징하지 않는다. `scripts/package-core` 같은 **선행 빌드 스크립트**를 구현해야 한다.

## 설치 경로 정책
```text
%LOCALAPPDATA%/Programs/AI Asset Hub/     # 예시 설치 경로; NSIS 설정에 따라 변경 가능
  AI Asset Hub.exe
  <packaged-python-sidecar>.exe
%APPDATA%/AI Asset Hub/ 또는 %LOCALAPPDATA%/AI Asset Hub/
  data/asset_hub.sqlite                  # 실제 운영 DB, 앱 경로 API로 결정
  thumbnails/
  embeddings/
  logs/
  backups/
  settings/
```
- 구체 경로는 Tauri/OS의 `appData`/`appLocalData` 경로 해석을 사용하며 하드코딩하지 않는다.
- `AppData`는 설정·DB·캐시·백업. 원본 게임 에셋 폴더는 사용자 선택 위치 그대로.

## 실행 수명주기
1. 사용자가 바탕화면/시작 메뉴에서 앱 실행.
2. Tauri가 Sidecar를 기동하고 세션 권한/DB 연결을 검사.
3. Vue 메인 갤러리 화면 로드, 연결 상태를 실제 응답으로 확인.
4. 앱 종료 시 진행 중 작업 취소/정리 정책, DB 커밋, Sidecar 종료.
5. 비정상 종료 후 재실행 시 미완료 작업 복구 상태 표시; AI를 무단 재실행하지 않는다.

## 초기부터 설치본 검증
- 첫 UI 레이아웃 생성 직후 최초 설치본을 생성해 Windows 실행 검증.
- Python/SQLite 통합 직후 재검증.
- MCP Bridge 연결과 Unity 연동 후 각각 설치본 재검증.
- 릴리스 시 버전, 스키마 마이그레이션, 기존 DB 업데이트, 설치/삭제 후 사용자 데이터 정책 검증.

## 업데이트 정책
- 첫 릴리스는 수동 새 설치본 업데이트. 추후 Tauri Updater 채택 여부는 사용자 결정.
- 업데이트 전 데이터 마이그레이션 백업 및 버전 호환 확인. 기존 사용 DB를 빈 DB로 대체 금지.
- 공개 배포 시 서명·Windows SmartScreen 경고 가능성·설치 프로그램 신뢰 정책 점검.

## 공식 자료
- Tauri Windows Installer: https://v2.tauri.app/distribute/windows-installer/
- Tauri Sidecar: https://v2.tauri.app/develop/sidecar/
- Tauri Shell Plugin: https://v2.tauri.app/plugin/shell/
- Tauri Updater: https://v2.tauri.app/plugin/updater/
