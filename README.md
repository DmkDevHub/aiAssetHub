# AI Asset Hub v0.5

> 상태: **M00 개발 기반·최초 NSIS 설치본 검증 완료** · 작성 기준: 2026-10-28 · 언어: 한국어  
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
├─ python-core/            # 분석·검색·MCP 코어 (향후 구현)
├─ unity-package/          # Unity Editor 패키지 (향후 구현)
├─ db/                     # 스키마·마이그레이션 (향후 구현)
├─ scripts/                # 개발 실행 사전 검사
└─ tests/                  # 개발 명령 회귀 테스트
```

## 현재 상태와 다음 행동
- `M00`: Windows 앱·개발 실행, 라이브러리/화면 설정 이동, 다크/라이트 테마 전환과 첫 NSIS 개발 설치본 검증 완료. 에셋 관리·분석 기능은 이후 작업 범위다.
- `npm run dev`로 개발 앱을 실행하고 `npm run build:installer`로 설치본을 만든다. 설치본은 `src-tauri/target/release/bundle/nsis/`에 생성된다.
- 개발 환경과 실행 명령, 검증 상태는 [DEPLOYMENT.md](docs/DEPLOYMENT.md)를 참고한다.
- [ROADMAP.md](docs/ROADMAP.md)에서 최초 미완료 작업을 골라 **한 번에 한 작업만** 구현한다.
- 완료 시 화면 직접 조작 없이 내부 자동화 테스트로 검증하고 결과·미검증 범위와 문서/변경 이력을 갱신한다(D-019). 현재 공통 검사 명령은 `npm run check`다.
