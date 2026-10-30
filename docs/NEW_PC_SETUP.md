# 새 Windows PC로 개발 환경 이전

작성 기준: 2026-10-29 / M08C 완료 / Windows x64 / DB v6.

목표는 새 PC에서 소스를 받은 다음 **환경 조사 → 부족한 필수 도구 설치 → 의존성 복원 → 내부 자동 테스트 → 설치본 재빌드·검증**까지 완료하는 것이다. 이 문서 작성 시 새 PC에서의 실행은 **미실행**이다. 기존 PC의 통과 기록을 새 PC의 검증 결과로 대신하지 않는다.

## 1. 새 PC의 에이전트에 전달할 요청

저장소를 먼저 복제하고 아래 내용을 새 채팅에 붙여 넣는다. 설치 프로그램이 아니라 이 문서 자체가 Git에 포함된다. 이 문서가 포함된 커밋을 원격에 push한 뒤 새 PC에서 받아야 한다.

> AGENTS.md와 docs/NEW_PC_SETUP.md를 읽고 이 PC의 AI Asset Hub 개발 환경을 준비해 줘. 현재 프로그램/아키텍처/경로부터 조사하고, 없는 필수 개발 도구만 공식 배포처에서 설치해. 필수 개발 도구 설치와 프로젝트 의존성 다운로드를 허용한다. 관리자 권한이나 재부팅이 실제로 필요하면 그 이유와 진행 상태를 알려 줘. 기존 프로그램을 제거하거나 사용자 데이터를 덮어쓰지 마. 프로젝트 전용 Python 환경과 Sidecar를 새로 만들고 내부 자동화 테스트·타입 검사·Rust 검사·Windows 설치본 빌드·격리된 무화면 설치 검증까지 순서대로 진행해. 앱/브라우저 화면을 열거나 직접 조작하는 테스트는 하지 마. Ollama와 모델 다운로드·실제 AI 추론은 선택 단계이므로 별도 요청 전에는 실행하지 마. 사용자 DB·원본 에셋 이전도 별도 승인된 복사본만 다뤄. 결과를 docs/TEST_PLAN.md에 실제 버전·명령·통과/실패/미실행으로 기록하고, 다음 기능 개발이나 원격 push는 하지 마.

## 2. Git으로 오는 것과 별도 준비할 것

| 대상 | 이전 방법 |
| --- | --- |
| Vue/TypeScript, Rust, Python, 문서, 테스트, SQL 001~006 | Git clone/pull. 소스와 마이그레이션을 함께 받는다. |
| package-lock.json, src-tauri/Cargo.lock, python-core/requirements-*.txt | Git에 포함된 버전을 사용한다. 환경 복원 중 임의 업그레이드하지 않는다. |
| node_modules, dist | 복사하지 않고 `npm ci` 및 빌드로 재생성한다. |
| src-tauri/target, src-tauri/gen, src-tauri/binaries | 복사할 필요 없다. Cargo/Tauri와 `npm run package:core`로 재생성한다. |
| .artifacts/core-build-venv, .venv | PC/기반 Python의 절대 경로에 묶일 수 있다. 새 PC에서 다시 만든다. |
| 기존 setup.exe·Sidecar·빌드 manifest·검증 로그 | Git 제외. 보관이 필요하면 별도 백업하되 새 개발 환경은 소스에서 재빌드한다. |
| Git/Node/Python/Rust/MSVC/Windows SDK/WebView2 | 새 PC 설치 상태를 조사한 뒤 없는 도구를 설치한다. |
| 실제 에셋 파일과 앱 DB | 개발 환경 설치와 별도다. 아래 데이터 이전 절차를 따른다. Git에 넣지 않는다. |
| Ollama 실행 파일·모델 가중치 | Git 제외. 선택적으로 다시 설치/다운로드하거나 모델 저장소를 복사한다. |
| .env, 외부 API 키, Git 인증, MCP 클라이언트 설정 | Git 제외 또는 PC별 설정이다. 필요한 것만 새 PC에서 재설정한다. 비밀을 문서/로그/Git에 넣지 않는다. |

`.gitignore`가 실제 기준이다. `.artifacts` 전체에는 재생성 가능한 캐시뿐 아니라 **개발 DB와 다운로드 모델**도 들어갈 수 있으므로, 기존 PC에서 폴더 전체를 무조건 삭제하지 않는다. 이전용 백업에서 필요한 데이터만 골라 보관한다.

## 3. 도구와 설치 기준

현재 PC에서 실측한 버전은 비교 기준이며 새 PC에 이미 설치됐다는 뜻이 아니다. 다른 버전의 호환성은 실제 테스트로 확인한다.

| 도구 | 준비 기준 | 현재 PC 실측 / 공식 배포처 |
| --- | --- | --- |
| Windows | 네이티브 x64. 현재 패키징 스크립트는 Windows ARM64/WSL/Linux 빌드를 지원하지 않는다. | Windows x64 |
| Git | clone/push 및 인증. 기존 사용자 identity를 덮어쓰지 않는다. | [Git for Windows](https://git-scm.com/downloads/win) |
| Node.js / npm | package.json의 Node ≥22.12.0. 우선 검증 기준과 같은 24 계열 사용. | Node 24.12.0 / npm 11.6.2 · [Node 공식 다운로드](https://nodejs.org/en/download) |
| Python | x64 CPython. 실행기 최소 조건은 3.11+지만 고정 패키지 조합은 3.13 계열을 우선한다. | Python 3.13.15 · [Windows 릴리스](https://www.python.org/downloads/windows/) |
| Rust / Cargo | MSVC x64 툴체인, rustfmt, clippy. GNU 툴체인으로 바꾸지 않는다. | rustc/Cargo 1.99.1 · [rustup 공식 설치](https://rust-lang.org/tools/install/) |
| Microsoft C++ Build Tools | VS 2022 C++ Desktop 워크로드, x64/x86 MSVC v143 및 Windows SDK | [Tauri 사전 요구사항](https://v2.tauri.app/start/prerequisites/), [Microsoft 구성 요소](https://learn.microsoft.com/en-us/visualstudio/install/workload-component-id-vs-build-tools?view=vs-2022) |
| WebView2 Runtime | Evergreen x64 Runtime 설치 상태 확인. SDK/NuGet 패키지와 별개다. | [Microsoft WebView2](https://developer.microsoft.com/en-us/microsoft-edge/webview2/) |
| Ollama / 모델 | 실제 로컬 AI 검증을 할 때만 필요하다. 일반 자동 테스트에는 없어도 된다. | 아래 선택 단계 |

SQLite 서버, 전역 Vue/Vite/Tauri CLI, Docker, Unity Editor는 현재 개발 환경 복원에 필요하지 않다. SQLite는 Python에 포함되며 JS 도구는 npm 잠금 파일로 설치한다. Unity는 후속 M09 작업에서 준비한다.

## 4. 저장소와 환경 조사

PowerShell에서 저장소 루트로 이동한다. 경로는 새 PC에 맞게 바꾸며 기존 `C:\Users\kdm` 경로를 그대로 복제하지 않는다. 공백이 있는 경로에는 따옴표를 사용한다.

```powershell
git clone https://github.com/DmkDevHub/aiAssetHub.git
Set-Location .\aiAssetHub
$taskRepo = (Get-Location).Path
git status --short
git branch --show-current
git log -1 --oneline
[Environment]::Is64BitOperatingSystem
[Environment]::Is64BitProcess
Get-Command git,node,npm,python,py,rustup,rustc,cargo -ErrorAction SilentlyContinue |
  Select-Object Name,Source
```

이미 존재하는 작업 폴더 위에 clone하지 않는다. 이미 복제했다면 clone을 생략하고 해당 루트에서 상태를 확인한다. 미커밋 변경이 있으면 reset/clean하지 않는다. Git 인증이 필요한 경우 사용자 계정으로 로그인하고 토큰 값을 출력하지 않는다.

설치된 명령만 실행해 버전을 기록한다. 없는 명령은 다음 단계에서 준비한다.

```powershell
git --version
node --version
npm --version
python --version
py -0p
rustup show
rustc --version
cargo --version
$taskVswhere = Join-Path ${env:ProgramFiles(x86)} 'Microsoft Visual Studio\Installer\vswhere.exe'
if (Test-Path -LiteralPath $taskVswhere) {
  & $taskVswhere -latest -products '*' -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath
}
Get-ItemProperty 'HKLM:\SOFTWARE\Microsoft\Windows Kits\Installed Roots' -ErrorAction SilentlyContinue
```

`py`는 설치 방식에 따라 없을 수 있다. `python`이 Store 안내를 열거나 다른 버전을 선택하면 실제 x64 CPython 실행 파일을 찾아 사용한다. 일반 터미널에서 `cl.exe`가 PATH에 없다는 것만으로 Build Tools 미설치로 판정하지 않는다. vswhere 결과·SDK 설치 경로와 실제 Cargo 빌드로 확인한다. WebView2는 설치 프로그램/설치 등록 정보로 확인하며 검사 목적으로 앱 창을 열지 않는다.

## 5. 부족한 필수 도구 설치

1. 공식 배포처에서 Git, Node 24 계열, Python 3.13 x64를 준비한다. Python은 일반 CPython 설치를 사용하며 Microsoft Store 별칭이나 프로젝트 venv를 기반 Python으로 선택하지 않는다.
2. Build Tools가 없으면 공식 VS 2022 설치 파일로 `Microsoft.VisualStudio.Workload.VCTools`와 권장 구성 요소를 설치한다. 워크로드 이름만 설치하고 MSVC/SDK를 빼먹지 않는다. Microsoft 문서의 권장 구성에 x64/x86 MSVC와 Windows SDK가 포함되는지 확인한다.
3. rustup의 Windows x64 설치 파일을 사용해 MSVC 툴체인을 설치한다. 아래 명령은 rustup 설치 후 실행한다. 아래 명령은 저장소별 override를 사용해 다른 프로젝트의 전역 default를 바꾸지 않는다.
4. WebView2 Evergreen x64 Runtime이 없으면 공식 배포처에서 설치한다.
5. 설치가 요청한 경우 재부팅하고 새 PowerShell/에이전트 세션에서 PATH를 다시 확인한다. 기존 프로세스는 새 PATH를 자동 반영하지 않을 수 있다.

```powershell
rustup toolchain install stable-x86_64-pc-windows-msvc
rustup override set stable-x86_64-pc-windows-msvc
rustup component add rustfmt clippy --toolchain stable-x86_64-pc-windows-msvc
rustup show
```

Build Tools의 무인 설치를 사용할 경우 **공식 배포처에서 받은 유효한 Microsoft 서명 설치 파일**만 사용한다. 경로는 실제 다운로드 위치로 바꾼다. 새 설치에 대한 예시이며 기존 VS 설치 수정은 설치 상태를 확인한 뒤 수행한다.

```powershell
$taskVsInstaller = Join-Path $env:USERPROFILE 'Downloads\vs_BuildTools.exe'
$taskSignature = Get-AuthenticodeSignature -LiteralPath $taskVsInstaller
if ($taskSignature.Status -ne 'Valid' -or $taskSignature.SignerCertificate.Subject -notmatch 'Microsoft') {
  throw '공식 설치 파일 서명을 확인하세요.'
}
$taskInstall = Start-Process -FilePath $taskVsInstaller -WindowStyle Hidden -Wait -PassThru -ArgumentList @(
  '--quiet','--wait','--norestart','--add','Microsoft.VisualStudio.Workload.VCTools','--includeRecommended'
)
if ($taskInstall.ExitCode -notin 0,3010) { throw 'Build Tools 설치 실패: 로그를 확인하세요.' }
# 3010이면 재부팅이 필요하다. 이후 검증을 먼저 실행하지 않는다.
```

관리자 권한·디스크 공간·다운로드 제한이 걸리면 실제 원인을 보고한다. 전역 보안 설정/백신/실행 정책을 일괄 해제하거나 다른 개발 도구를 제거해 해결하지 않는다. Rust/Cargo, npm, pip, NSIS 도구의 최초 다운로드에는 네트워크가 필요하다. 기존 PC에 있던 NSIS 캐시를 따로 복사할 필요는 없다.

## 6. 프로젝트 의존성·Python 환경·Sidecar 복원

이후 명령은 모두 저장소 루트에서 실행한다. **각 네이티브 명령의 종료 코드가 0인지 확인하고 실패하면 다음 단계로 넘어가지 않는다.** PowerShell의 `$ErrorActionPreference='Stop'`만으로 npm/cargo의 비정상 종료가 자동 중단된다고 가정하지 않는다.

```powershell
$taskRepo = (Get-Location).Path
$taskPython = (& python -c 'import sys; print(sys.executable)').Trim()
if ($LASTEXITCODE -ne 0) { throw '기반 CPython을 찾지 못했습니다.' }
$env:AI_ASSET_HUB_PYTHON = $taskPython
& $env:AI_ASSET_HUB_PYTHON -c 'import sys,struct; print(sys.version); print(sys.executable); print(struct.calcsize("P")*8); assert sys.prefix == sys.base_prefix; assert struct.calcsize("P") == 8'
if ($LASTEXITCODE -ne 0) { throw 'x64 기반 CPython 선택을 확인하세요.' }
npm ci
if ($LASTEXITCODE -ne 0) { throw 'npm 의존성 복원 실패' }
npm run package:core
if ($LASTEXITCODE -ne 0) { throw 'Core 패키징 실패' }
```

위 CPython 출력이 **64**인지도 확인한다. python 명령이 없다면 `$taskPython`에 설치된 기반 Python의 절대 경로를 직접 지정한다. `AI_ASSET_HUB_PYTHON`은 현재 PowerShell과 거기서 실행한 자식에만 적용된다. 새로운 에이전트/터미널에서도 필요한 경우 다시 지정한다.

`package:core`는 `.artifacts/core-build-venv`를 새로 만들고 `requirements-build.txt`→런타임/MCP 고정 의존성을 설치한다. 현재 Pillow 13.0.0, PyInstaller 6.22.3, MCP SDK 2.3.0 조합이다. Python 환경 복원 전에 `npm run check`만 실행하면 Pillow/MCP 부재로 실패할 수 있다. `pip freeze`로 잠금 파일을 임의 교체하지 않는다.

개발 Core와 일반 테스트는 **기반 Python**으로 프로젝트 전용 site-packages를 로드한다. `AI_ASSET_HUB_PYTHON`을 `.artifacts/core-build-venv/Scripts/python.exe`로 지정하지 않는다. Windows venv 실행기 때문에 자식 PID 검증이 달라질 수 있다. 모델 검증 보조 스크립트에서는 아래와 같이 전용 venv 실행 파일을 사용할 수 있다.

생성 확인 대상:

- `.artifacts/core-build-venv/Scripts/python.exe`
- `src-tauri/binaries/core/ai-asset-hub-core/ai-asset-hub-core.exe`와 `_internal/`
- `src-tauri/binaries/ai-asset-hub-core-x86_64-pc-windows-msvc.exe`
- `.artifacts/core-build-manifest.json`

기존 PC에서 가져온 venv가 이미 있다면 재사용하지 않는다. 해당 위치·백업 필요 여부를 먼저 확인하고 그 환경만 별도 보관한 다음 재생성한다. 사용자 데이터가 섞인 `.artifacts` 전체를 삭제하지 않는다.

## 7. 내부 자동화 검증 순서

설치본 빌드와 테스트는 **동시에 실행하지 않는다**. 기존 PC에서 CPU 경합 중 테스트 실행기의 30초 제한에 걸린 이력이 있다. 실패 시 로그에서 누락 도구와 시간 초과를 구분한다. 테스트 수는 아래 작성 시점 기준이며 이후 커밋에서 늘어날 수 있다.

```powershell
npm run check
if ($LASTEXITCODE -ne 0) { throw '공통 자동 검증 실패' }
cargo fmt --manifest-path src-tauri/Cargo.toml -- --check
if ($LASTEXITCODE -ne 0) { throw 'Rust 포맷 검사 실패' }
cargo clippy --manifest-path src-tauri/Cargo.toml --all-targets --locked -- -D warnings
if ($LASTEXITCODE -ne 0) { throw 'Rust 정적 검사 실패' }
$env:AI_ASSET_HUB_SIDECAR_DIR = Join-Path $taskRepo 'src-tauri\binaries\core\ai-asset-hub-core'
cargo test --manifest-path src-tauri/Cargo.toml --lib --locked -- --include-ignored --test-threads=1
if ($LASTEXITCODE -ne 0) { throw 'Rust/패키지 Core 테스트 실패' }
npm run build:installer
if ($LASTEXITCODE -ne 0) { throw 'Windows 설치본 빌드 실패' }
& .\scripts\verify-installer.ps1 -Mcp
if (!$?) { throw '격리 설치본 검증 실패' }
git status --short
```

작성 기준의 기존 PC 결과는 Node **137개**, Python **152개**, Rust **13개**(패키지 포함), 합계 **302개** 통과다. `npm run check`에는 타입 검사·Vite 빌드가 포함된다. 새 PC에서는 종료 코드·실제 테스트 수·소요 시간·실패 사유를 따로 기록한다. Rust의 ignored 패키지 테스트를 생략하고 전체 통과로 쓰지 않는다.

`verify-installer.ps1 -Mcp`는 설치본 빌드로 내려받은 NSIS 도구/생성 스크립트를 사용한다. 검증용 별도 제품명과 `.artifacts`의 새 위치에 조용히 설치하고, 창을 만들지 않는 `--verify-core` 분기와 공식 SDK MCP 클라이언트를 검사한 뒤 검증 설치본만 제거한다. 기존 설치·사용자 AppData를 검증 DB로 사용하지 않는다. 예상 스키마가 최신 마이그레이션과 맞는지도 확인한다(현재 v11; 실제 마이그레이션 SQL 개수와 대조).

최종 설치 파일: `src-tauri/target/release/bundle/nsis/AI Asset Hub_0.5.0_x64-setup.exe`. 이 파일은 Git에 없으므로 새로 만든다. 일반 사용자는 이 설치본만 사용할 때 Python/Node/Rust를 별도로 설치하지 않아도 된다. 개발자는 소스 빌드 도구가 필요하다.

검증 단계에서 `npm run dev`, `npm run dev:web`, `npm run preview`, 일반 앱 실행, 브라우저/Computer Use 조작을 사용하지 않는다. `dev`는 개발자가 나중에 실제 앱 실행을 요청했을 때 별도로 사용한다.

## 8. 기존 데이터와 원본 에셋 이전 — 필요한 경우만

새 환경이 통과한 뒤 사용자 데이터 보존이 필요한지 별도로 결정한다. 새로운 빈 테스트 DB의 통과와 기존 DB 이전 성공은 서로 다른 결과다.

1. 기존 PC의 앱·Core·DB 쓰기를 모두 종료한다. 실행 중인 SQLite의 `.sqlite` 파일 하나만 복사하면 WAL의 최신 변경을 놓칠 수 있다. 중지된 데이터 디렉터리를 통째로 백업하거나, 별도로 검증된 SQLite backup API 백업을 사용한다. `-wal`/`-shm`을 임의 삭제하지 않는다.
2. 개발 데이터는 기존 저장소 `.artifacts/data/development`, 설치 앱 데이터는 Tauri `app_local_data_dir()/data`다. Windows 기본 경로 후보는 `%LOCALAPPDATA%\local.aiassethub.dev\data`이며 실제 설치/환경을 확인해 결정한다. `asset_hub.sqlite`, `.ai-asset-hub.json`, 백업 및 필요한 캐시를 함께 식별한다.
3. 새 PC에서 앱/Core가 중지된 상태로 **별도 복사본**을 준비한다. 개발/운영 표식(environment)을 섞거나 덮어써 맞추지 않는다. `.core.lock` 파일 자체에 유효한 세션이 저장되는 것은 아니며 사용 중 오류를 잠금 파일 삭제로 해결하지 않는다.
4. 실제 원본 에셋은 별도로 복사한다. 현재 DB에는 라이브러리/파일의 절대 경로가 저장된다. 가능하면 이전 드라이브 문자·폴더 경로를 유지한다. 경로가 바뀌면 아직 일반 경로 재배치 기능이 없으므로 임의 SQL 수정이나 재등록으로 UUID/분석 이력이 유지된다고 약속하지 않는다. 재등록은 새 에셋 ID가 생길 수 있다. 필요한 경우 별도 이전 작업으로 설계·검증한다.
5. 복사본의 DB 무결성·등록 ID·활성 결과·그룹/패키지/예외·파일 경로를 내부 조회로 검증한다. 구버전 DB는 Core가 백업 후 가산 마이그레이션한다. 이전 DB나 원본을 지우는 것은 이 문서의 범위가 아니다.
6. 외부 모델 키는 Windows Credential Manager에 저장되며 DB 절대 경로 해시와 모델 ID에 연결된다. DB 복사로 키가 옮겨지지 않는다. 새 PC/새 경로에서는 필요한 자격 증명을 다시 등록하고 외부 유료 모델은 기본 비활성 상태를 유지한다.
7. MCP 클라이언트의 Core 실행 파일/cwd 절대 경로도 새 설치 위치에 맞춘다. 임시 PID·세션 토큰·포트는 이전하지 않는다. Codex/편집기 설정 및 Git 인증은 각 제품에서 다시 준비한다.

## 9. Ollama·실제 로컬 AI 검증 — 선택 단계

일반 자동 테스트/빌드/위의 `-Mcp` 검증은 실제 AI 모델 없이 수행한다. 모델 설치·다운로드와 아래 추론 검증은 사용자가 이 단계를 명시적으로 요청한 경우에만 수행한다. 외부 유료 모델로 대체하지 않는다.

기존 개발 PC는 Ollama CLI **0.40.12**, 이미지 모델 **qwen3-vl:2b**, 임베딩 모델 **embeddinggemma:300m**을 사용했다. 실행 파일은 사용자 LocalAppData의 `AIAssetHubTools/ollama-v0.40.12`, 모델은 저장소 `.artifacts/tools/ollama-models`에 있었으며 기본 Ollama 설치 경로와 다르다. 해당 사용자 경로를 새 PC에 하드코딩하지 않는다. 버전/모델 태그가 바뀌면 기존 실측 결과를 그대로 인용하지 않는다.

[Ollama 공식 Windows 안내](https://docs.ollama.com/windows)를 따라 설치하고, 모델 저장 위치는 `OLLAMA_MODELS`로 지정할 수 있다. 기존 모델을 복사할 때는 Ollama를 중지하고 해당 저장소의 manifests/blobs를 함께 옮긴 뒤 `ollama list`로 확인한다. 기본 위치를 추측해 일부 blob만 복사하지 않는다. 모델 가중치와 GPU 드라이버는 Git에 포함되지 않는다.

이미 실행 중인 Ollama의 루프백 서버를 우선 사용한다. 없다면 설치된 `ollama.exe`의 절대 경로를 확인한 뒤 아래처럼 숨김 프로세스를 시작할 수 있다. 환경 변수는 **서버를 시작하는 프로세스**에 적용해야 한다. 기존 서버에 나중에 변수를 설정했다고 적용되는 것은 아니다.

```powershell
$env:OLLAMA_HOST = '127.0.0.1:11434'
$env:OLLAMA_NO_CLOUD = '1'
$env:OLLAMA_MODELS = Join-Path $taskRepo '.artifacts\tools\ollama-models'
$taskOllama = (Get-Command ollama.exe -ErrorAction Stop).Source
# 기존 서버가 없는 것을 확인한 경우에만 실행한다.
$taskOllamaServer = Start-Process -FilePath $taskOllama -ArgumentList 'serve' -WindowStyle Hidden -PassThru
ollama --version
ollama list
# 다운로드 승인이 있고 해당 모델이 없을 때만 실행한다.
ollama pull qwen3-vl:2b
ollama pull embeddinggemma:300m
```

사용자 승인 후 실제 추론 검증:

```powershell
$taskHarnessPython = Join-Path $taskRepo '.artifacts\core-build-venv\Scripts\python.exe'
$taskSidecar = Join-Path $taskRepo 'src-tauri\binaries\core\ai-asset-hub-core\ai-asset-hub-core.exe'
& $taskHarnessPython -B scripts/verify-local-analysis.py --model qwen3-vl:2b --sidecar $taskSidecar --report .artifacts/new-pc-analysis.json
if ($LASTEXITCODE -ne 0) { throw '실제 로컬 이미지 분석 검증 실패' }
& $taskHarnessPython -B scripts/verify-semantic-search.py --embedding-model embeddinggemma:300m --analysis-model qwen3-vl:2b --sidecar $taskSidecar --report .artifacts/new-pc-semantic.json
if ($LASTEXITCODE -ne 0) { throw '실제 로컬 의미 검색 검증 실패' }
```

이 스크립트는 테스트 소유 이미지를 생성하고 실제 로컬 모델을 호출한다. GPU/메모리/드라이버·모델의 vision/embedding 지원을 확인한다. 실패하면 실제 실패로 기록하며 수동 설명/가짜 벡터로 성공을 대신하지 않는다. 모델 설치/추론 미승인 또는 미실행이어도 일반 개발 환경 복원과 분리해 보고한다.

## 10. 실패 진단과 완료 기록

| 증상 | 확인 순서 |
| --- | --- |
| python 명령이 Store 안내/잘못된 Python 선택 | 실제 기반 CPython 절대 경로와 AI_ASSET_HUB_PYTHON 확인. venv를 기반 실행기로 지정하지 않는다. |
| Pillow/MCP import 실패 | package:core 성공 여부, 고정 requirements 설치, 기반 Python과 venv의 버전 일치 확인. |
| link.exe/MSVC/SDK 오류 | vswhere의 x64/x86 도구, C++ 워크로드/SDK 설치, 재부팅·새 터미널 확인. |
| Sidecar 없음·패키지 ignored 테스트 실패 | package:core 재생성, AI_ASSET_HUB_SIDECAR_DIR를 exe가 아닌 폴더로 지정했는지 확인. |
| CORE_TIMEOUT / Core tests could not run | 실제 로그·Python 실행 경로·실행기 30초 제한·CPU/백신 경합 확인. 빌드 종료 후 직렬 재실행. 실패를 단순히 Python 미설치로 단정하지 않는다. |
| DATA_ENV_MISMATCH / DATA_DIRECTORY_UNKNOWN | 개발/운영 표식·복사 범위·실제 경로 확인. DB 초기화/표식 수정으로 우회하지 않는다. |
| DATA_IN_USE | 실제 Core가 사용 중인지 확인하고 소유 프로세스를 정상 종료한다. 다른 프로그램을 일괄 종료하지 않는다. |
| pip/npm/Cargo 다운로드 실패 | 원본 오류·네트워크/프록시·아키텍처/지원 Python 버전 확인. 잠금 파일 변경이나 임의 최신 패키지로 우회하지 않는다. |
| NSIS Korean choowHowToInstall 경고 | 기존에도 있었던 경고다. 종료 코드/실제 설치 검증 결과와 구분해 기록한다. |

완료 보고에는 PC/OS 아키텍처, 실제 도구 버전/경로, 새 설치 항목, Git 커밋, 실행 명령/종료 코드/실측 테스트 수, 설치본 위치·해시, 데이터 이전 여부, AI 단계 실행 여부, 실패/미검증 범위를 적는다. 비밀 값은 적지 않는다. 검증 로그는 `.artifacts/new-pc-*.log` 같은 Git 제외 위치에 보관하고 요약을 [TEST_PLAN.md](TEST_PLAN.md)에 기록한다. 실제 화면/깨끗한 PC 검증은 수행한 범위만 표시한다.

작업 규칙은 [AGENTS.md](../AGENTS.md), 제품 설치 정책은 [DEPLOYMENT.md](DEPLOYMENT.md), 최신 개발 단계는 [ROADMAP.md](ROADMAP.md), 이전 PC 검증 이력은 [TEST_PLAN.md](TEST_PLAN.md)를 따른다.
