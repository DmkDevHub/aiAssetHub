# DEPLOYMENT — Windows 실행·설치·업데이트

## 제공 방식
- 제품: **Windows x64 설치형 앱**. 초기 배포는 Tauri NSIS `*-setup.exe` 선호.
- 일반 사용자는 Python/SQLite 개발 환경을 별도로 설치하지 않는다.
- Tauri 앱 안에 Vue 정적 파일 + 패키징된 Python Core Sidecar를 포함.
- AI 모델 가중치는 크기/라이선스/하드웨어별 차이로 **설치본 기본 포함을 강제하지 않고**, 사용자 선택 다운로드/등록 방식을 적용한다.

## 현재 최소 앱 개발 실행 (R00-02~05)

테스트는 D-019에 따라 화면을 직접 조작하지 않는 내부 자동화로 수행한다. `npm run check`는 Node 회귀·가상 DOM 컴포넌트 테스트·프런트엔드 타입 검사·빌드를 실행하며 앱 창이나 브라우저를 열지 않는다. 아래 `dev` 명령은 개발자가 앱을 실행할 때 사용하는 명령이다. 이 문서의 기존 화면 확인 기록은 정책 변경 전 이력이다.

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
- `npm test`: Node 내장 러너로 개발 포트 점유 거부·반환과 상단 바 입력·이벤트·라우팅·상태를 검사한다. 컴포넌트 테스트는 개발 전용 jsdom과 메모리 라우터를 사용한다.
- Tauri가 `beforeDevCommand`로 Vite를 시작하므로 브라우저 확인용 서버는 먼저 종료한다.
- 최소 앱은 다크 테마로 라이브러리 화면을 연다. `화면 설정`에서 다크/라이트를 선택하면 화면 이동 후에도 테마가 유지된다. 테마는 메모리 상태이므로 새로고침·재실행 시 다크로 돌아간다. Python·DB·AI·파일 선택 기능은 아직 연결하지 않는다.
- `local.aiassethub.dev`는 개발용 임시 식별자다. 배포 식별자·출판사명은 DECISIONS의 미정 사항으로 유지한다. 현재 NSIS 번들은 최소 셸의 개발 설치본이다.
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

## 최소 셸 NSIS 개발 설치본 (R00-05)

```bash
npm run build:installer
```

- 프런트엔드 검사·빌드 후 Cargo 잠금 파일 기준으로 Windows x64 release 앱과 NSIS `*-setup.exe`를 생성한다. 결과 폴더는 `src-tauri/target/release/bundle/nsis/`다.
- 설치 언어는 한국어, 범위는 현재 Windows 사용자(`currentUser`)다. Python Core·DB·AI 기능은 아직 포함하지 않는다.
- WebView2가 없을 때는 공식 다운로드 bootstrapper 방식으로 설치하므로 인터넷 연결이 필요하다. WebView2가 있는 환경에서는 기존 런타임을 사용한다.
- 개발 식별자와 Tauri 기본 아이콘을 사용한 미서명 설치본이다. 제품 식별자·출판사·서명·업데이트는 공개 배포 전에 결정해야 한다.

2026-10-28 `AI Asset Hub_0.5.0_x64-setup.exe`(1,941,376바이트)를 생성하고 `/S /D=<새 경로>`로 `%LOCALAPPDATA%\Programs\AIAssetHubDev`에 검증용 설치했다. HKCU 제거 프로그램 등록의 버전·경로를 확인했으며 해당 설치는 PC에 유지한다.

설치된 실행 파일을 개발 서버 없이, PATH를 Windows System32로 제한해 실행한 뒤 라이브러리·화면 설정·테마 변경·뒤로 가기·정상 종료를 확인했다. 개발 도구가 설치된 현재 PC에서의 검증이며 깨끗한 PC, WebView2 신규 설치 및 설치 마법사 수동 클릭 검증은 미실행이다. 이번 설치본 해시는 TEST_PLAN의 R00-05 기록을 참고한다.

## 이후 Python Core 통합 빌드 순서 (미구현)
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
