# DEPLOYMENT — Windows 실행·설치·업데이트

새 PC에서 개발을 이어가려면 [개발 환경 이전 안내](NEW_PC_SETUP.md)의 조사·도구 설치·의존성 복원·무화면 검증 순서를 따른다. 아래 개별 마일스톤 기록은 당시 이력이다.

## 제공 방식
- 제품: **Windows x64 설치형 앱**. 초기 배포는 Tauri NSIS `*-setup.exe` 선호.
- 일반 사용자는 Python/SQLite 개발 환경을 별도로 설치하지 않는다.
- Tauri 앱 안에 Vue 정적 파일 + 패키징된 Python Core Sidecar를 포함.
- AI 모델 가중치는 크기/라이선스/하드웨어별 차이로 **설치본 기본 포함을 강제하지 않고**, 사용자 선택 다운로드/등록 방식을 적용한다.

## 현재 최소 앱 개발 실행 (R00-02~05)

테스트는 D-019에 따라 화면을 직접 조작하지 않는 내부 자동화로 수행한다. `npm run check`는 Node 회귀·가상 DOM 컴포넌트·Python Core 테스트·프런트엔드 타입 검사·빌드를 실행하며 앱 창이나 브라우저를 열지 않는다. 아래 `dev` 명령은 개발자가 앱을 실행할 때 사용하는 명령이다. 이 문서의 기존 화면 확인 기록은 정책 변경 전 이력이다.

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
- `npm test`: Node 내장 러너로 포트·작업 공간 컴포넌트 회귀를 검사한 뒤 `npm run test:core`로 Python 표준 unittest를 실행한다. 컴포넌트는 jsdom·메모리 라우터를 사용하며 Python은 3.11 이상이 필요하다. 기본 `python` 대신 쓸 실행 파일은 `AI_ASSET_HUB_PYTHON`으로 지정한다.
- Tauri가 `beforeDevCommand`로 Vite를 시작하므로 브라우저 확인용 서버는 먼저 종료한다.
- 앱은 다크 테마로 라이브러리 화면을 연다. `화면 설정`에서 다크/라이트를 선택하면 화면 이동 후에도 테마가 유지된다. 테마는 메모리 상태이므로 새로고침·재실행 시 다크로 돌아간다. 현재 Core·DB는 M02에서 연결했으며 AI·파일 선택은 후속 범위다.
- `local.aiassethub.dev`는 개발용 임시 식별자다. 배포 식별자·출판사명은 DECISIONS의 미정 사항으로 유지한다. 현재 NSIS 번들은 최소 셸의 개발 설치본이다.
- Windows 실행 파일의 아이콘은 공식 Tauri 템플릿 기본값을 개발용으로 사용한다. 제품 아이콘은 아직 정하지 않았다.

최소 셸의 실행 파일만 빌드하려면 다음 명령을 사용한다. 결과는 `src-tauri/target/debug/ai-asset-hub.exe`이며 NSIS 설치본이 아니다.

```bash
npm run tauri build -- --debug --no-bundle -- --locked
```

2026-10-28 위 실행 파일을 Vite 서버 없이 실행해 제목·한국어 문구 표시와 정상 종료를 확인했다. 검사 범위와 결과는 [TEST_PLAN.md](TEST_PLAN.md)의 R00-02 기록을 참고한다.

## 현재 Python Core 개발 조회 (R02-01)

Python 표준 라이브러리만 사용한다. 프로젝트 루트에서 `npm run test:core`로 내부 테스트를 실행한다. 직접 `health.get`을 호출하려면:

```powershell
Push-Location python-core
python -B -m ai_asset_hub_core health.get
Pop-Location
```

한 줄 JSON 응답 후 종료하는 개발용 조회다. PID·버전·가동 시간은 해당 프로세스 실측이며 DB는 `not_configured`다. 현재 앱/Tauri/설치본이 Core와 연결되었다는 뜻이 아니다. 통신·인증·시작/종료는 R02-02, DB는 R02-03, Sidecar 패키징은 R02-05에서 연결한다. 상세는 [Core 안내](../python-core/README.md)를 참고한다.

## 현재 Core 통합 개발 실행
```bash
npm ci
npm run dev
```
- Tauri가 개발 Python Core를 비공개 파이프로 시작하고 종료한다. Core를 별도로 띄워 같은 DB를 공유하지 않는다.
- 개발 DB는 `.artifacts/data/development`이며 운영 AppData DB와 공유하지 않는다.

## 최소 셸 NSIS 개발 설치본 (R00-05)

```bash
npm run build:installer
```

- 프런트엔드 검사·빌드 후 Cargo 잠금 파일 기준으로 Windows x64 release 앱과 NSIS `*-setup.exe`를 생성한다. 결과 폴더는 `src-tauri/target/release/bundle/nsis/`다.
- 설치 언어는 한국어, 범위는 현재 Windows 사용자(`currentUser`)다. R00-05 당시에는 Core·DB를 포함하지 않았으며 현재 빌드는 아래 R02-05의 Core/SQLite 번들을 포함한다. AI 기능은 후속 범위다.
- WebView2가 없을 때는 공식 다운로드 bootstrapper 방식으로 설치하므로 인터넷 연결이 필요하다. WebView2가 있는 환경에서는 기존 런타임을 사용한다.
- 개발 식별자와 Tauri 기본 아이콘을 사용한 미서명 설치본이다. 제품 식별자·출판사·서명·업데이트는 공개 배포 전에 결정해야 한다.

2026-10-28 `AI Asset Hub_0.5.0_x64-setup.exe`(1,941,376바이트)를 생성하고 `/S /D=<새 경로>`로 `%LOCALAPPDATA%\Programs\AIAssetHubDev`에 검증용 설치했다. HKCU 제거 프로그램 등록의 버전·경로를 확인했으며 해당 설치는 PC에 유지한다.

설치된 실행 파일을 개발 서버 없이, PATH를 Windows System32로 제한해 실행한 뒤 라이브러리·화면 설정·테마 변경·뒤로 가기·정상 종료를 확인했다. 개발 도구가 설치된 현재 PC에서의 검증이며 깨끗한 PC, WebView2 신규 설치 및 설치 마법사 수동 클릭 검증은 미실행이다. 이번 설치본 해시는 TEST_PLAN의 R00-05 기록을 참고한다.

## Core 통합 빌드 구조
1. Windows x64 타깃용 Python 의존성 설치·버전 고정.
2. PyInstaller 등으로 Python Core를 `.exe`로 패키징하고 직접 smoke test.
3. Sidecar 바이너리를 Tauri v2가 요구하는 target triple/`externalBin` 설정에 맞춰 배치.
4. Vue 프로덕션 빌드 → Tauri 번들 빌드.
5. Windows NSIS 설치본을 만들고 **개발 도구/Python 미설치 PC**에서 실제 실행 검증.
6. 설치본의 앱 시작/종료, 로컬 엔진, DB 저장, 폴더 선택, 검색, 분석, MCP, Unity 연동까지 단계별 검증.

```bash
npm run tauri build
```
> 현재 `beforeBuildCommand`는 `npm run build && npm run package:core`다. `scripts/package-core.mjs`가 고정 빌드 도구·Sidecar·마이그레이션을 준비하고 이후 Tauri가 번들한다. 깨끗한 PC/전체 제품 흐름은 아직 검증하지 않았다.

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

## 현재 Core 포함 Windows 설치본 (R02-05)

- `npm run package:core`는 프로젝트 `.artifacts/core-build-venv`에 `python-core/requirements-build.txt`의 빌드 도구만 설치한다. 런타임에는 pip·Python 설치가 필요하지 않다. 전역 Python을 수정하지 않는다.
- PyInstaller 6.22.3의 폴더형 번들은 실행 파일과 `_internal` CPython·SQLite DLL·마이그레이션을 포함한다. 단일 파일형의 부모/자식 부트로더를 피하고 실제 Core PID 검증을 유지한다. [PyInstaller 옵션](https://pyinstaller.org/en/stable/usage.html), [Tauri 외부 바이너리](https://v2.tauri.app/develop/sidecar/), [리소스 경로 매핑](https://v2.tauri.app/develop/resources/)을 기준으로 구성했다.
- `npm run build:installer`는 프런트엔드·Core 패키징 후 NSIS를 생성한다. 바이너리·가상 환경·빌드 캐시/manifest는 Git에서 제외하고 빌드 방법·잠금 버전만 기록한다.
- release는 앱 실행 파일 옆 `ai-asset-hub-core.exe`만 실행한다. PATH·개발 Python으로 대체하지 않으며 PYTHONHOME/PYTHONPATH를 제거하고 자식 PATH를 System32로 제한한다. debug는 개발 Python을 사용한다.
- `ai-asset-hub.exe --verify-core <새 절대 경로/core-verification-고유값>`은 창 없이 같은 Core 관리자로 실제 설치된 Sidecar·DB를 검증하고 종료한다. 기존 경로나 사용자 AppData는 검증 대상으로 받지 않는다. 일반 앱 시작 코드는 별도로 창을 생성한다.
- `scripts/verify-installer.ps1`는 생성된 NSIS의 제품/등록 이름만 분리해 동일 파일을 프로젝트 내부 새 위치에 무인 설치(`/S /NS`, 앱 실행 `/R` 없음)한다. Sidecar 해시·스키마·WAL·Python 없는 PATH·Core 종료를 검증하고 해당 검증 설치만 제거한다. 기존 AIAssetHubDev 설치·등록은 유지한다.
- R02-05 기본 설치본: 9,289,722바이트, SHA-256 `5177964f68361be44bf90baaa91856725b195db33ddc3be911939a7e3b235249`. 이후 변경 재빌드 시 해시는 달라진다. 미서명 개발본이며 깨끗한 PC/WebView2 신규 설치·GUI·정식 업그레이드는 미검증이다.

M02 최종 R02-06 설치본은 같은 경로의 `AI Asset Hub_0.5.0_x64-setup.exe`, 9,292,156바이트이며 SHA-256은 `cbe483921a88455f2bcd32177729bae87e4cb74ea69b6ecfb889e5a08dbc02c2`다. 동일한 무화면 설치 검증을 통과했다. 기존 AIAssetHubDev 설치는 자동 업그레이드하지 않았다. GUI·깨끗한 PC·정식 서명 검증 한계는 그대로다.

## M03 개발·배포 갱신

처음에는 `npm run package:core`로 프로젝트 전용 환경과 `requirements-runtime.txt`의 Pillow 13.0.0을 준비한 뒤 `npm run check`/`npm run dev`를 실행한다. 기반 Python 버전과 빌드 가상 환경 버전을 맞춘다. 테스트/개발 Core는 기반 Python에서 전용 site-packages를 로드하며 Windows venv 실행기의 별도 PID를 Core PID로 오인하지 않는다. 전역 Python을 수정하지 않는다. 설치본에는 Pillow와 이미지 DLL을 포함하므로 별도 Python/Pillow 설치가 필요하지 않다.

M03 최종 설치본은 13,439,139바이트, SHA-256 `5442007a81021003c9cbee1091cf9ef061c152d742f11f0b4a7f54e55016b7f9`이며 같은 NSIS 출력 경로에 생성된다. 실제 패키지에서 PNG 등록/스캔/썸네일·원본 보존과 분리된 무인 설치/무화면 Core 검증을 통과했다. 기존 AIAssetHubDev 설치는 보존하며 실제 GUI·깨끗한 PC·정식 서명은 검증하지 않았다.
