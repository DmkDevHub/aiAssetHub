# TEST_PLAN — 기능 완료와 설치본 수용 테스트

## 검증 정책 (D-019, 2026-10-28 변경)

- 테스트는 내부 자동화로 수행한다. 실제 앱·브라우저 화면을 열어 직접 조작하거나 Computer Use/브라우저 제어 도구로 클릭·키보드 입력·화면 캡처 검증을 하지 않는다. 사용자 화면의 포커스를 변경하지 않는다.
- UI 동작은 테스트 러너 안에서 컴포넌트의 렌더 출력·이벤트·상태·라우팅을 검증한다. 내부 로직과 경계는 유닛·통합·API/DB·프로세스/파일 검사로 확인한다. 사용자 화면을 열지 않는 격리 환경·fixture를 사용한다.
- 현재 공통 검사 명령은 `npm run check`다. Node 회귀·가상 DOM 컴포넌트·Python Core 테스트와 프런트엔드 타입 검사·빌드를 실행한다. 해당 테스트가 다루는 기능 범위만 검증하며 시각적 배치를 확인하는 명령은 아니다. 이후 작업에서 관련 동작·오류·회귀 테스트를 추가한다.
- 시각적 배치, 실제 OS 화면, 설치 마법사 등 내부 검사로 확인하지 못한 범위는 **미검증**으로 기록한다. 정적 검사·빌드 성공을 실제 기능·화면 확인으로 보고하지 않는다.

## 테스트 레벨
1. 유닛: 분석 범위 판정, 모델 기능 검증, 파일 식별·필터, 경로 검증, 비용 상한.
2. 통합: SQLite 마이그레이션·파일 스캔·검색 인덱스·Sidecar 통신·MCP 도구.
3. 컴포넌트·흐름: 내부 테스트 러너에서 렌더 출력·상태·이벤트·라우팅과 계층 간 입력/응답 계약을 검증. 실제 폴더·파일·AI·Unity 결과와 fixture/mock 결과를 구분.
4. 설치본: 사용자 화면을 조작하지 않는 격리된 Windows 환경에서 무인 설치·파일/버전/해시·등록 상태·프로세스/IPC 및 데이터 유지 자동 검사. 실환경 미검증 범위 별도 기록.

## 필수 사용자 수용 시나리오

아래 표는 제품의 사용자 동작 목표다. 검증은 위 내부 자동화 정책을 따르며, 실제 화면을 직접 조작하는 절차를 요구하지 않는다.

| ID | 시나리오 | 통과 조건 |
|---|---|---|
| T-01 | 앱 실행/메인 화면 | 3단 UI 및 메뉴 정상 표시 |
| T-02 | 폴더 등록 | 실제 경로 등록 후 갤러리·상세 표시; **AI 호출 0회** |
| T-03 | 폴더 재스캔 | 새/변경/누락 파일 반영, 원본 파일 변경 없음 |
| T-04 | 키워드 검색 | 실제 파일명/태그 검색 및 필터 정확 |
| T-05 | 태그 수정 | 저장/재실행/재스캔 후 사용자 입력 유지 |
| T-06 | 전체 분석 | 대상 범위의 모든 접근 가능한 에셋에 새로운 run, 기존 성공 이력 유지 |
| T-07 | 미분석 분석 | 성공 결과 미보유 에셋만 요청 |
| T-08 | 분석 완료 재분석 | 성공 결과가 있는 에셋만 실행, 실패 시 기존 결과 유지 |
| T-09 | 실패 재시도 | 마지막 실패 항목만 재실행 |
| T-10 | 선택 분석 | 체크한 에셋 ID만 실행 |
| T-11 | 모델 연결/비용 | 비활성화 유료 호출 0회; 예산 초과 작업 거부 |
| T-12 | 분석 진행/취소 | 실측 건수와 상태 일치, 취소 시 불변 이력 보존 |
| T-13 | 자연어 검색 | 분석된 샘플에서 관련 후보 반환, 출처 확인 |
| T-14 | MCP 검색 | 실제 등록된 ID/경로 반환, 연결 오류 시 명확한 실패 |
| T-15 | Unity PNG 임포트 | 실제 프로젝트 `Assets/` 안에 파일 존재/Editor 임포트 성공 |
| T-16 | Unity 씬 배치 | 대상 Scene에 실제 GameObject 생성 및 상태 반환 |
| T-17 | 권한 방어 | 승인하지 않은 경로/덮어쓰기 요청 차단 |
| T-18 | 설치/업데이트 | Python 별도 설치 없이 실행, DB·사용자 데이터 유지 |

## 테스트 샘플 권장
- 이미지 PNG/JPEG 각각 3~5개, 투명 스프라이트, 손상 이미지, 매우 긴 한글 파일명, 같은 이름 중복 파일.
- 3D/오디오 최소 포맷 샘플, 지원 불가 확장자, 파일 접근 차단 폴더.
- 작은 Unity 2D 테스트 프로젝트와 PNG 배치 가능한 테스트 씬.
- Mock 로컬 AI 응답과 실모델 1회 연동 테스트 구분. 실제 외부 API 비용 발생 전 명시적 승인.

## ROADMAP 작업별 완료 조건
- `작업 ID`가 UI의 어느 실제 사용 흐름을 완성하는지 적는다.
- 내부 자동화 테스트의 명령·기대값·실측 결과와 fixture/mock 사용 여부, 미검증 범위를 기록한다.
- 기능 실패·미실행 테스트를 숨기지 않고 작업 완료를 연기한다.
- 완료 후 ROADMAP 갱신 + CHANGELOG + 관련 변경 Git 커밋.

## 실패율·성능
- 초기에는 정량 SLA를 추정으로 확정하지 않는다. 실제 샘플 폴더 100/1,000개에서 탐색·스크롤·스캔 소요 시간을 측정해 기준 결정.
- 벡터 검색 품질은 사람이 평가한 고정 질의/정답 세트를 만든 후 개선.

## R00-02 검증 기록 (2026-10-28)

> 아래 R00-02~05 기록은 D-019 변경 전에 수행한 검증 이력이다. 앞으로의 화면 직접 조작 테스트 요구사항으로 적용하지 않는다.

범위는 최소 진입 화면과 Tauri 데스크톱 셸이다. P0 제품 기능 및 설치본 수용 테스트 통과를 뜻하지 않는다.

검증 환경: Windows x64, Node.js 24.12.0, npm 11.6.2, Rust/Cargo 1.99.1 MSVC, C++ Build Tools 2022 17.14.42, Windows SDK 10.0.26100, WebView2 155.0.4283.62. 의존성은 npm·Cargo 잠금 파일로 기록한다.

| 검사 | 실제 결과 |
|---|---|
| `npm run build` | 통과: Vue·Vite 설정 타입 검사 및 프로덕션 번들 생성 |
| `cargo fmt --all --manifest-path src-tauri/Cargo.toml -- --check` | 통과 |
| `npm run tauri build -- --debug --no-bundle -- --locked` | 통과: `src-tauri/target/debug/ai-asset-hub.exe` 생성 |
| `cargo clippy --manifest-path src-tauri/Cargo.toml --locked --all-targets --features tauri/custom-protocol -- -D warnings` | 통과: 경고를 오류로 처리한 검사 성공 |
| 브라우저 UI 자동 검사 | 통과: 페이지 제목, `AI Asset Hub` 제목 요소, `로컬 에셋 작업 공간` 표시. 콘솔 오류·경고 0건 |
| Windows 네이티브 UI | 통과: Vite 서버 종료 후 실행 파일을 직접 실행. `http://tauri.localhost/` 내장 화면에서 제목·한국어 문구 표시, 최대화/복원 후에도 내용 유지 |
| 정상 종료 | 통과: 네이티브 창에서 Alt+F4 후 창 0개 및 시작한 앱 프로세스 종료 확인 |
| 개발 포트 중복 실행 | 기대한 실패: 두 번째 `npm run dev`가 `Port 1420 is already in use`로 종료 코드 1 반환 |
| 민감정보 패턴 검사 | 통과: 소스·설정 15개 파일에서 지정된 비밀키·토큰 패턴 검출 0건 |

기능 로직은 아직 없어 별도 유닛 테스트를 추가하지 않았다. 폴더·AI·DB·MCP·Unity 및 설치본 테스트는 미실행이며 해당 ROADMAP 작업에서 검증한다.

## R00-03 검증 기록 (2026-10-28)

- `npm run build` 통과. `npm test` 1개 통과: 임시 loopback 포트에서 점유 거부·기존 서버 보존·성공 후 포트 재사용 확인.
- `npm run dev`: Windows 앱에서 `http://127.0.0.1:1420/` 개발 화면의 제목·한국어 문구 확인. Alt+F4 후 CLI 종료 코드 0, 앱 프로세스 0개, 포트 1420 리스너 0개 확인.
- 포트가 사용 중이면 사전 검사가 종료 코드 1을 반환하고 앱 프로세스를 생성하지 않음. 기본 Tauri 명령의 포트 충돌 시 앱 잔류 문제를 사전 검사로 방지.
- 원본 파일 접근·AI·DB·Core 실행 코드는 추가하지 않았으며 제품 기능 테스트는 해당 작업 범위에서 수행한다.

## R00-04 검증 기록 (2026-10-28)

- `npm run build` 통과. `npm test` 기존 회귀 테스트 1개 통과. Vue Router 4.6.4 추가 후 npm 의존성 감사 취약점 0건.
- 브라우저 자동 검사: 기본 테마 `dark`와 실제 배경색 확인 → 화면 설정 → 라이트 선택 후 배경색 변경 → 라이브러리 이동·뒤로 가기 후 라이트 유지 → 새로고침 시 같은 해시 경로와 기본 다크 복귀 확인.
- 라디오 방향키로 테마 변경, `본문으로 이동` Enter로 현재 경로를 바꾸지 않고 본문 포커스 이동 확인. 콘솔 오류·경고 0건.
- Windows 개발 창에서도 라이브러리·화면 설정 이동과 다크→라이트→다크 실제 표시를 확인하고 정상 종료했다.
- 테마 상태는 Vue 공용 반응형 메모리에만 둔다. 새로고침·재실행 후 영속 저장은 이번 범위에 포함하지 않는다.

## R00-05 검증 기록 (2026-10-28)

- `npm run build:installer` 통과: 타입 검사·프런트엔드 빌드·Rust release 빌드 및 x64 NSIS 번들 1개 생성. 공식 NSIS 도구와 Tauri 플러그인 다운로드 해시 검증 통과.
- 생성 파일: `src-tauri/target/release/bundle/nsis/AI Asset Hub_0.5.0_x64-setup.exe`, 1,941,376바이트. SHA-256: `a193cd4710afeffd13c59fe5ebce24d3d47d3d18021dce02f7bb3bd6e3f51aa6`.
- 실제 설치: 기존 설치·대상 폴더가 없는 것을 확인한 뒤 NSIS 무인 설치(`/S /D=...`) 종료 코드 0. `%LOCALAPPDATA%\Programs\AIAssetHubDev`의 실행 파일과 HKCU 제거 프로그램 등록 버전 `0.5.0`·설치 경로 확인.
- 초기 원시 해시 비교 실패 원인은 Tauri 번들 종류 표시 `UNK`→`NSS`의 3바이트 차이였다. 사용 중인 `tauri-utils`의 표시 정의와 빌드 로그를 확인하고 메모리에서 해당 표시만 정규화한 비교로 나머지 전체 바이트 일치 확인. 설치 파일을 수정하지 않았다.
- 설치 앱 UI: Vite 서버 종료 및 PATH를 Windows System32로 제한한 환경에서 설치된 실행 파일 실행 → `http://tauri.localhost/#/library`의 다크 화면 → 화면 설정 → 라이트 전환 → Alt+Left 후 라이브러리와 테마 유지 → Alt+F4 정상 종료·프로세스 소멸 확인.
- `npm test` 회귀 테스트 1개 및 소스/설정 민감정보 패턴 검사 통과. 실행 시 원본 에셋·AI·Core에 접근하는 코드는 없다.
- 한계: 설치본은 `NotSigned` 개발본이다. 깨끗한 PC, WebView2 미설치 PC, 설치 마법사 수동 클릭, 삭제·업그레이드 및 P0 제품 기능 검증은 미실행이다.

## R01-01 검증 기록 (2026-10-28, 내부 자동화만 수행)

- `npm run check`: 컴포넌트 테스트 8개와 기존 포트 회귀 1개, 총 9개 통과 및 Vue/Vite 타입 검사·프로덕션 빌드 통과.
- `tests/topbar.test.mjs`는 Vite JavaScript 빌드 API로 실제 App·컴포넌트·라우터·스토어를 컴파일하고 Node 프로세스 안의 jsdom에 마운트한다. `.artifacts/component-tests/`에 테스트 번들을 생성하며 HTTP 서버·실제 브라우저·Windows 앱은 실행하지 않는다.
- 확인 항목: 검색 필드 접근성·현재 위치, Unicode/HTML 형태의 문자 입력과 submit 차단, 지우기 버튼·Escape·입력 포커스, 한글 조합 완료 반영과 조합 중 Escape 보존, 실제 라우트와 브레드크럼 이동·검색어 유지, 본문 이동 포커스, 기존 테마와 알 수 없는 경로 복구.
- 외부 전송·Core 호출과 새 창 열기는 차단 mock으로 감지하며 호출 0건을 확인한다. 테스트 입력은 고정 fixture이고 실제 라이브러리·AI 결과를 사용하지 않는다.
- 초기 테스트에서 발견한 브레드크럼의 중복 현재 페이지 표시를 수정했다. 테스트 환경의 Vue 선행 로드·DOM 생성자 누락으로 발생한 초기 실패도 보정하고 최종 검사를 통과했다.
- 개발 의존성으로만 jsdom 28.1.0 추가. Node 24.12 호환 및 설치 시 npm 감사 취약점 0건 확인. 기존 Node 러너·Vite·Vue를 유지한다.
- 미검증: 시각적 배치·크기별 실제 렌더링·Windows 입력기·Tauri/설치본 화면. 실제 에셋 검색·필터링은 이번 범위에 포함하지 않는다.

## R01-02 검증 기록 (2026-10-28, 내부 자동화만 수행)

- `npm run check`: 라이브러리 패널 테스트 11개 추가, 기존 9개를 포함해 총 20개 통과. Vue/Vite 타입 검사·프로덕션 빌드 통과. 새 의존성 추가 없이 기존 Node·Vite·jsdom 사용.
- 실제 App의 기본 빈 트리·`전체 에셋` 선택·구분선 이름/범위/제어 대상과 CSS 너비 상태를 검사했다. 생산 화면에 테스트 폴더가 섞이지 않음을 확인했다.
- 격리된 컴포넌트 입력으로만 `fixture-*` 폴더 트리를 제공해 ID 선택·전체 선택 해제·접기/펼치기·중첩 group·리프 상태·보이는 계층의 방향키·Home/End·Enter/Space 및 단일 탭 정지를 검증했다. 폴더명 마크업은 텍스트로 유지되고 특수문자 ID도 그대로 전달된다.
- 키보드/포인터 너비 조절·200/360px 경계·기본값 복원·다른 포인터 무시·보조 버튼 무시·비유한 너비 거부를 확인했다. Escape 복원·pointerup/pointercancel·가상 창 blur·해제 이벤트 누락 시 버튼 상태 감지 및 화면 이동 후 리스너 정리/너비 유지도 검증했다.
- 기존 차단 mock에서 외부 전송·Core·새 창 호출 0건. 실제 폴더·원본 파일·DB·모델에는 접근하지 않았다.
- 초기 타입 검사에서 재귀 렌더 함수의 반환형 누락을 확인해 `VNode`로 명시하고 최종 검사를 통과했다.
- 미검증: 실제 화면의 배치/리사이즈·OS 포인터·보조기술·Tauri/설치본. 실제 등록 폴더 표시·스캔·폴더별 에셋 필터링은 M03 이후 범위다.

## R01-03 검증 기록 (2026-10-28, 내부 자동화만 수행)

- `npm run check`: 갤러리 테스트 7개 추가, 기존 20개를 포함해 총 27개 통과. Vue/Vite 타입 검사·프로덕션 빌드 통과. 기존 Node·Vite·jsdom을 사용했으며 새 의존성은 없다.
- 실제 App의 에셋 0개·빈 상태·그리드 기본 선택·예시 에셋 및 이미지 미포함을 확인했다. 빈 상태에서 보기 전환과 잘못된 보기 값 거부도 검사했다.
- 격리된 fixture 입력으로 카드의 이름·유형·ID·순서·개수와 표의 열 제목·셀 값, 그리드/목록 왕복 시 데이터 일치를 검증했다. 반응형 입력을 2→1→0개로 갱신했을 때 개수·표·빈 안내가 일치하며 선택한 보기 방식은 유지된다.
- 실제 라우터로 설정 화면 왕복 후 갤러리 보기·검색어·패널 너비가 함께 유지됨을 확인했다. 긴 이름·HTML 형태 이름/유형·특수문자 ID는 원문 텍스트/속성으로 유지되고 실행 가능한 img/script 노드를 생성하지 않는다.
- 모든 컴포넌트 사례에서 차단 mock의 외부 전송·Core·새 창 호출 0건, Vue 오류·경고 0건을 확인했다. 실제 폴더·원본 파일·DB·AI에는 접근하지 않았다.
- 미검증: 실제 화면의 시각적 배치·크기별 렌더링·보조기술·OS 동작·Tauri/설치본. 실제 파일/썸네일·정렬/다중 선택은 M03, 검색 결과 연동은 M04 범위다. 화면을 열거나 직접 조작하지 않았다.

## R01-04 검증 기록 (2026-10-28, 내부 자동화만 수행)

- `npm run check`: 7개 추가해 총 34개 통과, 타입 검사·프로덕션 빌드 통과. 기존 테스트 환경·의존성 유지.
- 실제 App의 선택 전 빈 상세, 연결된 접기 버튼과 hidden/aria-expanded, 설정 화면 왕복 후 접기 상태 유지를 확인했다.
- 실제 LibraryView에만 fixture 목록을 입력해 그리드/목록 단일 선택 → 상세 이름/유형 갱신, 선택 강조, 기본/분석 탭, 좌우/Home/End 자동 활성화·포커스·tabpanel 연결을 검사했다.
- 에셋 변경 시 기본 탭 복귀, 선택한 에셋 제거 시 상세 초기화, 접힌 동안 동일 ID 데이터 갱신과 선택/탭 보존, 마크업 형태 이름·유형·분석문의 텍스트 이스케이프를 확인했다.
- 외부/Core/새 창 호출 및 Vue 오류·경고 0건. 분석 텍스트는 fixture 입력이며 실제 분석 실행/결과 조회가 아니다.
- 미검증: 실제 화면 배치·보조기술·OS 포인터/키보드·Tauri 설치본. 파일 속성/미리보기 조회는 M03, 실제 분석 결과 연결은 M06 범위다.

## R01-05 검증 기록 (2026-10-28, 내부 자동화만 수행)

- `npm run check`: 반응형·키보드 테스트 9개 추가, 총 43개·타입 검사·프로덕션 빌드 통과.
- 320/569/570/768/800/859/860/900/1100px과 패널 240/360px의 정책 경계, 상세 접힘 여부를 검사했다. 실제 컴포넌트의 ResizeObserver 입력 → 배치 속성 변경·좁은 구분선 제거·다시 확장 시 너비 복원을 확인했다.
- 드래그 중 축소 시 후속 pointermove 무시와 갤러리 포커스 복구, 크기 변경 후 선택/목록/접기 유지, observer 해제·NaN 무시·미지원 시 window resize 대체 경로를 확인했다.
- F6/Shift+F6 실제 영역 순환, 선택 에셋/활성 탭 우선 포커스, Tab 비차단 및 그리드/목록 방향키·Home/End 이동이 선택을 바꾸지 않는 것을 확인했다.
- 초기 테스트의 포인터 도우미 호출 인자/await 누락을 바로잡고 최종 검사를 통과했다. 외부/Core 호출·Vue 오류·경고 0건. 실제 화면·브라우저를 실행하지 않았다.
- 미검증: jsdom은 픽셀 배치 엔진이 없으므로 실제 창 크기별 렌더링·스크롤·시각적 겹침·보조기술·OS 키보드·Tauri 설치본은 검증하지 않았다.

## R01-06 검증 기록 (2026-10-28, 내부 자동화만 수행)

- `npm run check`: 상태/오류 테스트 11개 추가해 총 54개 통과, 타입 검사·프로덕션 빌드 통과. M01 최종 회귀로 상단 바·트리·갤러리·상세·반응형·키보드 테스트를 함께 실행했다.
- 실제 App에서 초기 상태 바 부재, 실제 테마/보기 변경 → 실제 상태 변경과 완료 표시·화면 이동 후 유지·완료 지우기, 같은 보기 중복 클릭 시 작업 미생성을 확인했다.
- 별도 fixture 이벤트로 동시 작업·실측 진행 건수·입력 객체 복사·완료/취소·0/0건 완료를 검증했다. unknown/음수/비정수/초과 건수·역행·총수 변경·다른 작업 유형·완료 이후 늦은 이벤트를 거부하고, 진행 건수가 없는 이벤트에는 진행률을 만들지 않는다.
- 실제 콜백을 실행하는 명령 래퍼의 대기/성공·예외/실패·단 1회 실행을 확인했다. 예외·알 수 없는 오류 코드·경로·키 형태 문자열은 표시/기록/로그에 보존하지 않고 고정 오류 문구만 알린다. 오류 닫기·완료 정리는 진행 중 작업·미확인 오류를 보존한다.
- 최대 20개 상태 이력과 상한 도달 시 활성 작업/미확인 오류 비삭제를 검증했다. 테스트의 비동기 명령 완료/DOM 갱신 대기를 보정하고 최종 검사를 통과했다. 외부/Core/새 창 호출·Vue 오류·경고는 모든 사례에서 0건이다.
- fixture 스캔·분석·Unity 이벤트는 표시 계약 테스트이며 해당 기능의 실제 실행 증거가 아니다. 실제 Core 이벤트 연결·파일/모델/Unity 작업·설치본/화면/보조기술은 미검증이다. 실제 화면을 열거나 직접 조작하지 않았다.

## R02-01 검증 기록 (2026-10-28, 내부 자동화만 수행)

- `npm run check`: 기존 Node 54개와 Python unittest 11개, 총 65개 통과. 프런트엔드 타입 검사·프로덕션 빌드 통과. 현재 Python 3.13.15, 신규 pip/npm 의존성 설치 없음.
- `python-core/tests/test_core.py`는 실제 Core 모듈의 건강 상태·응답 키·제품/Python 버전·현재 PID·UTC 타임스탬프·DB `not_configured`를 확인한다. 가동 시간의 250/500ms 검사는 격리된 단조 시계 fixture이며 그 외 프로세스 값은 실측이다.
- 실제 `python -B -m ai_asset_hub_core health.get` 자식 프로세스의 PID와 JSON 응답 PID 일치·stdout 한 줄·stderr 없음·종료 코드 0을 검증했다. 요청 UUID 생성/보존, 잘못된 ID·요청 형식·추가 필드·매개변수·미지원/분석 명령 거부와 종료 코드 2를 확인했다.
- 주입한 예외에서 안전한 `INTERNAL_ERROR`·종료 코드 1·원문/traceback/로그 미노출을 검증했다. 별도 Python 프로세스에서 import 이후 audit hook으로 파일 열기/변경·디렉터리 스캔·SQLite·소켓·추가 프로세스 실행을 차단한 상태로 실제 health 명령 성공을 확인했다.
- 첫 audit 검사에서 argparse의 표준 라이브러리 지연 import까지 차단한 것을 확인해 명령 처리 자체에 guard를 적용했다. Node 테스트 자동 탐색이 Python 실행 도우미를 중복 실행하는 문제는 파일명을 바꿔 해결했다. 최종 결과는 중복 없는 Node 54개 + Python 11개다.
- UI·Tauri는 변경하지 않았고 실제 화면을 열지 않았다. Core는 개발 조회 후 종료하며 UI 연결/수명주기/인증은 R02-02, DB는 R02-03, 설치본 Sidecar는 R02-05에서 검증한다. 이를 실제 앱 연결·DB 성공·제품 기능 완료로 보고하지 않는다.

## R02-02 검증 기록 (2026-10-28)

- `npm run check`: Node 57개·Python 14개 및 타입·빌드 통과. `cargo test --manifest-path src-tauri/Cargo.toml --lib`: Rust 2개 통과. `cargo fmt` 적용.
- Rust는 실제 Python 자식으로 두 health 응답의 동일 PID/서로 다른 UUID, EOF 종료·명시적 새 세션·실행 파일 없음의 고정 오류를 검증했다. Python은 다중 프레임/EOF·잘못된 UTF-8/JSON·중복 키/NaN·초과/불완전 프레임 거부를 검사했다.
- DOM에서는 브라우저 미연결·fixture health 성공/DB 미연결·오류 원문 비노출·명시적 재연결을 검증했다. 실제 프로세스 결과와 UI fixture를 구분한다. 새 의존성은 공식 `@tauri-apps/api` 및 기존 Cargo 잠금 파일의 serde/serde_json/uuid 직접 참조다. npm 감사 0건.
- 실제 GUI·OS 화면·설치본은 실행하지 않았다. DB·배포 Sidecar·비정상 종료 복구 강화는 다음 작업 범위다.

## R02-03 검증 기록 (2026-10-28)

- `npm run check`: Node 57개·Python 23개 및 타입·빌드 통과. DB 9개 테스트 추가, 신규 의존성 없음.
- 격리된 `.artifacts/core-tests` 아래 한글 경로 DB에서 빈 20개 테이블·스키마/WAL/FK 실측·재오픈·설정 영속화·JSON/FK 거부·모델 기본 OFF를 확인했다.
- 성공/실패 업그레이드·사전 백업 내용·롤백·체크섬 변경/손상/다른 용도 DB 거부를 검증했다. fixture 성공 결과의 불변성·다른 에셋 결과 참조 거부·실패 재분석 후 기존 성공/사용자 설명 보존도 확인했다.
- 초기 sandbox 임시 경로의 접근 제한은 프로젝트 내부 격리 경로로 변경했다. 실제 운영 DB·원본·모델·네트워크·화면은 사용하지 않았다. Tauri 경로 연결은 다음 작업 범위다.

## R02-04 검증 기록 (2026-10-28)

- `npm run check`: Node 57개·Python 28개·타입·빌드 통과. Rust 테스트 3개 통과·fmt 적용.
- 격리 경로에서 개발/운영 DB 분리·환경 변경 거부·중복 쓰기 거부·정상 종료 후 잠금 해제·알 수 없는 디렉터리/상대 경로/손상 표식·손상 DB 보존을 확인했다.
- Python이 쓴 설정을 실제 CLI 프로세스로 두 차례 조회 후 재오픈해 보존을 확인했다. Rust 실제 파이프 세션도 임시 운영 경로의 DB ready/schema 1·종료·재시작을 검증했다. 실제 사용자 AppData·원본·화면은 테스트에 사용하지 않았다.

## R02-05 검증 기록 (2026-10-28)

- `npm run check`: Node 57개·Python 28개·타입·빌드 통과. Rust 기본 3개 통과, 패키지 전용 1개는 `AI_ASSET_HUB_SIDECAR_DIR`를 지정한 `cargo test --lib --locked -- --ignored`에서 별도 통과했다. 일반 실행에서 전용 1개는 의도적으로 ignored다.
- `npm run build:installer`로 CPython/SQLite/마이그레이션을 동봉한 x64 NSIS 생성. 기본 설치본 9,289,722바이트, SHA-256 `5177964f68361be44bf90baaa91856725b195db33ddc3be911939a7e3b235249`. Sidecar SHA-256 `8f45865b860a4342da09e80a4e2a5a33abf55affb9ac54e717c8d6817efa0435`.
- 기존 설치 보호를 위해 생성 NSIS에서 제품/등록 이름만 바꾼 검증 설치를 `.artifacts/m02-installed-UUID`에 무인 설치했다. 원래 설치본의 파일을 변경하지 않았고 기존 등록 위치/버전 유지도 확인했다. 검증 설치만 제거했다.
- 실제 설치 앱의 `--verify-core`는 Tauri 창을 생성하지 않고 release와 동일한 관리자로 Sidecar를 자동 시작한다. PATH=System32·잘못된 PYTHONHOME/PYTHONPATH 환경에서도 실제 PID health·DB ready/schema 1·SQLite 3.50.4·WAL·stderr 없음·종료 후 Core PID 소멸을 확인했다. SQLite/DB 검증 경로도 새 전용 fixture다.
- 초기 제거 검사의 NSIS 후속 프로세스 대기 누락을 보정하고 최종 무인 설치/제거 절차가 통과했다. NSIS 공식 템플릿의 한국어 `choowHowToInstall` 번역 경고 1개는 남으며 실제 GUI는 검증하지 않았다.
- 깨끗한 PC·WebView2 신규 설치·실제 GUI·정식 배포 서명/업그레이드는 미검증이다. 원본·AI·유료 모델·Unity 작업은 실행하지 않았다.
- Rust Clippy의 중첩 조건 경고 2개를 정리한 후 `cargo clippy --lib --locked -- -D warnings` 통과·fmt 적용.

## R02-06 / M02 최종 검증 (2026-10-28)

- `npm run check`: Node 61개·Python 29개, 타입 검사·프로덕션 빌드 통과. `cargo test --lib --locked`: 6개 통과·패키지 전용 1개 ignored, 해당 1개는 별도의 `-- --ignored` 실행에서 통과. 합계 중복 없는 테스트 97개다. `cargo clippy --all-targets --locked -- -D warnings`·fmt 통과.
- Rust는 실제 Core 강제 종료→원인 유지/암묵 재시작 없음→명시 재연결/새 PID/DB ready, 응답 정지→100ms 테스트 제한/수거, 잘못된 JSON/상관 ID/초과 크기 프레임→안전한 오류/수거를 확인했다. 기본 제품 응답 제한은 3초이며 테스트의 100ms는 격리 fixture다.
- Python은 설정을 저장한 DB로 실제 Core를 띄운 뒤 강제 종료해 OS 잠금 해제·WAL 재오픈·커밋 데이터 보존·분석 작업 0개를 확인했다.
- DOM fixture에서는 5초 감시의 종료 감지·실패 후 자동 재연결 없음·DB 오류/잠금 안내·불완전 health 거부·원문 비노출·동시 요청 방지·해제 후 타이머/늦은 응답 정리를 검증했다. 실제 프로세스와 UI fixture는 별도 증거다.
- 최종 `npm run build:installer` 성공. 설치본 9,292,156바이트, SHA-256 `cbe483921a88455f2bcd32177729bae87e4cb74ea69b6ecfb889e5a08dbc02c2`. 분리된 제품/등록 이름의 같은 payload로 무인 설치·실제 설치 파일 `--verify-core`·Python 없는 PATH/잘못된 Python 환경·DB/WAL/종료·검증 설치 제거·기존 설치 등록 보존을 재확인했다.
- 실제 화면/브라우저를 열거나 조작하지 않았다. 현재 PC에는 개발 도구가 있으므로 깨끗한 PC의 WebView2/시스템 DLL·실제 GUI·정식 서명/업그레이드는 미검증이다. NSIS 템플릿 한국어 경고는 R02-05 기록과 같다. 실제 에셋·AI·MCP·Unity 작업은 수행하지 않았으며 M03 이후 범위다.

## R03-01 검증 기록 (2026-10-28)

- `npm run check`: Node 69개·Python 29개, 타입·프런트엔드 빌드 통과. `cargo test --lib --locked`: Rust 11개 통과, 기존 패키지 전용 1개는 ignored이며 이번 작업에서 미실행. 합계 실행한 테스트는 109개다. `cargo clippy --all-targets --locked -- -D warnings`·fmt 통과.
- DOM 8개 추가: 브라우저 미제공·클릭 전 호출 없음·고정 단일 명령/입력 인자 없음·한글 경로 반영·취소 시 이전 선택 유지·고정 오류/비밀 원문 비노출·중복/늦은 응답 거부·문자 이스케이프·선택 지우기·잘못된 결과 거부를 검증했다. 실제 App 라우트 왕복 후 선택 유지, 빈 트리/0개 에셋과 선택 시 Core/등록/분석 미호출도 확인했다.
- Rust 5개 추가: 화면 없는 선택 closure로 취소·실패·동시 선택/패닉 후 잠금 해제를 확인했다. UNC/장치/상대/상위 이동/드라이브 루트 거부, 드라이브 유형 정책의 네트워크/알 수 없음 거부와 로컬 유형 허용을 검증했다.
- 실제 `.artifacts/folder-tests/UUID/한글 선택 폴더` fixture를 선택 어댑터에 전달해 경로 정규화·지정 파일 내용/개수 보존·파일/누락 경로 거부를 확인했다. 테스트 경로의 내부 `..`를 정규화해 실제 picker와 같은 입력으로 보정했다. 기존 사용자 폴더·원본·운영 DB는 사용하지 않았다.
- 신규 직접 의존성은 공식 Rust `tauri-plugin-dialog` 2.8.4이며 Cargo.lock에 고정했다. JS dialog/fs 패키지·범용 권한·네트워크/모델 호출은 추가하지 않았다.
- 실제 OS 폴더 선택 창·mapped network 연결·OS 접근성·설치본은 미검증이다. D-019에 따라 앱/선택 창을 열거나 직접 조작하지 않았고 설치본 재빌드·패키지 전용 검사는 미실행이다. 실제 등록/스캔/AI 기능 완료를 의미하지 않는다.

## R03-02 검증 기록 (2026-10-28)

- `npm run check`: Node 76개·Python 37개, 타입·프런트엔드 빌드 통과. `cargo test --lib --locked`: Rust 12개 통과·기존 패키지 전용 1개 ignored/이번 작업 미실행. 합계 실행 테스트 125개. `cargo clippy --all-targets --locked -- -D warnings`·fmt 통과.
- Python 8개 추가: 실제 격리 폴더/DB의 UUID 생성·한글 경로·대소문자 중복·동일 ID 재활성·DB 재오픈, 부모/자식 중첩 양방향 거부, 비활성 해제 후 원본/에셋/설명 유지, 누락/파일/루트/네트워크/잘못된 입력 거부를 확인했다.
- 권한·SQL 오류의 원문 비노출, 51개 긴 경로의 페이지 전체 조회/각 16KiB 미만 응답, 알 수 없는 ID·DB 부재를 검사했다. 따옴표/SQL 형태의 실제 폴더명도 파라미터 값으로 저장되고 스키마는 유지된다. 네트워크/하위 프로세스를 차단한 등록·조회·해제에서 에셋·분석·임베딩·Unity 기록 0개를 확인했다.
- Rust 실제 파이프에 등록→중첩 오류→같은 PID health→프로세스 종료/재시작→같은 ID 목록→해제를 수행했다. 비허용 분석 명령과 초과 크기 요청은 전송하지 않고 정상 세션을 보존하며, 원본 fixture 내용 유지도 확인했다. 마지막 선택과 다른 등록 경로는 거부한다.
- DOM 7개 추가: 실제 목록 입력→트리·0개 에셋, 명시 등록/중복 응답 단일 항목·해제 후 선택 초기화, 실패 시 확인 목록/선택 보존·오류 원문 비노출, 조회 실패≠빈 DB, 다중 페이지/반복 커서 거부·중복 쓰기 방지·늦은 응답 무시·새 UI 세션 목록 복원·문자 이스케이프를 확인했다.
- 실제 파일/DB 증거와 UI fixture를 구분한다. 새로운 의존성·DB 마이그레이션·원본 수정·스캔·AI 호출은 없다. 실제 GUI/OS 선택 창·설치본 재빌드/배포 검증은 미실행이며 다음 스캔/필터 작업의 성공을 의미하지 않는다.

## R03-03~R03-09 / M03 최종 내부 검증 (2026-10-28)

- `npm run check`: Node 81개·Python 41개·타입·프로덕션 빌드 통과. `cargo test --lib --locked`: 12개 통과, 패키지 전용 1개는 별도 `-- --ignored`에서 통과. 중복 없는 최종 테스트 135개. `cargo clippy --all-targets --locked -- -D warnings`·fmt 통과.
- Python 실제 fixture: 한글/중첩 경로 수집·파일명/크기·반복 수집 ID 유지·원본 내용 보존·분석 작업 0개, PNG 원본 해상도/캐시 동일성/원본 바이트 불변, 손상·미지원·누락·권한 실패 후 DB 정상, 신규/변경/누락 건수·기존 사용자 설명 유지·부분 스캔 미관찰 파일 보존을 확인했다. 삭제/변경 상황은 테스트가 생성한 임시 파일로만 재현했다.
- DOM: 경로 구간별 계층/접두어 충돌 필터, 가시성 이전 이미지 요청 0회/이후 고정 JPEG data URL, 선택 ID의 실측 크기/해상도·다른 선택/누락 시 이전 값 제거, Ctrl/Shift 다중 선택·선택 해제·그리드/목록 유지·61개 입력의 60개 렌더/페이지 이동·정렬을 검사했다. 원본 데이터와 합성 fixture를 구분한다.
- Rust 실제 Core 파이프: 등록→스캔→인덱스→현재 메타데이터→미지원 썸네일 응답·재시작/ID 복원을 확인했다. 패키지 전용 검사에서는 PATH=System32인 Sidecar에 실제 1px PNG를 등록/수집하고 Pillow JPEG ready·해상도·원본 바이트 보존·DB 재시작을 확인했다.
- `npm run build:installer` 성공. 최종 NSIS 13,439,139바이트, SHA-256 `5442007a81021003c9cbee1091cf9ef061c152d742f11f0b4a7f54e55016b7f9`. `scripts/verify-installer.ps1`의 분리된 제품/등록 이름으로 동일 payload를 무인 설치해 실제 설치 파일의 Core/SQLite/WAL/종료·기존 설치 등록 보존·검증 설치 제거를 확인했다. 실제 창/브라우저는 만들지 않았다.
- 새 런타임은 고정 Pillow 13.0.0이며 프로젝트 전용 환경과 설치본에만 포함한다. Windows venv 실행기의 PID 차이를 발견해 기반 Python 프로세스가 전용 site-packages를 로드하도록 수정하고 실제 PID 검사를 유지했다. 테스트 모듈 탐색·메타데이터 타입·선택적 Boolean 기본값·부분 권한 실패 주입도 보정 후 최종 통과했다.
- 실제 OS 폴더 선택기·GUI 배치/접근성·깨끗한 PC·서명·대량 파일 성능/장시간 작업은 미검증이다. 빈 물리 하위 폴더는 현재 파일 인덱스 트리에 나타나지 않는다. 변경/캐시 판정은 크기/mtime 기반이며 내용 해시 검증은 후속이다. Core의 현재 3초 응답 제한을 유지하며 긴 작업 큐/취소 강화는 안정화 범위다. NSIS 템플릿의 기존 한국어 번역 경고 1개는 유지된다.

## R04-01 내부 검증
- `npm run check`: Node 83개, Python 43개 통과, 타입 검사·빌드 성공. 태그 입력/삭제/실패 DOM 및 DB 재개방·원본 불변·작업 미생성 검증.
- `cargo test --lib --locked`: 12개 통과, 패키지 전용 1개 제외. 실제 화면 조작은 수행하지 않음.

## R04-02 내부 검증
`npm run check`: Node 84개·Python 44개, 타입 검사·빌드 통과. 사용자 정보 명시 저장 DOM, 표시명 복귀·재개방·원본 불변 검증. Rust 12개 통과(패키지 1개 제외). 실제 화면 미검증.

## R04-03 내부 검증
`npm run check`: Node 85개·Python 45개, 타입 검사·빌드 통과. 실제 다중 선택 이벤트에서 선택 ID만 전송, DB 전체 롤백·기존 태그 유지 확인. Rust 12개 통과(패키지 1개 제외). 태그 최대 32개/합계 512자·단일 64자, 일괄 최대 100개. 실제 화면 미검증.

## R04-04 내부 검증
`npm run check`: Node 87개·Python 45개, 타입 검사·빌드 통과. 검색/초기화·태그 조건에서 실제 카드 수 감소, 한글/복수 공백/대소문자/별칭과 원본 이름 검색 검증. 서버 전문 검색은 다음 R04-05. 실제 화면 미검증.

## R04-05 내부 검증
`npm run check`: Node 89개·Python 49개, 타입 검사·빌드 통과. FTS5 MATCH 실측·한글/부분 단어/공백/대소문자·사용자 수정 동기화·201개 이상 검색 페이지·비활성 폴더 제외·DB v1→v2 백업/기존 자료 재색인·인덱스 integrity-check 통과. Rust 12개 통과: 실제 파이프에서 태그/설명/일괄 수정·한글 검색·재시작 유지 검증. 화면 조작 미실행.

## R04-06 / M04 최종 내부 검증
- `npm run check`: Node 94개·Python 50개 통과, 타입 검사 및 Vite 프로덕션 빌드 성공.
- Rust `cargo test --lib --locked -- --include-ignored`: 13개 통과. 실제 파이프·Core 재시작·패키지 FTS5/한글 검색과 PNG 썸네일 검증 포함. `cargo clippy --all-targets --locked -- -D warnings` 통과.
- 복합 폴더/검색/태그/타입/분석 상태 DOM, 정확한 나노초·분석일 정렬, 마지막 시도 실패+성공 결과 보유의 중첩, 사용자 태그 삭제 시 AI 태그/결과 보존을 검증했다. 테스트의 분석 이력은 테스트 소유 DB에 직접 만든 fixture이며 실제 모델 호출은 없다.
- 메타데이터 로드 실패 시 빈 값 저장 차단·재시도, 태그 갱신 중 표시명 초안 보존, 목록 갱신 경합 후 재조회도 검증했다.
- 실제 화면/시각 배치·깨끗한 PC·대규모 라이브러리 검색 성능은 미검증. 의미 검색/모델 실행은 이번 범위에 포함하지 않는다.

- 최종 `npm run build:installer` 및 `scripts/verify-installer.ps1` 통과: 전용 임시 설치본의 DB v2 초기화·실제 Core PID 종료·Sidecar 해시·조용한 제거 확인, 기존 설치 보존. 실제 GUI는 열지 않았다. 소스와 동봉 002_search.sql 해시 일치.
- 설치 파일 13476050 bytes, SHA256 `a65593995d5a9d5166d5a34fa5abd91c33c612ba178cc0ddf23aecf483e26221`. NSIS 기본 템플릿의 Korean `choowHowToInstall` 문자열 경고 1개는 기존과 동일하다.

## R05-01 내부 검증
`npm run check`: Node 95개·Python 53개, 타입 검사·빌드 통과. 모델 등록/목록 DOM·재개방·중복·잘못된 입력·페이지 검증. Rust 12개 통과(기존 패키지 전용 1개 제외). 연결/입력 지원 검증은 R05-02 이후이며 현재 등록 유형은 사용자 선언이다. 실제 화면 미검증.

## R05-02 내부 검증
`npm run check`: Node 96개·Python 55개·타입/빌드 통과. Rust 12개 통과(패키지 1개 제외). 별도 검사 버튼·타임아웃·기능 파싱·네트워크 리다이렉트 차단을 검증. 성공 응답은 테스트 fixture, 실제 Ollama 실행 파일은 PATH에서 발견되지 않아 실제 모델 실행 가능성은 미검증.

## R05-03 내부 검증
Node 97개·Python 56개·타입/빌드, Rust 12개 통과. 외부 동의 없는 요청 0건, 무료/유료·NaN 가격 거부, 인증 미검증·추론 호출 없음 표시를 fixture 응답으로 확인했다. 실제 공급자 인증/추론은 실행하지 않았다. 카탈로그 조회 성공을 인증 성공으로 표시하지 않는다.

## R05-04 내부 검증
Node 98개·Python 57개·타입/빌드 통과. 실제 Windows 테스트 전용 vault 항목의 저장/읽기/삭제와 DB/응답 키 미포함 확인. UI 마스킹·명시 저장·실패 후 입력 초기화 검증. 실제 OpenRouter 인증은 fixture로 검증하며 사용자 키나 생성 API를 호출하지 않았다. Rust 12개 통과(패키지 1개 제외).

## R05-05 내부 검증
Node 99개·Python 59개·타입/빌드 통과. 유료 기본 OFF·미인증/미승인/0예산 활성화 거부, 정확한 0.1+0.2 예약·한도 초과 롤백·정책 재저장 시 예약 누적 유지 검증. Rust 12개 통과. 실제 생성/과금 호출은 하지 않았다. 예약 가드는 후속 분석 엔진이 호출할 내부 기반이며 현재 모델 관리 화면에서는 예약이나 분석을 생성하지 않는다.

## R05-06 / M05 최종 내부 검증
- `npm run check`: Node 100개·Python 60개 통과, 타입 검사와 프로덕션 빌드 성공. 입력 비호환 버튼 차단/서버 재검증, 스냅샷 버전 변경·이전 값 불변·선택 해제·분석 작업/임베딩 미생성 확인.
- Rust 12개(패키지 전용 1개 제외) 및 `cargo clippy --all-targets --locked -- -D warnings` 통과. 실제 파이프에서 Registry 등록/목록·실제 UUID·비활성 기본값·미확인 모델 선택 차단까지 검증.
- Windows 테스트 전용 자격 증명 저장/읽기/삭제 실측, 정적 비밀 패턴 검사 통과. 모델 관리의 성공/가격/인증 데이터는 명시된 fixture를 사용했으며 실제 사용자 키·생성 API·유료 모델·원본 에셋을 호출/변경하지 않았다.
- 실제 Ollama 모델 추론/실사용 공급자 인증·깨끗한 PC·대규모 모델 목록 성능 및 실제 화면 배치는 미검증. 실제 AI 분석과 과금 정산은 M06 이후 범위다.


- 최종 Rust `--include-ignored` 13개 통과: 새 PyInstaller Core에서도 Registry UUID·기본 OFF·비호환 선택 차단을 실측했다. `npm run build:installer` 및 `scripts/verify-installer.ps1` 통과: 임시 전용 설치본의 DB v2·Core 실제 PID 종료·Sidecar 해시·조용한 제거/기존 설치 보존 확인, GUI 미실행.
- 설치 파일 13544949 bytes, SHA256 `61f157a587a5c26b9271cbeac4e4957f99b79fd39274d4ae4742af8e8ecbbbff`. 기존 NSIS Korean choowHowToInstall 문자열 경고 1개 유지.

## R06-01 내부 검증
`npm run check`: Node 100개·Python 61개·타입/빌드 통과. 대기 상태 DB 재개방·원본 변경 시 해시 무효화, 기존 실패 재분석 후 성공 결과 유지 회귀 통과. 실제 화면 조작 없음.

## R06-02 내부 검증
Node 101개·Python 61개·타입/빌드 통과. 다이얼로그 열기/닫기·Escape 포커스 복원·프로필 조회만 수행·검토 전 시작 비활성 확인. 대상 미리보기와 실행 연결은 R06-03~05에서 구현. 실제 화면 미검증.

## R06-03 내부 검증
Node 102개·Python 62개·타입/빌드 통과. 성공 보유+마지막 실패의 중첩·선택 ID 검증·대상 개수·미리보기 Job 미생성 확인. 범위 결합은 다음 R06-04, 모델/비용 실행 검증은 R06-05에서 연결.

## R06-04 내부 검증
Node 102개·Python 63개·타입/빌드 통과. 폴더/하위/라이브러리 수와 선택 교집합, tree/treehouse 접두 충돌 방지, 경로 순회·없는 루트 거부 확인.

## R06-05 내부 검증
Node 103개·Python 65개·타입/빌드, Rust 12개 통과. 검토 후 원본 변경 시 Job 생성 거부·재검토 후 queued 생성·같은 요청 UUID 재전송 시 중복/예약 추가 없음·시작 전 run 미생성 확인. 선택 최대 200개(16KiB 파이프), 범위 최대 1000개. 실제 모델 실행은 다음 R06-06에서 연결한다.

R06-05 추가: 유료 모델의 컨텍스트 상한 미확인 거부, 분석별 외부/유료 재승인 각각 누락 시 Job 0개, 명시 승인 후 예약을 네트워크 금지 fixture로 검증.

## R06-06 내부 및 실제 로컬 검증
Node 104개·Python 66개·타입/빌드, Rust 12개 통과. 제한된 실제 PNG 디코드·원자적 결과/활성 포인터/AI 태그 저장·사용자 태그 보존·출처 텍스트 렌더 검증.
사용자 승인으로 공식 Ollama v0.40.12 Windows CLI SHA256 검증 후 숨김 서버 설치, qwen3-vl:2b(2.1B Q4_K_M, vision 실측) 다운로드. `verify-local-analysis.py --model qwen3-vl:2b` 실제 실행: 41.03초에 completed, 실제 설명이 흰 배경의 빨간 사각형을 식별, 원본 SHA256 불변·DB 결과 저장. 외부/유료 호출·GUI 없음. 진단 보고는 .artifacts/m06-real-analysis.json. 서비스는 localhost에만 실행하며 실행 엔진은 임의 모델 설치/다운로드/유료 폴백을 하지 않는다.

## R06-07 내부 검증
Node 105개·Python 67개·타입/빌드, Rust 12개 통과. 3개 실제 PNG 전처리 큐에서 처리 전 0/3, 중간 API_RATE_LIMIT 후 최종 3/3(성공 2·실패 1) 실측, 호출 3회로 자동 재시도 없음 확인. 최근 Job 재선택·다이얼로그 밖 진행/상태 바 값 검증. 원문 오류는 반환하지 않고 처음 10개 고정 오류만 표시한다.

## R06-08 내부 및 실제 취소 검증
Node 107개·Python 69개·타입/빌드, Rust 12개 통과. 활성 취소 시 후속 호출 없음·canceled run/항목 보존, 고아 작업 자동 재개 없음·명시적 정리, 재실행의 새 검토/시작 분리 확인. 실제 qwen3-vl:2b PNG 작업 `--cancel-after 1` 검증: 2.0초에 canceled, 원본 해시 불변(.artifacts/m06-real-cancel.json). 취소는 진행 중 연결을 닫고 실제 상태가 저장될 때까지 요청 상태로 표시하며 예약 상한을 자동 환급하지 않는다.

## R06-09 내부 검증
Node 108개·Python 70개·타입/빌드, Rust 12개 통과. 결과/run 삭제·완료 run 수정·Job 스냅샷 변경을 SQLite가 거부, 최신 실패와 이전 활성 성공 결과를 별도 페이지로 조회/렌더. v1→v3 재색인/백업 및 실패한 v4 마이그레이션 롤백 회귀 통과. 실제 화면 조작 없음.

## R06-10 내부 검증
Node 109개·Python 71개·타입/빌드 통과. 이전 성공 후 재분석 대기 중 사용자 표시명/설명/태그를 수정하고 API_TIMEOUT 발생 시 사용자 수정과 기존 활성 AI 결과가 모두 유지됨을 실측. 사용자/AI 영역 구분과 실패 후 이전 성공 유지 문구를 DOM으로 검증.

## R06-11 내부 검증
Node 110개·Python 74개·타입/빌드 통과. PNG+WAV+FBX 범위에서 이미지 모델 호출은 1회·미지원 2개 오류 기록, 미지원/20MB 초과만 있는 범위는 Job 0개. 투명 픽셀의 숨은 RGB는 파생 JPEG에서 흰색으로 합성하고 원본을 보존, 권한 오류의 원문 경로 레드랙션 확인. 오디오/3D 실제 AI 추론·3D 렌더는 명시적 미지원이며 기술 메타데이터 표시만 제공한다.

## R06-12 / M06 최종 검증
- `npm run check`: Node 110개·Python 77개 통과, 타입 검사·Vite 빌드 성공. `cargo test --lib --locked -- --include-ignored`: 실제 패키지 포함 13개 통과. `cargo clippy --all-targets --locked -- -D warnings` 통과. 총 200개 내부 테스트.
- `npm run build:installer` 및 `scripts/verify-installer.ps1 -AnalysisModel qwen3-vl:2b` 통과. 전용 임시 설치본에서 Tauri의 무화면 CLI로 Core/DB/PID를 검증하고, 설치된 Sidecar에 Python 없는 PATH·비공개 JSON 파이프로 실제 이미지 분석 명령을 보냈다. 44.05초에 completed, 실제 설명은 흰 배경의 빨간 사각형을 식별했다.
- 원본 SHA256 불변·실제 응답 모델 기록·DB v3·Core 정상 종료·같은 DB로 Core 재시작 후 동일 결과/Job 1개 유지·stderr 없음·임시 설치 제거·원래 설치 보존 확인. 최종 Sidecar SHA256은 설치본 보고와 개발 번들이 일치한다. 보고 파일 `.artifacts/m06-installed-analysis.json`, 로그 `.artifacts/m06-installed-check.log`.
- 원본/기존 사용자 AppData는 검증에 사용하지 않았다. 실제 앱 창·브라우저·화면 조작은 미실행이며 UI는 내부 DOM/상태/이벤트로 검증했다. 실제 GUI·깨끗한 PC·대규모 라이브러리/모델 성능·외부 유료 추론/청구서는 미검증이다. 오디오/3D는 기술 메타데이터와 제한/오류만 제공하며 AI 성공으로 표시하지 않는다.
- 설치 파일 13616738 bytes, SHA256 `d2b4175992620873796ea8733404e402d855d9637a82ae45d01fe211fd8e6e11`. 기존 NSIS Korean `choowHowToInstall` 문자열 경고 1개 유지.
- 개발 검증용 Ollama CLI v0.40.12: `C:/Users/kdm/AppData/Local/AIAssetHubTools/ollama-v0.40.12/ollama.exe`, 모델 경로 `.artifacts/tools/ollama-models`. 사용자 설치/다운로드 승인으로 루프백 127.0.0.1:11434·클라우드 비활성 환경에서 실행했다. 앱이 런타임/모델을 자동 설치·다운로드하지 않는다.

## R07-01 내부 검증
`npm run check`: Node 110개·Python 78개·타입/빌드 통과. 현재 활성 AI 설명/태그 키워드·실패 후 성공 결과 검색·FTS 무결성 및 모델 호출 0건 확인.

## R07-02 내부 검증
Node 111개·Python 79개·타입/빌드, Rust 12개 통과. 메타데이터에서 차원 확인·재개방 설정 유지·차원별 버전 분리·비정상 벡터 거부·명시적 설정 UI와 상태 조회의 생성 호출 0건 확인.

## R07-03 내부 검증
Node 111개·Python 80개·타입/빌드, Rust 12개 통과. 생성 명령 전 모델 호출 0건, 선택된 성공 결과 1개 저장·버전/차원·원본 해시 무효화 시 준비 대상 제외 확인. 생성 상태는 실제 DB 저장 건수 기준이며 Core 재시작으로 자동 재개하지 않는다.

## R07-04 내부 검증
Node 112개·Python 81개·타입/빌드, Rust 12개 통과. 한국어 질의에서 질의 임베딩 1회·코사인 .8 계산·문서 벡터 추가 없음, 입력만으로 호출 0건·실행 후 실제 ID/관련도 반영 확인. 벡터는 수학 검증 fixture이며 실제 한국어 품질 검증은 모델 다운로드 승인 후 별도 수행 예정.

## R07-05 내부 검증
Node 113개·Python 82개·타입/빌드, Rust 12개 통과. 벡터 없는 혼합 검색의 모델 호출 0건·키워드만 결과 표시, 태그/경로 검증·타입 조건 서버 전달·혼합 출처 표시 확인.

## R07-06 / M07 최종 내부 검증
- `npm run check`: Node 114개·Python 84개·타입 검사·Vite 빌드 통과. 이후 두 후보의 실제 UUID 코사인 순위·태그 선필터 회귀 추가 후 `npm run test:core` Python 85개 통과. `cargo test --manifest-path src-tauri/Cargo.toml --lib --locked -- --include-ignored`: 13개, `cargo clippy --manifest-path src-tauri/Cargo.toml --all-targets --locked -- -D warnings` 통과. 최종 내부 테스트 총 212개.
- 버전 변경 후 준비 0개·신규 차원 재구축 후 준비 1개, 기존 공간 보존, 실패한 재구축 전후 벡터 bytes 동일, FTS integrity-check 통과. 질의 원문 DB 미포함·로컬 고정 HTTP 대상/검색 접두어·응답 모델 불일치/리다이렉트 거부·취소 후 요청 0건 확인. 벡터/메타데이터는 명시된 테스트 fixture이며 실제 한국어 모델 결과가 아니다.
- 전체 재구축 체크박스와 명시 버튼, 승인 전 명령 0건, 일반 선택 생성과 재구축 명령 분리를 jsdom으로 확인. 실제 화면·브라우저·앱 창은 열거나 조작하지 않았다.
- `npm run build:installer`와 `scripts/verify-installer.ps1` 통과. 새 Sidecar의 임베딩 상태 조회·미승인 재구축 거부를 Rust의 실제 비공개 파이프에서 확인했다. 전용 임시 설치본의 DB v3·실제 PID 종료·Sidecar 해시·조용한 제거/기존 설치 보존 통과. 설치본에서는 모델 추론을 실행하지 않았다.
- 설치 파일 13677238 bytes, SHA256 `d2ca203790948a801363ce44705dc55353ddb714575cb0bc163b17d87dfe36c9`. 기존 NSIS Korean `choowHowToInstall` 문자열 경고 1개 유지. 로그 `.artifacts/m07-check.log`, `m07-python-final.log`, `m07-rust.log`, `m07-clippy.log`, `m07-installer-build.log`, `m07-installed-check.log`.
- `scripts/verify-semantic-search.py --help` 통과. 실제 PNG fixture 3개의 로컬 이미지 분석→임베딩→한국어 top1·혼합 태그 검색→규격 변경/재구축/기존 공간 복원·원본 불변을 확인하도록 준비했으나 **실제 실행은 미실행**. 추가 다국어 모델 다운로드 승인 대기이며 R07-04의 실제 적합 결과와 마일스톤 H는 미완료다. 실제 모델 호출 예: `.artifacts/core-build-venv/Scripts/python.exe scripts/verify-semantic-search.py --embedding-model embeddinggemma:300m --report .artifacts/m07-real-semantic.json --sidecar src-tauri/binaries/core/ai-asset-hub-core/ai-asset-hub-core.exe`. 이는 승인 후 명시적으로 실행하며 자동 테스트에 포함하지 않는다.
- 대규모 라이브러리 검색 성능·실제 OS 화면 배치·외부/유료 임베딩은 미검증/미지원. 원본 파일과 기존 사용자 DB를 검증 대상으로 사용하지 않았다.

## 2026-10-29 R07-04 / M07 실제 로컬 검증 완료
- 사용자 ‘추가 다운로드·실제 검증 허용’ 승인 후 기존 Ollama에 `embeddinggemma:300m` 다운로드. 공식 표기 622MB, 로컬 실측 621875917 bytes·embedding capability·768차원. manifest digest `85462619ee721b466c5927d109d4cb765861907d5417b9109caebc4e614679f1`, pull의 SHA256 검증 성공. 설치 경로/공식 근거는 MODEL_MANAGEMENT에 기록했다. 외부/유료 추론 호출 없음.
- 초기 동봉 Core 실제 시험은 물결 이미지 1개에서 INVALID_MODEL_OUTPUT으로 실패했다(`.artifacts/m07-real-semantic.log`). 같은 테스트 이미지의 로컬 진단은 `done_reason:length`, eval_count=512, 빈 최종 content를 반환했다. 추론을 완성된 설명으로 저장하지 않았다. 로컬 출력 상한 1024·한 문장/최대 8태그의 v2 규격·명시적 MODEL_OUTPUT_LIMIT 오류 및 스냅샷 한도 기록 회귀를 추가했다. 외부 512토큰 예약/상한은 유지한다. 자동 재시도 없이 보완 후 명시적으로 다시 실행했다.
- 실행: `.artifacts/core-build-venv/Scripts/python.exe -B scripts/verify-semantic-search.py --embedding-model embeddinggemma:300m --report .artifacts/m07-real-semantic.json`. 테스트 소유 torch/tree/water PNG를 qwen3-vl:2b가 실제 분석하고 실제 결과 UUID를 임베딩했다. 실제 설명은 각각 ‘stylized fire icon…brown stick’, ‘green triangular tree…brown trunk’, ‘Blue background with white curved lines…’였다. 수동 설명/가짜 벡터/추측 ID를 삽입하지 않았다.

| 한국어 질의 | 실제 1위 테스트 파일 | 코사인 점수 |
|---|---|---|
| 중세 마을 횃불 | torch.png | 0.282786 |
| 숲에서 쓸 만한 나무 | tree.png | 0.366854 |
| 푸른 바다의 물결 | water.png | 0.260616 |

- 3/3 top1 통과, 사용자 태그 필터를 적용한 혼합 검색에서 실제 tree UUID·hybrid 출처 확인. EmbeddingGemma→plain 규격 교체 시 새 버전/준비 0개, 전체 재구축 후 준비 3개, 원래 규격 복원 시 기존 벡터 3개 확인. 원본 PNG 3개 SHA256 불변. 보고 `.artifacts/m07-real-semantic.json`, 로그 `.artifacts/m07-real-semantic-final.log`.
- 최종 동봉 PyInstaller Core를 Python 없는 PATH·비공개 JSON 파이프로 다시 실행했다. 앞선 개발 검증 DB를 같은 development 환경으로 열어 실제 PID·동일 profile·준비 3개·한국어 ‘숲에서 쓸 만한 나무’ top1 보존을 확인하고 EOF 정상 종료·stderr 0 bytes 확인. 보고 `.artifacts/m07-packaged-restart.json`, 로그 `.artifacts/m07-packaged-restart.log`. Sidecar SHA256 `29185b32e64c2985c67824c16b71442531ddd17fd6a2a0115e5b3e947ad58fcb`.
- 최종 `npm run check` Node 114개·Python 86개·타입 검사·Vite 빌드 통과, 스냅샷 검증 보완 후 `npm run test:core`도 Python 86개 통과. Rust `--include-ignored` 13개 및 Clippy `-D warnings` 통과. **총 213개 내부 테스트**. 로그 `.artifacts/m07-final-check.log`, `m07-final-python.log`, `m07-final-rust.log`, `m07-final-clippy.log`.
- 최종 `npm run build:installer` 및 `scripts/verify-installer.ps1` 통과. 임시 전용 설치본의 DB v3·실제 Core PID 종료·Sidecar 해시·조용한 제거/기존 설치 보존 확인. NSIS 설치본은 13675518 bytes, SHA256 `815259d92f3ca6c35005da5540341384398b630d7f4e0f63ad6c4908224e0246`. 기존 Korean choowHowToInstall 문자열 경고 1개 유지. 로그 `.artifacts/m07-final-installer-build.log`, `m07-final-installed-check.log`.
- R07-04/H 및 M07 전체 완료로 갱신한다. 위 결과는 단순 테스트 이미지 3개에 한정하며 다양한 실사용 에셋·대규모 라이브러리 품질/성능·깨끗한 PC·시각적 배치/OS 화면은 미검증이다. 실제 화면 조작·외부 유료 호출·사용자 원본 수정·원격 push는 하지 않았다. 앞선 승인 대기/미실행 기록은 당시의 검증 이력으로 보존한다.

## R08-01 내부 및 패키지 Host 검증
- `npm run check`: Node 114개·Python 88개·타입/Vite 빌드 통과. 실제 현재 사용자/SYSTEM 전용 Windows 보호 DACL의 세션 발견 파일·인증된 로컬 health 및 정상 종료 후 APP_NOT_RUNNING 확인. 모델 호출/Job 생성 없음.
- `npm run package:core` 및 `.artifacts/core-build-venv/Scripts/python.exe -B scripts/verify-mcp.py --core src-tauri/binaries/core/ai-asset-hub-core/ai-asset-hub-core.exe --report .artifacts/m08-host.json` 통과. 공식 SDK Client Host→별도 패키징 stdio Bridge→실행 Core 구성에서 초기화/서버 이름·버전/도구 목록 조회, 프로토콜 2026-07-28 협상 성공. Bridge는 Python 없는 PATH에서 실행했다. 현재 목록은 아직 조회 도구 연결 전의 빈 목록이다.
- SDK의 Windows pywin32 초기화에는 가상환경 site의 .pth 처리가 필요했다. 실제 인터프리터에 `site.addsitedir`를 적용해 SDK를 초기화하고 Windows venv redirector의 중간 PID 문제를 피한다. 기존 실제 자식 PID 일치 검증은 유지한다. 실제 화면·특정 AI 제품 개인 설정/모델 호출·유료 API·사용자 데이터 사용 없음.

## R08-02 내부 검증
`npm run test:core` Python 90개 통과. 실제 Core Broker의 목록·한국어 파일명 검색·종류/루트 필터·안정적 페이지·잘못된 ID/한도/경로 필터 거부 및 모델 호출/Job/벡터 생성 0건 확인. 보완 후 `test_mcp` 4개도 통과: 별도 stdio Bridge를 사용하는 공식 SDK Host에서 실제 등록 라이브러리/에셋 UUID를 구조화 결과로 반환했다. 이전 R08-01 Rust 13개도 패키지 포함 통과. 검색 순위/임베딩을 암묵적으로 생성하지 않는다.

## R08-03 내부 검증
`npm run test:core`: Python 92개 통과. 공식 SDK Host로 5개 도구를 실제 stdio 프로세스에서 호출, 실제 등록 ID·미분석 null·현재 파일 present 확인. 테스트 소유 불변 성공/실패 이력 fixture에서 성공 설명 유지/마지막 실패 구분·파일 삭제 후 missing·없는/해제된 ID 거부 확인. 썸네일 생성과 추론을 호출하면 실패하도록 막은 상태에서 상세/파일/상태 조회 통과. 실제 화면 조작 없음.

## R08-04 내부 검증
`test_mcp` 11개 통과. 실제 로컬 TCP에서 잘못된 MAC·이전 세션 재사용·쓰기 명령을 거부하고 가짜 서버의 서명 없는 성공 결과를 거부했다. 송신 요청에 세션 비밀값이 없음을 확인했다. 실제 Windows 발견 파일 DACL을 Everyone Full Access로 완화하면 클라이언트가 거부하며 원래 ACL 복구 후 정상 연결한다. 1.7초 미완성 요청·중복 JSON·64KiB 초과 요청·과대 응답 실패 후에도 Core 채널 생존 확인. 같은 SDK stdio 세션에서 Broker 종료 후 도구가 APP_NOT_RUNNING 오류로 응답하고 Bridge가 앱을 재기동하지 않음을 확인했다. 다른 실제 사용자 계정 로그인 시험은 하지 않았으며 같은 사용자 신뢰 경계를 SECURITY에 기록했다.

## R08-05 / M08 최종 검증
- `npm run check`: Node 116개·Python 101개, 타입 검사·Vite 빌드 통과. `cargo test --manifest-path src-tauri/Cargo.toml --lib --locked -- --include-ignored` 13개 및 `cargo clippy --manifest-path src-tauri/Cargo.toml --all-targets --locked -- -D warnings` 통과. **총 230개 내부 테스트**. 로그 `.artifacts/m08-check.log`, `m08-rust.log`, `m08-clippy.log`.
- 성공/거부 감사의 실제 요청 UUID·대상 UUID·결과·고정 오류 및 안정적인 페이지 확인. 질의·사적인 Host 문자열·경로·세션 비밀값이 DB 로그에 없음을 검사했다. DB 경로 변조 및 실제 `mklink /J` Windows junction을 통한 탈출은 파일/상대 경로를 숨기고 unavailable로 반환했다. junction은 테스트 소유 폴더에서만 생성/해제했고 외부 테스트 파일도 보존했다. DB v3의 기존 audit_events를 사용하므로 새 마이그레이션 없음.
- 연결 실행 정보·로그 페이지의 실제 상태/요청/대상 표시·HTML 텍스트 이스케이프·실패 메시지 레드랙션/재조회·cursor 전송·조회 명령만 호출함을 jsdom으로 검증했다. 실제 화면을 열거나 조작하지 않았다.
- `npm run build:installer` 통과. `.artifacts/core-build-venv/Scripts/python.exe -B scripts/verify-mcp.py --core src-tauri/binaries/core/ai-asset-hub-core/ai-asset-hub-core.exe --data-dir <M07 테스트 데이터 절대 경로> --environment development --query tree --require-analyzed --report .artifacts/m08-analyzed-host.json` 통과. M07의 실제 qwen3-vl:2b 결과를 새로운 패키지의 5개 도구로 조회해 실제 에셋/활성 결과 UUID·파일 존재·분석 성공 상태를 확인했다. 분석 Job 목록·벡터 준비 상태 불변·등록된 테스트 원본 전체 SHA256 불변 확인. 새 분석/임베딩 호출 없음.
- 공식 SDK Client reference Host는 별도 stdio Bridge를 Python 없는 PATH에서 실행했다. 자동 협상 2026-07-28 및 legacy 초기화 2025-11-25 모두 실제 도구 호출 성공. Core EOF 종료 후 도구 오류·동일 데이터로 명시적 재시작 후 실제 PID 교체/활성 결과 보존·감사 로그 성공/거부/비밀 미포함 확인. 보고 `.artifacts/m08-analyzed-host.json`, 로그 `m08-analyzed-host.log`.
- `scripts/verify-installer.ps1 -Mcp` 통과. 전용 임시 설치본의 Tauri 무화면 Core/DB/PID 검사 후 설치된 Sidecar/Bridge에서 같은 5개 도구·두 프로토콜·종료/재연결·감사를 실측했다. 이 생산 환경 테스트 DB의 신규 PNG는 미분석이므로 activeResultId=null이 맞으며 성공 결과를 만들지 않았다. 조용한 제거/기존 설치 등록 보존 통과. 보고 `.artifacts/m08-installed-host.json`, 로그 `m08-installed-check.log`. 개발/설치본 Sidecar SHA256 `142e2bab6dfcc3f6fa1ba46b27efbcd22727c554a057c487e9638f7521613b3f` 일치.
- 설치 파일 23593535 bytes, SHA256 `d745baeca3da5e17d137838066fd8847578038723cf7d3b50a00bbd03edb28a6`. 기존 NSIS Korean choowHowToInstall 문자열 경고 1개 유지.
- 마일스톤 I/M08 전체 완료. 특정 AI 제품의 개인 MCP 설정·대화/모델 실행, 실제 GUI·깨끗한 PC·다른 사용자 계정 로그인·대규모 성능은 미검증이다. reference Host와 실제 TCP/패키지/설치본으로 측정한 범위를 구분한다. Unity 도구는 M09 범위로 아직 노출하지 않으며 원격 push는 하지 않았다.


## D-029 통합 에셋 관리 확장 문서 검증
- 사용자 첨부 원문을 ASSET_MANAGEMENT_REQUIREMENTS.md에 바이트 동일하게 보존하고 ASSET_METADATA.md/PRD/관련 상세 설계와 로드맵에 연결했다. 원문 SHA256 `ae1de49da7d4ecd90912022fc8ae542d6bdd378b11c9317d7e5dd43e98f56044`.
- 내부 Python 문서 검사: A01~A14 코드 14개/중복 없음, 신규 R08A~I 작업 45개 전부 미완료/ID 유일, 기존 R00~R10 작업 75개 상태 보존, 변경 Markdown 15개 로컬 링크·민감정보 패턴 검사 통과. `git diff --check` 통과. 진단 `.artifacts/metadata-design-check.json`.
- 앱/DB/원본을 변경하지 않은 문서 작업이다. 앱 기능/DOM/모델/설치 테스트는 **미실행**이며 신규 기능 완료로 표시하지 않는다. 기존 M08 테스트 230개는 과거 검증 기록이고 이번 실행 결과가 아니다. 실제 화면 조작·분석/임베딩·외부 유료 호출·push 없음.

### 후속 구현 시 추가할 수용 시나리오 (현재 미실행)
1. A02 기사 모델/역할 캐릭터·A03 걷기 클립·A09 캐릭터 세트의 대표 유형과 복수 탐색 분류를 중복 Asset 없이 조회한다.
2. 1개 Package/다중 Asset/다중 File, 복수 계층 그룹·이동/삭제 후 원본 SHA256·UUID·불변 분석 결과가 유지된다.
3. 공유 제작 주체 변경의 조회 반영, 패키지 기본값/에셋별 예외·구매 당시 기록·미확인 라이선스/금액 null 구분을 검증한다.
4. 형식별 실제 파서/모델을 검증하고 관측/AI 제안/사용자 확정·미지원·부분 실패·취소를 구분한다. 등록/스캔/MCP 조회 시 AI·임베딩 호출 0건과 재분석 후 사용자 값/이전 성공 보존을 확인한다.
5. 7개 상세 탭·사전 관리·복합 필터/하위 분류/정렬/페이지·명시 저장/취소/충돌·키보드 대체는 DOM/상태/API로 검증한다.
6. 일괄 미리보기·JSON/CSV 참조/수식·해시 후보·민감 정보 제외·실패 롤백을 검증하고 자동 파일 병합/삭제를 거부한다.
7. 설치본 reference Host에서 확장 메타데이터/종속 파일을 실제 ID로 조회하고 경로·인증·감사를 검증한다. Unity 계획/실제 쓰기 검증은 별도 승인과 기존 M09 실제 Editor 결과를 요구한다.


## D-030 로드맵 순서 변경 검증
문서 검사 통과: M08H→M08I→M09→M10 제목 순서·작업 ID 유일성·기존 120개 체크 상태 보존·변경 Markdown 7개 로컬 링크 확인. `git diff --check` 통과. 앱 코드/DB 변경이 없는 문서 작업으로 기능/DOM/모델/설치 테스트는 **미실행**이다. 신규 기능을 완료로 표시하지 않으며 실제 화면 조작·분석·push 없음.


## R08A-01 내부 검증
`npm run test:core` Python 105개 통과(신규 분류 계약 4개). 실제 버전형 사전·14개 루트·3단계 경로·한영/NFKC 별칭·미지 값/파일명 거부·단일 대표/null·계층 중복 제거·잘못된 부모/중복 코드/별칭 충돌/비활성 경로를 검증했다. 응답 복사본 변경으로 원본 사전이 바뀌지 않음도 확인했다. 로그 `.artifacts/r08a-01-tests.log`. DB/UI/MCP 통합·설치본·실제 화면은 미검증이며 UI를 열거나 조작하지 않았다. 이번 범위는 순수 Core 계약이고 저장/사전 관리/독립 분류 축은 후속 범위다. Node/Rust/빌드 테스트는 미실행이다.


R08A-02: `npm run test:core` Python 107개 통과. 축 혼합/미지 값/버전 거부·한영 중복 제거·사용 중 비활성 승인/동일 축 대체·구버전 유지 검증. UI/DB 통합은 후속 범위.


R08A-03: `npm run test:core` Python 109개 통과. 새 AI 제안 뒤 사용자 값/명시 빈 값 보존·선택 제안 재적용·관측 우선·미승인/버전 충돌/미지 claim/NaN 거부·이력 복사 검증. DB 영속성은 R08A-05에서 연결한다.


R08A-04: `npm run test:core` Python 111개 통과. 실제 파일 UUID·내용 지문·내부 위치에 따른 구성 ID 안정성/변경 분리·미지 파일/잘못된 locator 거부를 검증했다. 계약은 파서/Unity 객체의 존재를 추측하지 않는다.


## R08A-05 / M08A 최종 검증
- `npm run check` Node 116개·Python 116개·타입 검사/Vite 빌드 통과. DB 버전 선택/다중 파일 회귀 보완 후 `npm run test:core` Python 117개 통과. 사용자 표시명/메모 보존 fixture 보완 후 `test_metadata_store` 6개도 통과. Rust `cargo test --manifest-path src-tauri/Cargo.toml --lib --locked -- --include-ignored` 13개 및 Clippy `--all-targets --locked -- -D warnings` 통과. 최종 고유 내부 테스트 **246개**.
- 기본 사전 JSON과 실제 103개 용어 행 일치·타입/축 FK 혼합/스냅샷 밖 코드/비활성/대표와 탐색 중복 거부·구버전 유지·사용 참조 수/승인/대체값 검증. 새 버전 명시 재지정과 사용자 이력도 저장/재개방 후 유지했다.
- v3 fixture의 실제 UUID·표시명/메모·사용자 태그·성공/실패 run·불변 결과/활성 포인터·검색 문서·벡터 bytes를 비교해 모두 보존했고 FTS integrity-check 통과. source 멤버십만 추가하고 원본 SHA256은 불변이다. 실제 004 SQL 뒤에 오류를 넣은 별도 migration fixture는 v3로 롤백·부분 테이블 없음·백업 보존을 확인했다. 기존 001~003은 수정하지 않았다.
- 파일/파서 근거는 실제 멤버 파일, AI 근거는 같은 에셋의 성공 결과 FK를 요구한다. 사용자 set/clear/adopt의 revision 충돌·미승인/미지 근거·재분석 제안 후 사용자 보정 유지·최초 관측 및 이전/새 결정 이력·삭제/수정 차단을 검증했다. 다중 파일 연결 뒤 원래 물리 소유자/에셋 수/원본 bytes도 유지했다. 분석 이력은 명시된 테스트 fixture이며 새 모델 호출은 없다.
- `npm run build:installer` 통과. 아직 공개 API에서 참조하지 않는 내부 계약 모듈이 최초 PyInstaller 수집에서 누락된 것을 확인해 metadata_store/asset_composition을 명시 포함하고 5개 내부 모듈의 PYZ 목록 검사를 패키징 단계에 추가했다. 최종 번들에서 모두 확인했고 동봉 004 SQL은 소스와 바이트 동일하다.
- 최종 `scripts/verify-installer.ps1 -Mcp` 통과: 임시 전용 설치본의 v4 DB/Core 실제 PID·Python 없는 PATH·5개 MCP 조회·최신 2026-07-28/legacy 2025-11-25 협상·종료 오류/명시 재시작 보존·조용한 제거/기존 설치 보존 확인. 기존 M07 실제 분석 테스트 DB도 새 Core에서 v4 업그레이드/조회하여 실제 활성 결과·Job/벡터 상태·테스트 원본 전체 해시 보존을 확인했다. 새로운 분석/임베딩 없음.
- 보고/로그: `.artifacts/r08a-final-check.log`, `r08a-check.log`, `r08a-store-tests.log`, `r08a-rust.log`, `r08a-clippy.log`, `r08a-installer-build.log`, `r08a-installed-check.log`, `r08a-analyzed-host.json`; 설치본 Host 보고는 `.artifacts/m08-installed-host.json`. 최종 설치/개발 Sidecar SHA256 `231f1235c85ea36ff3398f2042083947635bce3116bcfb66ff74df63ec4f3a7d` 일치.
- 설치 파일 23619224 bytes, SHA256 `7716dcfebeaa099f17149e283617712e1d7d7833ce0c5a11e7edb2c592d2bb5f`. 기존 NSIS Korean choowHowToInstall 문자열 경고 1개 유지.
- M08A 완료 범위는 분류/우선순위 계약과 DB 저장 기반이다. 새 분류 편집/사전 관리 UI·공개 쓰기 API·검색 투영·다중 형식 실제 분석은 M08B 이후 범위다. 실제 GUI·깨끗한 PC·대규모 성능은 미검증. 화면 조작·사용자 원본/기존 AppData 변경·원격 push 없음.


## R08B-01 내부 검증 (2026-10-29)
- npm run check: Node 120개·Python 120개, 타입 검사·Vite 빌드 통과. 신규 DOM 4개·Python 3개를 추가했다. 로그 .artifacts/r08b-01-check.log.
- DOM(mock Core): 원본 이름 HTML 이스케이프/표시명·별칭·설명 분리·입력만으로 호출 없음·고정 저장 인자·revision 갱신·충돌/일반 실패 초안 보존·명시 재조회·선택 변경 후 늦은 저장 결과 무시 확인.
- 실제 격리 SQLite/원본 fixture: NFKC/casefold 중복 제거·개수/개별/합계 한도·빈 배열·제어문자/서로게이트 거부·DB 재개방/재스캔·UUID/파일명/bytes 보존·구형 저장의 별칭 보존·stale revision 거부·후반 SQL 실패 시 결정/이력/주석 전체 롤백·고정 오류 원문 비노출 확인. 새 분석 Job/run/벡터/claim 0건이며 모델 실호출 없음.
- 구형 v1/v3 업그레이드 테스트는 현행 v4 서비스 대신 당시 스키마에 직접 fixture를 넣도록 수정했다. 업그레이드/백업/FTS/원본 보존 회귀는 유지한다. 최초 샌드박스 실행은 localhost 제한으로 MCP 검사가 실패했고 동일 격리 검사를 권한 확장 후 재실행해 통과했다.
- cargo test --manifest-path src-tauri/Cargo.toml --lib --locked: 12개 통과, 패키지 전용 1개 ignored. 실제 자식 파이프로 별칭 저장·충돌·원본 보존·Core 재시작 조회 일치 확인. cargo clippy --manifest-path src-tauri/Cargo.toml --all-targets --locked -- -D warnings 통과. 로그 r08b-01-rust.log / r08b-01-clippy.log.
- 총 252개 내부 테스트 통과. 실제 GUI·OS 화면·이번 변경의 설치본은 미검증이며 설치 패키지 검사는 미실행이다. 별칭 검색 색인은 M08E, 관리 필드/다중 파일/관계/전체 이력 UI는 R08B-02~05에 남긴다. 실제 화면 직접 조작·사용자 원본/AppData 변경·AI/임베딩 호출·push 없음.

## M08B 전체 내부 검증 (2026-10-29)
- `npm run check`: 최종 Node 127개, Python 132개 통과(총 259개); vue-tsc/tsc·Vite 빌드 통과. `.artifacts/r08b-final-check.log`.
- 관리 정보: 미평가/null과 정수 1~5, bool 혼동 거부, 상태·메모/버전 한도, 실제 윤년/날짜 순서, 실패 원자성, 재개방/재스캔 보존을 검증했다.
- 파일 구성: 실제 등록 ID·역할·소유 source 보호, 외부 파일 연결/누락·부분 가용, UUID 유지, 관측된 구성 요소의 실제 UUID/현재 해시/연결 파일 검증, 오래된 참조 거부를 검증했다. 신규 형식 파서 추출은 M08F 범위다.
- 관계: 실제 활성 대상, 중복/자기 연결, 원본·변형·파생 방향을 섞은 순환, 전체 결정/이력 롤백, 수신 관계 조회·2개씩 커서 페이지, 비활성 대상 보존/해제를 검증했다.
- 변경 이력: 이전/새 값·행위·시각·필드별 버전, 실제 이력 커서, append-only, 큰 값의 명시적 미리보기와 DB 원문 보존, 16KiB 응답 한도를 검증했다. 2개 DB 연결 충돌·태그 충돌은 기존 값/이력을 보존한다.
- DOM(mock Core): 명시 저장만 쓰기, 원문 HTML 이스케이프, 실패/충돌 초안 보존, 충돌 재저장 차단/명시 재조회, 에셋 전환 후 늦은 응답 무시, 이력 페이지 실패 시 기존 행 보존을 검증했다.
- 성공/실패 분석 이력 fixture와 새 AI 후보 후에도 사용자 기본 텍스트·관리·구성·관계 결정 및 활성 성공 결과가 보존됨을 확인했다. 실제 모델 호출 없이 수행했으며 등록/스캔/조회/메타데이터 명령의 신규 Job/벡터 생성은 없다.
- `cargo clippy --manifest-path src-tauri/Cargo.toml --all-targets --locked -- -D warnings`: 통과, `.artifacts/r08b-clippy.log`.
- `AI_ASSET_HUB_SIDECAR_DIR=.../src-tauri/binaries/core/ai-asset-hub-core`를 지정한 `cargo test --manifest-path src-tauri/Cargo.toml --lib --locked -- --include-ignored --test-threads=1`: 패키지 포함 13개 통과. `.artifacts/r08b-rust-serial.log`. 개발 Python 없는 패키지에서 관리/구성/관계/후보/이력 명령 및 재시작 보존을 확인했다. 앞선 빌드 동시·병렬 실행은 3개 Core 시작 CORE_TIMEOUT으로 실패했고 빌드 종료 후 직렬 재실행은 모두 통과했다. 제품의 기존 시작 제한 시간은 변경하지 않았다.
- 최종 합계 272개 내부 테스트 통과. `npm run build:installer` 및 `scripts/verify-installer.ps1 -Mcp` 통과. `.artifacts/r08b-installer-build.log`, `r08b-installed-check.log`, `m08-installed-host.json`. 격리 설치본의 v4/실제 PID·Python 없는 PATH·5개 MCP 조회·최신/레거시 프로토콜·종료/명시 재시작·원본/Job/벡터 보존·검증 설치본 제거와 기존 설치 보존을 확인했다. 설치/패키지 Sidecar SHA256 b69e5deebebed41de81e350923bbc1a24a1cc869910c43df9a9616e8abb20733 일치.
- 설치 파일 23,664,549 bytes. 기존 NSIS Korean choowHowToInstall 문자열 경고 유지. 실제 GUI·OS 화면/시각 배치·깨끗한 PC·대규모 성능은 미검증이다. 화면 직접 조작·사용자 원본 수정·외부 AI/임베딩 호출·원격 push는 수행하지 않았다.

## M08C 전체 내부 검증 (2026-10-29)
- 최종 `npm run check`: Node 137개·Python 152개(19.077초), vue-tsc/tsc·Vite 빌드 통과. `.artifacts/r08c-final-check.log`. 각 항목의 초기 검증은 r08c01/02/03/04/05-check.log, R08C-03 페이지/응답 한도 보완은 r08c03-core-final.log에 기록했다.
- 그룹 CRUD/복수 소속: 실제 ID·입력 한도·버전 충돌·후반 SQL 실패 원자성·삭제 시 원본/에셋/활성 결과 보존·DB 재개방을 검증했다. 기존 v4→현재 v6 업그레이드/백업, 새 스키마 합계 41개, 실패 마이그레이션 롤백·기존 메타데이터 보존 회귀도 통과했다.
- 그룹 계층: 실제 부모·자기/조상 순환·부모 삭제 시 하위 그룹 최상위 승격/버전/이력·실패 롤백을 검증했다. DOM의 DND 및 키보드 선택은 검토 후 명시 적용하며 취소·실패 시 기존 계층이 보존된다. 실제 화면 드래그는 수행하지 않았다.
- 그룹 검색: 키워드/태그/형식/폴더/분석 필터를 페이지 전에 적용, 202개 fixture에서 200개/2개 커서 경계·중복 없음, 의미 검색 랭킹 전 그룹 필터, 검색 실패 시 다른 그룹으로 대체하지 않음을 검증했다. 최대 32개 소속·긴 Unicode 이름도 응답 16KiB 미만이다.
- 일괄 지정: 최대 100개 대상의 전후 소속/버전·그룹 버전 검토는 쓰기를 만들지 않는다. 명시 승인·선택 변경 시 검토 폐기·중복 방지·stale plan 거부·후반 SQL 실패 시 전체 롤백과 각 에셋 변경 이력을 검증했다. 검토 행은 2개씩 페이지다.
- 패키지: 배포/구매 단위 구분, 에셋↔패키지 다대다, null 미확인/문자열 0 무료·금액/통화/실제 날짜, 최초 소속 당시 기록의 불변·해제/재연결/수정/삭제/재개방 보존을 검증했다. 하나의 패키지를 여러 에셋에 연결한 뒤 삭제해도 각각의 원본/에셋/버전이 보존된다.
- 상속/예외: 공유 기본값 실시간 참조, 동일 값의 근거 병합·다른 값은 conflict, 사용자 에셋 버전 우선·개별 값/null 미확인/상속 복귀, 두 DB 연결의 공유 버전 변경 후 stale 예외 거부, 저장 실패/재스캔/재개방/늦은 UI 응답/편집 중 공유 갱신의 초안 보존을 검증했다. 선언된 엔진/라이선스명은 호환성/권리 검증으로 표시하지 않는다.
- `cargo clippy --manifest-path src-tauri/Cargo.toml --all-targets --locked -- -D warnings` 통과. `.artifacts/r08c-clippy.log`.
- `AI_ASSET_HUB_SIDECAR_DIR=.../src-tauri/binaries/core/ai-asset-hub-core`에서 `cargo test --manifest-path src-tauri/Cargo.toml --lib --locked -- --include-ignored --test-threads=1`: 패키지 포함 13개 통과(7.62초). `.artifacts/r08c-rust.log`. Python 없는 PATH의 패키지에서 실제 그룹 생성/이동/소속/검색/일괄 적용·패키지 생성/공유값/상속/예외와 Core 재시작 보존을 확인했다. 최종 합계 302개 내부 테스트 통과.
- 최종 npm 검증의 첫 실행은 설치본 컴파일과 CPU 경합 중 테스트 실행기의 30초 제한으로 중단되어 전체 통과로 처리하지 않았다. 빌드 종료 후 동일 명령 재실행은 152개 모두 통과했다. 제품/테스트 제한 시간은 변경하지 않았다.
- `npm run build:installer` 및 `scripts/verify-installer.ps1 -Mcp` 통과. `.artifacts/r08c-installer-build.log`, `r08c-installed-check.log`, `m08-installed-host.json`. v6/실제 PID·Python 없는 PATH·5개 읽기 도구·최신 2026-07-28/레거시 2025-11-25·종료/명시 재시작·원본/Job/벡터 보존·격리 설치본 제거·기존 설치 보존 확인. Core Sidecar SHA256 c2e5d567bbe0caa1a4c7b143f2fdd14d4aa4538c5a33703882a45205dc0b4afe 일치. 새 005/006을 포함한 마이그레이션과 8개 메타데이터/컬렉션 모듈을 번들했다.
- 설치 파일 23,756,869 bytes. 기존 NSIS Korean choowHowToInstall 문자열 경고 유지. 실제 GUI/OS 시각 배치·깨끗한 PC·대규모 성능은 미검증. 실제 화면 조작·사용자 원본 이동/수정/삭제·AI/임베딩 호출·원격 push는 수행하지 않았다. 제작 주체/출처 객체·권리/새 구매 이력은 M08D, 전체 상세 탭/검색 확장은 M08E 범위다.

## ENV-01 이전 문서 검증 (2026-10-29)
- 문서 변경만 수행했다. 현재 소스의 .gitignore/package.json, Python 고정 requirements, Core 패키징/테스트 실행기, Tauri MSVC/데이터 경로, Windows Vault 키 범위를 읽고 실제 명령/경계와 대조했다. 기존 PC 실측 Node 24.12.0/npm 11.6.2/Python 3.13.15/rustc·Cargo 1.99.1을 비교 기준으로 기록했다. 설치 요구사항은 공식 Tauri/Microsoft/Rust/Node/Python/Ollama 자료와 대조하고 문서에 출처를 연결했다.
- System.Management.Automation.Language.Parser::ParseInput으로 NEW_PC_SETUP의 PowerShell fenced block 8개 검사: 구문 오류 0. Python pathlib/re 기반 로컬 Markdown 링크 검사(NEW_PC_SETUP/README/DEPLOYMENT): 36개 누락 0. git diff --check 통과. 명령 예제는 실제 설치/추론을 실행하지 않고 정적으로 검사했다.
- 앱 코드 변경이 없어 npm/Cargo 전체 기능 테스트·설치본 재빌드는 이번 문서 작업에서 미실행이다. 302개 통과는 이전 M08C 검증 이력임을 구분했다. 새 PC의 실제 설치/네트워크 다운로드/기존 DB 복원/모델 이동/실행·화면 동작은 미검증이며 새 PC의 실제 결과를 별도로 기록해야 한다. 현재 PC 프로그램/사용자 DB/원본/모델은 변경하지 않았다.

## ENV-02 새 PC 실제 환경 준비 (2026-10-29, 재부팅 대기 / 미완료)

대상 소스 `f5d7bf768ecfdd7fce4a74cd0e5a48909aea58ea` (`main`), 저장소 `D:\ai_workspace\aiAssetHub`. 시작 시 `git status --short`는 비어 있었다. 기존 PC의 302개 통과 기록은 이 PC의 결과로 사용하지 않았다.

### 환경 조사·실제 도구

- OS API: `Microsoft Windows 10.0.26300`, 네이티브 X64, Intel64 Family 6 Model 158 Stepping 10. 레지스트리 DisplayVersion `26H2`, build `26300.9711`; ProductName은 `Windows 10 Pro`로 보고되어 OS 마케팅 명칭은 확정하지 않았다. CIM OS/CPU 조회는 접근 제한으로 실패해 .NET OSArchitecture/OSDescription·환경 변수·레지스트리로 확인했다.
- 작업 전 C: 약 131.6 GB, D: 약 743.5 GB 여유. Git 2.53.0.windows.3은 Codex 제공 경로에서 사용 가능해 추가 설치하지 않았다. 기존 Git identity는 변경하지 않았다.
- 초기 PATH에는 Codex Node 24.22.1이 있었으나 npm 명령이 없었다. 저장소에 이미 있던 공식 Node 배포본 24.22.2/npm 11.19.1을 프로젝트 전용으로 사용한다. ZIP SHA256 `ca1bff5d8ead13c9f2ea404a176db46bd430704d5b5113734049fa365e7799e2`가 저장된 공식 SHASUMS256 항목과 일치했다. 다른 프로그램/전역 PATH는 변경하지 않았다.
- 초기 python은 WindowsApps 별칭뿐이며 일반 CPython·Rust·VS Build Tools·SDK는 조사 위치에서 확인되지 않았다. WebView2 Runtime `156.0.4314.50`은 HKLM EdgeUpdate 등록에서 확인돼 재설치하지 않았다. 실제 WebView2 화면 구동은 미검증이다.

| 도구 | 최종 실제 버전 | 경로 / 설치 결과 |
| --- | --- | --- |
| Git | 2.53.0.windows.3 | `C:\Users\KDM_SERVER\.cache\codex-runtimes\codex-primary-runtime\dependencies\native\git\cmd\git.exe` (기존) |
| Node / npm | 24.22.2 / 11.19.1 | `D:\ai_workspace\aiAssetHub\.artifacts\tools\node-v24.22.2-win-x64` (ZIP 배포본 사용) |
| CPython | 3.13.17, MSC v.1944, AMD64 | `C:\Program Files\Python313\python.exe` (신규 전체 사용자 설치, 종료 0) |
| SQLite | 3.50.4 | 위 기반 CPython의 sqlite3 모듈, 별도 서버 설치 없음 |
| rustup | 1.29.2 | `C:\Users\KDM_SERVER\.cargo\bin\rustup.exe` (신규) |
| rustc / Cargo | 1.99.1 / 1.99.1 | `C:\Users\KDM_SERVER\.cargo\bin`, stable-x86_64-pc-windows-msvc; rustfmt/clippy 설치 |
| VS Build Tools 2022 | 17.14.43 / 17.14.37824.6 | `C:\Program Files (x86)\Microsoft Visual Studio\2022\BuildTools` (신규) |
| MSVC v143 | 디렉터리 14.44.35207 | 위 BuildTools의 `VC\Tools\MSVC`; 실제 Rust 링크 검사는 미실행 |
| Windows SDK | 디렉터리 10.0.26100.0 | `C:\Program Files (x86)\Windows Kits\10`; 실제 컴파일 검사는 미실행 |
| WebView2 | 156.0.4314.50 | 기존 런타임 등록 확인, 추가 설치 없음 |

설치 근거: [Python 공식 배포](https://www.python.org/ftp/python/3.13.17/), [Node 배포 체크섬](https://nodejs.org/dist/v24.22.2/SHASUMS256.txt), [Rust 공식 설치](https://rust-lang.org/tools/install/), [Tauri Windows 요구사항](https://v2.tauri.app/start/prerequisites/). Python 설치기는 유효한 Python Software Foundation 서명, Build Tools 설치기는 유효한 Microsoft 서명을 확인했다. Rust는 `https://static.rust-lang.org/rustup/dist/x86_64-pc-windows-msvc/rustup-init.exe`와 해당 `.sha256`을 새로 받아 해시를 비교한 뒤 실행했다. 기존 미서명 Rust 다운로드는 실행하지 않았다.

### 설치·복원 명령 및 실측

| 명령 / 단계 | 결과 | 근거 / 제한 |
| --- | --- | --- |
| Python `/quiet InstallAllUsers=0 PrependPath=0 Include_launcher=0 Include_test=0` | **실패**, 종료 3 | 기존 잔존 로그 및 이번 retry에서 MSI 2203 / 0x80070003, 사용자 Package Cache의 core.msi 경로 실패 |
| Python `/quiet InstallAllUsers=1 PrependPath=0 Include_launcher=0 Include_test=0` | **통과**, 종료 0 | 공식 설치기로 전체 사용자 설치 재시도. 재부팅 요구 없음. 기존 프로그램 제거/보안 설정 변경 없음 |
| `vs_BuildTools.exe --quiet --wait --norestart --add Microsoft.VisualStudio.Workload.VCTools --includeRecommended` | 설치 성공, **종료 3010 / 재부팅 필요** | 관리자/시스템 영역 설치가 필요해 샌드박스 밖 실행을 사용. vswhere 최종 isComplete/isLaunchable=true. isRebootRequired=false 필드와 달리 설치기 종료 코드는 3010이므로 NEW_PC_SETUP §5에 따라 재부팅 우선 |
| `rustup-init-verified.exe -y --no-modify-path --default-toolchain none` | **통과**, 종료 0 | 전역 PATH 변경 안 함. 기존 Rust 설치 없음 |
| `rustup toolchain install stable-x86_64-pc-windows-msvc` / `rustup override set stable-x86_64-pc-windows-msvc` / `rustup component add rustfmt clippy --toolchain stable-x86_64-pc-windows-msvc` | **통과**, 모두 종료 0 | 저장소 override 적용. 최초 툴체인 설치 과정에서 rustup이 비어 있던 default도 stable로 설정했으며 기존 default를 교체한 것은 아님 |
| `npm.cmd ci` | **통과**, 종료 0 | 97개 설치, 98개 audit, 16초, 보고된 취약점 0. 잠금 파일 수정 없음 |
| `AI_ASSET_HUB_PYTHON=C:\Program Files\Python313\python.exe`, `npm.cmd run package:core` | **통과**, 종료 0 | 새 `.artifacts/core-build-venv` 생성, 고정 requirements 설치, PyInstaller 최종 빌드 로그 32.343초(패키지 다운로드/설치 시간 제외) |
| `pip show Pillow PyInstaller mcp` / venv cfg / 파일·해시 확인 | **통과** (설치 메타데이터 검사) | Pillow 13.0.0, PyInstaller 6.22.3, MCP 2.3.0. 기반 Python 64비트·base_prefix 일치 확인. 기능 테스트를 대체하지 않음 |

새 환경은 기존 venv 복사본을 사용하지 않았다. 기반 Python과 프로젝트 venv는 분리했다. 생성 파일:

- `.artifacts/core-build-venv/Scripts/python.exe`, cfg 기반 `C:\Program Files\Python313`.
- `src-tauri/binaries/core/ai-asset-hub-core/ai-asset-hub-core.exe` (8,602,474 bytes) 및 `_internal/`.
- `src-tauri/binaries/ai-asset-hub-core-x86_64-pc-windows-msvc.exe` 및 `.artifacts/core-build-manifest.json`.
- Sidecar SHA256: `403ddcf35b8f8554760bef1b4c9d2b38ed0835bb0ccd65c27a2f0d4cd8586d72` (파일 해시와 manifest 일치). 실행/파이프/DB 기능 검증은 아직 하지 않았다.

### 재부팅으로 보류된 검증

Build Tools의 3010 결과를 확인한 뒤 아래 검증은 시작하지 않았다. 기능 테스트 실행 수 **0개**이며 개발 환경 복원 전체를 완료로 표시하지 않는다. 자동 재부팅은 수행하지 않았다.

| 명령 | 상태 |
| --- | --- |
| `npm.cmd run check` (Node·Python 자동 테스트 + 타입 검사 + Vite 빌드) | **미실행** — 재부팅 후 |
| `cargo fmt --manifest-path src-tauri/Cargo.toml -- --check` | **미실행** |
| `cargo clippy --manifest-path src-tauri/Cargo.toml --all-targets --locked -- -D warnings` | **미실행** |
| `cargo test --manifest-path src-tauri/Cargo.toml --lib --locked -- --include-ignored --test-threads=1` | **미실행** — 패키지 ignored 테스트도 추후 포함 |
| `npm.cmd run build:installer` | **미실행** — 최종 NSIS 설치 파일/해시 없음 |
| `./scripts/verify-installer.ps1 -Mcp` | **미실행** — 격리 무화면 설치·DB v6·공식 MCP Host·제거/기존 설치 보존 아직 미검증 |
| Ollama 설치·모델 다운로드·실제 추론/임베딩 | **미실행** — 별도 요청 없음 |
| 사용자 DB·원본 에셋 복사/이전 | **미실행** — 별도 승인된 복사본 없음 |

### 재부팅 후 재개

새 PowerShell 세션에서 아래 준비 후 NEW_PC_SETUP §7 명령을 하나씩 실행하고, 각각 종료 코드가 0일 때만 다음 단계로 진행한다. 설치본 빌드와 테스트를 동시에 실행하지 않는다.

```powershell
Set-Location D:\ai_workspace\aiAssetHub
. ./.artifacts/Use-DevEnvironment.ps1
rustup show
& $env:AI_ASSET_HUB_PYTHON --version
node --version
npm.cmd --version
```

현재 PC 전용 `.artifacts/Use-DevEnvironment.ps1`은 기반 Python·Sidecar 폴더와 프로젝트 Node/Cargo PATH를 현재 세션에만 설정한다. `.artifacts/Run-NewPcStep.ps1 -Step check` → `fmt` → `clippy` → `rust-tests` → `installer` → `verify`를 각각 별도 프로세스로 실행하면 실제 명령별 로그와 종료 코드/초 단위 소요 시간이 `.artifacts/new-pc-steps.jsonl`에 기록되도록 준비했다. **이 실행 보조 스크립트 자체와 이후 단계는 아직 미실행**이다. 새 다운로드/실행이 네트워크·레지스트리 샌드박스에 막히면 승인된 범위에서 권한 확장 후 재실행해야 한다.

현재 로그: `.artifacts/new-pc-python-{retry,machine}*.log`, `new-pc-rustup-install.log`, `new-pc-rust-toolchain.log`, `new-pc-npm-ci.log`, `new-pc-package-core.log`. 환경 스냅샷 `new-pc-inventory.json`, VS 상태 `new-pc-vswhere.json`, 종료 코드 요약 `new-pc-provision-status.json`. Build Tools의 3010은 대기 프로세스 실측을 위 요약에 기록했다. 설치 도구/로그/venv/Sidecar는 Git 제외 상태다.

사용자 DB·원본 에셋·모델·기존 프로그램 제거/덮어쓰기·전역 보안 설정 변경·앱/브라우저 화면 실행·Computer Use·다음 기능 개발·원격 push는 수행하지 않았다. 실제 GUI/OS 시각 배치·깨끗한 PC 실행·성능·서명/업데이트는 미검증이다. 문서 변경만 커밋하며 ENV-02 체크는 미완료로 유지한다.

## ENV-02 재부팅 후 순차 검증 (2026-10-30)

아래는 앞 절의 재부팅 대기 이후 같은 PC에서 실제 실행한 결과다. 재부팅 시각은 CIM 실측 `2026-10-29 23:53:21.500 +09:00`, OS Caption은 **Microsoft Windows 11 Pro**, 버전 `10.0.26300`, 64비트로 확인했다. 이전 레지스트리 ProductName과 달리 CIM에서 제품명이 확인됐다. vswhere 재부팅 요구는 0이다. 저장소는 `a88e804`에서 작업 변경 없이 시작했다.

`./.artifacts/Use-DevEnvironment.ps1`을 현재 PowerShell에 로드해 이전 절의 Node 24.22.2/npm 11.19.1·기반 CPython 3.13.17·Rust MSVC 1.99.1을 사용했다. 저장소 override와 `AI_ASSET_HUB_SIDECAR_DIR`를 확인했다. 검증은 아래 순서로 직렬 실행했으며 테스트와 설치본 빌드는 겹치지 않았다. `.artifacts/Run-NewPcStep.ps1`은 각 실제 명령의 종료 코드와 실행 시간을 기록했다.

| 실제 실행 명령 | 결과 | 실측 시간 |
| --- | --- | --- |
| `npm.cmd run check` | **통과**, 종료 0 — Node 137/137, Python 152/152, vue-tsc/tsc, Vite 빌드 | 전체 52.657초; Node 20.968초, Python 17.575초, Vite 1.07초 |
| `cargo fmt --manifest-path src-tauri/Cargo.toml -- --check` | **통과**, 종료 0 | 2.795초 |
| `cargo clippy --manifest-path src-tauri/Cargo.toml --all-targets --locked -- -D warnings` | **통과**, 종료 0, 경고 없음 | 95.510초 (최초 의존성 다운로드/컴파일 포함) |
| `cargo test --manifest-path src-tauri/Cargo.toml --lib --locked -- --include-ignored --test-threads=1` | **통과**, 종료 0 — 13/13、ignored 0、실패 0 | 전체 79.142초, 테스트 4.63초 |

고유 내부 테스트는 **302개(Node 137 + Python 152 + Rust 13)** 통과했다. Rust는 실제 개발 Core 파이프·PID/EOF/재시작/DB 보존·비정상 종료/시간 초과 및 인자 레드랙션, Python/개발 PATH 없는 동봉 Core 테스트를 포함한다. 폴더 선택 테스트는 어댑터/내부 경로 정책을 검사하며 OS 선택 창을 열지 않았다. DOM 테스트는 jsdom을 사용했다. 잠금 파일이나 제품 코드를 바꾸지 않았으며 AI/유료 공급자 실호출은 없다.

| 후속 실제 실행 명령 | 결과 | 실측 시간 |
| --- | --- | --- |
| `npm.cmd run build:installer` | **통과**, 종료 0; 잠금 Cargo 의존성으로 x64 NSIS 생성, beforeBuildCommand의 타입/Vite·Core 패키징도 성공 | 191.297초, Release 컴파일 2분 23초 |
| `./scripts/verify-installer.ps1 -Mcp` 첫 실행 | **실패**, 종료 1; Core/DB v6 검증 후 레거시 Host `get_asset`의 `is_error` 단언 실패 | 35.936초 |
| 진단용 MCP 스크립트 복사본 (아래 설명) | **통과**, 종료 0; 같은 설치 Core의 최신/레거시 검증 | 전체 시간 별도 계측 안 함 |
| `./scripts/verify-installer.ps1 -Mcp` 원본 재실행 | **통과**, 종료 0; 새 격리 설치부터 Core/DB/MCP·제거까지 전체 성공 | 34.337초 |

**최초 실패·남은 불확실성:** `.artifacts/new-pc-verify-first-failure.log`에 최초 실패를 보존했다. 최신 MCP 조회·Core 종료 오류·명시 재시작·원본 보존 단언 뒤 레거시 `get_asset`이 `is_error`를 반환했지만, 당시 스크립트가 오류 본문을 출력하지 않아 구체적인 응답 코드는 확인하지 못했다. 첫 fixture DB의 감사 마지막 레거시 조회는 `succeeded`/errorCode null이다. 오류 단언에 응답 출력만 추가한 Git 제외 복사본 `.artifacts/new-pc-verify-mcp-debug.py`로 재실행하자 성공했고, 그 뒤 **수정하지 않은 원본 설치 검증도 새 경로에서 통과**했다. 일시적 실패의 원인은 미확정이며 수정 완료나 안정성 결함 해소로 표시하지 않는다. 제품 코드/SDK/타임아웃/인증/단언을 완화하지 않았다. 필요 시 후속 별도 작업으로 재현·진단해야 한다.

첫 실패 때문에 남은 **검증 전용** 설치본은 보고서 경로가 저장소 `.artifacts/m02-installed-<UUID>` 내부인지 확인한 뒤 그 경로의 `uninstall.exe /S`를 숨김 실행해 종료 0·전용 레지스트리 제거를 확인했다. 이후 원본 전체 검증은 새 `m02-installed-469638e1-cd4d-4414-b34a-3f9d0b77d4f5` 경로에서 수행했다. 재실행이 끝난 뒤 설치 exe·검증 등록·실행 Core PID 모두 없음을 확인했고, 테스트 데이터/보고서는 보존했다. 기존 사용자 프로그램을 제거하지 않았다.

설치 검증 최종 실측:

- 설치 버전 0.5.0, 설치 Sidecar/소스 SHA256 일치, 동봉 마이그레이션 확인. Python 없는 PATH와 잘못된 PYTHONHOME/PYTHONPATH에서도 `--verify-core` 분기가 창을 만들지 않고 Core PID 12820·SQLite 3.50.4·DB ready/WAL·스키마 v6를 반환했다. stderr 비어 있음, 종료 후 Core 프로세스 없음.
- 공식 Python MCP SDK Client로 읽기 도구 5종(`list_libraries`, `search_assets`, `get_asset`, `get_asset_files`, `get_analysis_status`)·실제 fixture ID·안전 경로·거부 감사와 질의 원문 레드랙션을 확인했다. 최신 `2026-07-28` 및 레거시 `2025-11-25` 협상, Core 종료 오류·명시 재시작 PID 변경·조회 결과/fixture 원본 해시 보존을 검증했다. `noAnalysisOrEmbeddingCreated=true`, `guiOpened=false`, `pythonOnPath=false`이다. 생성된 테스트 에셋은 미분석 상태(`activeResultId=null`)이며 실제 모델을 호출하지 않았다.
- 이번 PC에는 기존 AI Asset Hub HKCU 설치 등록이 없었고 검증 후에도 없다. 따라서 기존 설치가 존재하는 상태의 업그레이드/보존은 이번 결과로 보증하지 않는다. 격리 검증 설치의 정상 제거는 확인했다.
- 검증용 NSIS 재컴파일에서 기존 Korean `choowHowToInstall` 경고 6040이 발생했다(동일 문구 반복 출력 후 요약 1 warning). 설치/검증 종료 코드와 구분해 기록하며 현지화 경고는 남아 있다.

최종 설치 파일: `D:\ai_workspace\aiAssetHub\src-tauri\target\release\bundle\nsis\AI Asset Hub_0.5.0_x64-setup.exe`, **24,037,209 bytes**, SHA256 `0a8e32473b49caaf147520b8931147104415a049f2323e4dbcc0f1dccb1dc25a`.

Sidecar SHA256 `403ddcf35b8f8554760bef1b4c9d2b38ed0835bb0ccd65c27a2f0d4cd8586d72`는 빌드 manifest·소스·최종 설치 검증 보고서에서 일치한다. 설치본/Sidecar는 Git 제외 산출물이며 일반 사용자용 제품을 별도로 설치하거나 실행하지 않았다.

로그/근거: `.artifacts/new-pc-check.log`, `new-pc-fmt.log`, `new-pc-clippy.log`, `new-pc-rust-tests.log`, `new-pc-installer.log`, `new-pc-verify.log`, `new-pc-verify-first-failure.log`, `new-pc-mcp-debug.log`; 명령별 실측 `new-pc-steps.jsonl`; 설치 Core/Host 보고서 `new-pc-installed-result.json`, `new-pc-installed-host.json`; 해시 `new-pc-final-hashes.json`; 재부팅/OS `new-pc-post-reboot.json`; 설치 전 등록 `new-pc-install-registry-before.json`; 최종 정리 `new-pc-final-cleanup.json`. 원본 검증 스크립트가 생성한 `r02-05-installed-result.json`, `m08-installed-host.json`도 보존했다.

**완료 범위:** ENV-02의 도구/새 환경·Sidecar 복원, 순차 내부 테스트·타입/Rust 검사, Windows 설치본 빌드·격리 무화면 설치/제거 검증을 완료했다. 최초 실패는 위에 별도 기록했다. 변경 파일은 `docs/TEST_PLAN.md`, `docs/ROADMAP.md`, `docs/CHANGELOG.md`이며 기능/잠금 파일 변경은 없다. Ollama/모델 다운로드·실제 AI 추론·사용자 DB/원본 이전·실제 GUI/OS 시각 배치·개발 도구가 없는 깨끗한 PC·서명/업그레이드·대규모 성능은 **미실행/미검증**이다. 앱/브라우저 화면 조작·다음 기능 개발·원격 push는 수행하지 않았다.

## R08D-01 제작 주체 사전·Core 관리 API (2026-10-30)

- 신규 `007_creators.sql`(v7)과 `creators.py`를 추가했다. 개인/팀/회사·브랜드·홈페이지/판매자 프로필 URL·연락처·국가·설명을 저장하며 Core `creator.list/get/create/update/set_enabled` 5개 명령과 Rust 내부 허용 목록을 제공한다. 신규 의존성은 없다. UI/Tauri 화면 명령·MCP 쓰기·에셋/패키지 역할 연결은 이번 범위가 아니다.
- 명시 쓰기·revision 충돌 검사·원자 저장/감사·비활성/복원을 제공한다. 목록은 2개씩 UUID 커서의 공개 요약이다. HTTPS 호스트/포트/IDNA·제어문자/크기/타입을 검증하고 userinfo·쿼리/fragment를 거부한다. URL 접속·신원/국가/연락 가능성 확인은 하지 않는다. 연락처·URL·설명 원문은 목록/감사/MCP/FTS에 복제하지 않는다. 감사에는 ID·revision·변경 필드명만 기록한다.
- 변경 파일: `db/migrations/007_creators.sql`, `python-core/ai_asset_hub_core/{creators,application}.py`, `python-core/tests/test_creators.py` 및 기존 스키마 기대값 3개 테스트 파일, `src-tauri/src/core_process.rs`, `scripts/package-core.mjs`, `scripts/verify-installer.ps1`, API/메타데이터/DB/이전 안내·ROADMAP·CHANGELOG·본 문서. 기존 SQL 001~006/잠금 파일/프런트엔드 코드는 변경하지 않았다.

| 내부 자동화 명령 | 실측 결과 |
| --- | --- |
| `AI_ASSET_HUB_PYTHON=<기반 CPython 3.13.17>`, `PYTHONPATH=<저장소>/python-core`, `python -B -m unittest discover -s python-core/tests -p test_creators.py -v` | 종료 0, 신규 9개 통과, 1.033초 |
| `npm.cmd run check` | 종료 0, Node 137개·Python 161개(17.825초), vue-tsc/tsc·Vite(0.967초) 통과 |
| `cargo fmt --manifest-path src-tauri/Cargo.toml -- --check` | 종료 0, 통과 |
| `npm.cmd run package:core` | 종료 0, 새 creators 모듈 포함 PYZ 검사·v7 SQL 동봉 성공; PyInstaller 빌드 로그 35.729초 |
| `cargo clippy --manifest-path src-tauri/Cargo.toml --all-targets --locked -- -D warnings` | 종료 0, 경고 없음, 19.264초 |
| `cargo test --manifest-path src-tauri/Cargo.toml --lib --locked -- --include-ignored --test-threads=1` | 종료 0, 14개 통과/ignored 0, 전체 17.548초·테스트 5.34초 |

고유 내부 테스트 합계 **312개(Node 137 + Python 161 + Rust 14)**다. 모든 빌드와 테스트는 순차 실행했다. Rust 신규 테스트는 실제 개발 Core의 생성/조회/수정/충돌/비활성/재시작 보존을 확인했고, 패키지 전용 테스트에도 같은 검증을 넣어 Python/개발 PATH 없는 동봉 Core에서 API를 확인했다.

신규 Python 테스트는 다음 상태·실패 경로를 확인했다: 유형/한글/NFKC와 동명 UUID 분리·재개방 보존, 안전하지 않은 URL/잘못된 타입·길이/서로게이트 거부, 두 DB 연결의 낙관적 충돌·stale 쓰기 불변, 비활성/복원·동일 상태 no-op, 민감 원문의 목록/감사 미포함·MCP 감사 분리, 5개 항목의 2개씩 커서 페이지·Unicode 응답 한도, 감사 SQL 후반 실패 시 생성/수정/비활성 전체 롤백과 오류 원문 레드랙션. 별도 v6 fixture를 v7로 올려 **모든 기존 테이블 행**·활성 분석 결과·FTS/원본 bytes·v6 백업을 보존했고, 새 SQL 뒤 오류를 넣어 v6/에셋/스키마 롤백과 creators 부분 테이블 없음도 확인했다. 생성·수정이 AI Job/벡터·기존 에셋/분석/검색 기록을 바꾸지 않았으며 네트워크 진입점을 막은 사전 작업도 통과했다.

후속 패키지 검증도 순차 실행했다. `npm.cmd run build:installer` 종료 0(93.968초, Release 컴파일 48.85초), `./scripts/verify-installer.ps1 -Mcp` 종료 0(32.666초). 격리 설치본은 버전 0.5.0/DB v7 ready/WAL·실제 Core PID·개발 Python 없는 PATH·비어 있는 stderr·Core 종료를 통과했다. 공식 MCP SDK의 읽기 5종·실제 fixture ID·감사/경로 거부·최신 2026-07-28 및 레거시 2025-11-25·종료 오류/명시 재시작·원본/Job/벡터 보존과 검증 설치본 제거를 확인했다. 이번 실행은 재시도 없이 통과했고, ENV-02 최초 MCP 일시 실패의 원인이 해결됐다고 주장하지 않는다. 기존 Korean choowHowToInstall 경고 6040(요약 1 warning)은 유지한다.

최종 설치본 `src-tauri/target/release/bundle/nsis/AI Asset Hub_0.5.0_x64-setup.exe`: 24,040,442 bytes, SHA256 `2238999f7952d92b98a53795218b71939630d6eaf0056ba4674f92ae3d7b9dfe`. 소스/설치 Sidecar SHA256 `4ba3a46438f31ed74feb00aa00cf1f7a937e3f00dfce10f7e5b860e52000fc19` 일치. API 동작은 개발/동봉 Core의 Rust 검사로, 설치된 앱은 무화면 Core/DB/MCP 회귀로 구분해 검증했다.

로그/보고서: `.artifacts/r08d-01-creators.log`, `r08d-01-check.log`, `r08d-01-package-core.log`, `r08d-01-clippy.log`, `r08d-01-rust-tests.log`, `r08d-01-installer.log`, `r08d-01-verify.log`, `r08d-01-steps.jsonl`, `r08d-01-installed-result.json`, `r08d-01-installed-host.json`, `r08d-01-hashes.json`. 문서/코드 공백 검사는 `git diff --check`로 확인한다.

이번 작업은 R08D-01만 완료한다. 제작 주체와 에셋/패키지의 역할 연결(R08D-02), 출처/구매·라이선스(R08D-03~04), 전체 변경 원문 이력/삭제 영향/내보내기 보호 확장(R08D-05), 실제 관리 UI(M08E)는 미구현/미검증이다. 실제 GUI/OS 화면·깨끗한 PC·기존 설치 업그레이드·대규모 성능은 미검증이다. 연락처는 이 사전 DB에 일반 텍스트로 저장되며 비밀 저장소로 제공하지 않는다. 실제 사용자 DB·원본·모델·유료 API를 다루지 않았고 화면/브라우저 조작·AI/임베딩·다음 작업·원격 push는 수행하지 않았다.

## R08D-02 (2026-10-30)
Core 역할 연결 API와 v8 asset/package FK 링크·독립 revision·append-only provenance_history를 구현했다. Python 역할/공유 수정·해제/구매 당시 기록·원본 보존, 비활성/중복/미지 ID·stale revision 거부, 후반 SQL 실패 원자성, 최대 Unicode 16개 연결 응답 16KiB 미만·불변 이력을 검증했다. `npm run test:core` 최초 174개 통과는 imported TestCase 9개가 중복 발견된 결과이며 모듈 import로 고쳤다. 최종 명령/개수는 아래에 기록한다. 새 스키마 기대값은 테스트·설치 검증이 실제 마이그레이션 개수를 사용하도록 수정했다. 사용자 DB/원본·모델·GUI는 건드리지 않았다. Rust 기능/패키지/설치 통합 회귀는 M08D 최종 단계에서 실행한다.
R08D-02 최종: npm run test:core 종료 0, Python 165개/18.493초 통과. 로그 .artifacts/r08d-02-core-final.log; cargo fmt 종료 0. 변경은 역할 연결 모듈/008 SQL·Core/Rust 허용 목록·스키마 테스트/패키징 가드·계약/검증/로드맵 문서다.

## R08D-03 (2026-10-30)
v9 출처/상품/원본·상품·다운로드 URL과 구매 가격·통화·구매/다운로드일을 asset/package 소유 기록으로 구현했다. 새 source_records.py/009 SQL·Core/Rust 허용 목록·테스트/패키징 가드·문서를 변경했다. 개인 정보/서명 URL·구매 정보는 기본 응답/감사에서 제외하고 명시 승인한 private get만 허용한다. 실제 네트워크 요청·다운로드·AI 없음. 무료 0·미확인 null·정확한 소수 금액/윤년·잘못된 입력 거부·소유 범위/페이지·버전 충돌·불변 과거 구매 값·후반 실패 원자성과 비활성 후 보존을 테스트했다. Rust/설치 통합은 M08D 최종 검증에서 실행한다.
R08D-03 실측: npm run test:core 종료 0, Python 169개/17.325초 통과. 로그 .artifacts/r08d-03-core.log. GUI/실제 URL 접속/AI/사용자 데이터 이전은 미실행.

## R08D-04 (2026-10-30)
v10 라이선스·증빙 테이블/FK/소유 범위 트리거와 license_records.py/명령/테스트를 추가했다. 사용자 명시 조건·출처 표시·검토 상태·적용 범위·메모·출처 참조를 보관하며 허가 판정은 항상 unknown이다. 증빙은 승인한 실제 등록/연결 파일 ID만 수용하고 범위/경로/리파스/현재 존재를 검증한다. 조건/노트·증빙은 기본 조회에서 제외, private get만 승인 후 제공한다. Python은 미확인/사용자 검토와 허가의 분리·AI 가장 거부·다른 소유자 출처 참조/FK 거부, 패키지 멤버/증빙 범위·해제 후 unavailable 보존·원본/FK 보호, 경로 이탈/리파스·중복/버전 거부, SQL 실패 원자성·민감 원문 레드랙션·최대 Unicode 응답 한도를 검증했다. 실모델/GUI/다운로드는 미실행이며 최종 Rust/설치 회귀는 M08D 마지막에 수행한다.
R08D-04 실측: npm run test:core 종료 0, Python 174개/17.894초 통과. 로그 .artifacts/r08d-04-core.log. Source와 동일 Core 연결/트랜잭션을 재사용하며 임의 네트워크/법적 권리 판정은 수행하지 않는다.
