# AI Asset Hub v0.5

> 상태: **M00~M08·M08A 완료 / 확장 관리 UI 후속** · 작성 기준: 2026-10-29 · 언어: 한국어
> 이 문서는 새로운 v0.5 설계의 출발점이다. 별도의 과거 설계 문서를 상속하거나 참조하지 않는다.

## 프로젝트 한 줄 정의

**로컬 게임 에셋을 분석·관리하고, 분석된 정보를 MCP를 통해 Unity 및 기타 개발 도구에 연결하여 자연어 명령으로 실제 개발 작업을 수행하는 Windows 앱**.

### 목표 1 — 에셋 분석·관리
- 사용자가 로컬 폴더를 등록해 썸네일 갤러리에서 에셋을 탐색하고 검색한다.
- **폴더 등록·스캔 시 AI 분석을 자동 실행하지 않는다.** `AI 분석` 버튼을 눌렀을 때만 실행한다.
- 전체·미분석·분석 완료 재분석·실패 재시도·선택한 에셋 분석을 제공한다.
- 로컬 모델과 사용자가 활성화한 외부 무료/유료 모델로 콘텐츠를 분석하고 이력을 보존한다.

### 목표 2 — MCP를 통한 실제 개발
- Codex 등 MCP 클라이언트가 에셋을 검색하고 분석 결과를 읽는다.
- Unity에 실제로 에셋을 임포트하고 장면(Scene)에 배치한 뒤 결과를 확인한다.
- 이후 다른 게임 엔진 또는 개발 툴용 커넥터를 추가할 수 있어야 한다.

## 기술 기준
| 계층 | 기술/정책 |
|---|---|
| 데스크톱 | Tauri 2, Windows x64 우선 |
| 화면 | Vue 3, TypeScript, Vite, 어두운 테마 |
| 엔진 | Python Core Engine, 배포 시 Sidecar 실행 파일 |
| 저장소 | 로컬 SQLite, AppData 운영 데이터 |
| 검색 | 메타데이터 필터·키워드(FTS5)·선택적 임베딩 검색 |
| AI 모델 | Native SDK + Provider Adapter + Model Registry |
| 자동화 | MCP 서버 + Unity Editor 연동 패키지 |
| 배포 | Windows NSIS `.exe` 설치본, 모델은 별도 선택 구성 |

## 문서 탐색
| 문서 | 설명 |
|---|---|
| [AGENTS.md](AGENTS.md) | 개발 작업 원칙과 완료 조건 |
| [ASSET_MANAGEMENT_REQUIREMENTS.md](docs/ASSET_MANAGEMENT_REQUIREMENTS.md) | 사용자 제공 확장 요구사항 원문 |
| [ASSET_METADATA.md](docs/ASSET_METADATA.md) | 통합 분류·메타데이터·그룹·제작/권리·형식별 분석 설계 |
| [PRD.md](docs/PRD.md) | 사용자 기능, 범위, 수용 기준 |
| [UI_DESIGN.md](docs/UI_DESIGN.md) | 첨부 이미지 기반 3단 화면·행동 |
| [ARCHITECTURE.md](docs/ARCHITECTURE.md) | 프로세스·모듈·로컬 통신 |
| [ASSET_LIBRARY.md](docs/ASSET_LIBRARY.md) | 폴더·에셋 등록과 식별·갱신 |
| [DATABASE.md](docs/DATABASE.md) | SQLite 스키마 초안과 데이터 이력 |
| [AI_ANALYSIS.md](docs/AI_ANALYSIS.md) | 수동 분석 범위·상태·잡 처리 |
| [MODEL_MANAGEMENT.md](docs/MODEL_MANAGEMENT.md) | 로컬·외부 모델 및 비용 정책 |
| [SEARCH.md](docs/SEARCH.md) | 검색·임베딩·결과 랭킹 |
| [API_CONTRACTS.md](docs/API_CONTRACTS.md) | 앱·엔진 내부 계약 초안 |
| [MCP.md](docs/MCP.md) | MCP 도구와 실행/응답 계약 |
| [UNITY_INTEGRATION.md](docs/UNITY_INTEGRATION.md) | Unity Editor 임포트/배치 |
| [SECURITY.md](docs/SECURITY.md) | 로컬 파일·외부 API·실행 권한 |
| [DEPLOYMENT.md](docs/DEPLOYMENT.md) | 개발 실행·Sidecar·Windows 설치 |
| [TEST_PLAN.md](docs/TEST_PLAN.md) | 테스트·UI 수용 기준 |
| [ROADMAP.md](docs/ROADMAP.md) | 작업 1개씩 완료하는 체크리스트 |
| [DECISIONS.md](docs/DECISIONS.md) | 확정 결정과 검토 필요 사항 |
| [CHANGELOG.md](docs/CHANGELOG.md) | 개발·검증 이력 |
| [GLOSSARY.md](docs/GLOSSARY.md) | 기술 용어·약어 |
| [REFERENCE_LINKS.md](docs/REFERENCE_LINKS.md) | 공식 기술 문서 링크 |

**화면 기준 이미지:** [`assets/ui_reference.jpg`](assets/ui_reference.jpg) — 제공된 Blueberry 레퍼런스의 레이아웃·탐색 흐름 참고. 원본 서비스의 로고·콘텐츠·상표를 그대로 복제하지 않는다.

## 리포지토리 폴더 구조
```text
AI-Asset-Hub/
├─ AGENTS.md
├─ README.md
├─ docs/
├─ assets/                 # 디자인 참고 리소스만
├─ src/                    # Vue 화면·테마·라우터
├─ src-tauri/              # Tauri 셸·NSIS 설치 설정
├─ python-core/            # Python Core 진입점·health 조회
├─ unity-package/          # Unity Editor 패키지 (향후 구현)
├─ db/                     # 스키마·마이그레이션 (향후 구현)
├─ scripts/                # 개발 실행 사전 검사
└─ tests/                  # 개발 명령·내부 컴포넌트 테스트
```

## 현재 상태와 다음 행동

2026-10-29 현재 M00~M08 구현·검증은 ROADMAP/TEST_PLAN 기록을 따른다. 새 확장 요구는 D-029/M08A~I에 미완료로 추가했으며 다음 구현 후보는 R08B-02이다. D-030에 따라 M08H→M08I→M09→M10 순서로 진행한다. 아래 개별 단계 설명은 개발 당시 이력으로 보존한다.

- `M00`: Windows 앱·개발 실행, 라이브러리/화면 설정 이동, 다크/라이트 테마 전환과 첫 NSIS 개발 설치본 검증 완료. 에셋 관리·분석 기능은 이후 작업 범위다.
- `R01-01`: 상단 검색어 입력·초기화, 실제 화면 경로 표시와 설정 이동 구현. 검색어는 화면 이동 중 유지하며 실제 에셋 필터링은 후속 M04 범위다.
- `R01-02`: 왼쪽 라이브러리 트리·폴더 선택 UI와 패널 너비 조절 구현. 현재 앱의 등록 폴더는 빈 상태이며 실폴더 연결은 M03 이후 범위다. 내부 자동화에서만 fixture 트리를 사용한다.
- `R01-03`: 중앙 갤러리의 그리드/목록 전환·개수·빈 상태 구현. 현재 앱은 0개 에셋이며 데이터가 있는 레이아웃은 내부 fixture로 검증했다. 실제 파일·썸네일 연결은 M03 범위다.
- `M01` 전 항목 완료: 오른쪽 선택 상세/탭/접기, 너비별 반응형 배치·F6/방향키 이동, 실제 테마/보기 명령 상태·오류 알림까지 구현. 내부 자동화 54개·타입·빌드 통과. 실제 화면 배치와 Core·파일·AI·Unity 연결은 미검증/후속 범위다.
- `R02-01`: Python Core의 실측 `health.get` 개발 CLI 구현. 데이터 경로 없이 직접 조회하면 DB 미연결로 반환한다. 데스크톱의 실제 연결은 아래 M02에 포함한다. 실행·검사 방법은 [Core 안내](python-core/README.md)를 참고한다. 공통 검사는 개발용 Python 3.11 이상이 필요하다.
- `M02`: 데스크톱 비공개 Core 통신·실측 연결 상태, SQLite 스키마/백업/개발·운영 분리, Python 동봉 NSIS, 종료 감지/명시적 재연결 구현. 현재 범위는 엔진·DB 기반이며 실파일 수집·AI·MCP·Unity는 후속 범위다. 기존 `AIAssetHubDev` 설치는 보존하며 최신 설치본은 아래 빌드 결과를 사용한다.
- `R03-01`: Windows 로컬 폴더 선택·취소·선택 경로의 세션 표시 구현. 선택은 등록/스캔을 수행하지 않으며 DB 저장은 R03-02에서 연결한다. 내부 자동화만 검증했고 실제 선택 창·이 변경을 포함한 설치본은 미검증이다.
- `R03-02`: 선택 폴더의 실제 DB 등록/비활성 해제·등록 트리·새 세션 복원 구현. 중복 ID 재사용·중첩 거부·원본/이력 보존을 검증했다. 파일 스캔·AI 작업은 시작하지 않으며 수집은 R03-03 범위다.
- `M03`: 명시적 파일 스캔·인덱스 폴더 필터·PNG/JPEG 캐시·실측 상세 정보·오류 대체·재스캔·정렬/다중 선택 구현. 새 개발 환경은 `npm run package:core`로 고정 Pillow 런타임을 먼저 준비한다. 실제 화면을 직접 조작하지 않으며 원본/AI 작업은 변경하지 않는다.
- `npm run dev`로 개발 앱을 실행하고 `npm run build:installer`로 설치본을 만든다. 설치본은 `src-tauri/target/release/bundle/nsis/`에 생성된다.
- 개발 환경과 실행 명령, 검증 상태는 [DEPLOYMENT.md](docs/DEPLOYMENT.md)를 참고한다.
- [ROADMAP.md](docs/ROADMAP.md)에서 최초 미완료 작업을 골라 **한 번에 한 작업만** 구현한다.
- 완료 시 화면 직접 조작 없이 내부 자동화 테스트로 검증하고 결과·미검증 범위와 문서/변경 이력을 갱신한다(D-019). 현재 공통 검사 명령은 `npm run check`다.


M08A의 버전형 분류·메타데이터 저장 기반과 SQLite v4 마이그레이션은 구현·검증 완료했다. 분류/확장 메타데이터의 사용자 편집 UI는 후속 범위다. [저장 계약](docs/METADATA_SCHEMA.md)을 참고한다.
