# Python Core — M02

런타임 코드는 Python 3.11 이상 표준 라이브러리만 사용한다. 개발용 health CLI와 Tauri 비공개 파이프 Sidecar·SQLite를 구현했다. Windows 설치본은 Python/SQLite를 동봉한다. PyInstaller는 빌드 전용이며 MCP 서버·파일 수집·AI 분석은 아직 구현 범위가 아니다.

프로젝트 루트의 PowerShell에서 직접 조회:

```powershell
Push-Location python-core
python -B -m ai_asset_hub_core health.get
Pop-Location
```

- stdout에 JSON 응답 한 줄을 출력하고 종료한다. 성공은 종료 코드 0, 요청 오류는 2, 내부 오류는 1이다. `--help`만 일반 도움말을 출력한다.
- `--request-id <UUID>`를 지정하면 유효한 ID를 응답에 유지하며, 생략하면 새 UUID를 만든다. 이것은 요청 상관 ID이며 에셋·모델·작업 ID가 아니다.
- `data.core`는 실행 중인 해당 프로세스의 상태(`ready`)·제품 버전·PID·Python 버전·단조 시계 가동 시간(ms)을 반환한다. 응답은 그 순간의 실측이며 종료 뒤에도 앱에 연결되어 있다는 뜻이 아니다.
- 데이터 경로 없이 실행한 일회성 조회의 `data.database.status`는 `not_configured`다. 데스크톱은 백엔드가 정한 `--data-dir`와 `--environment`로 실제 DB에 연결하며 상태·스키마·SQLite 버전·WAL을 실측한다.
- `--serve`는 상속된 stdin/stdout 파이프에서 16KiB 이하 JSON 줄을 처리한다. EOF로 종료하며 네트워크를 열지 않는다. 사용자가 임의로 Core를 띄워 앱과 같은 DB를 공유하는 방식은 지원하지 않는다.
- DB를 지정하면 환경 표식·단일 쓰기 잠금을 확인한 뒤 필요한 스키마만 트랜잭션으로 적용한다. 기존 업그레이드는 사전 백업하며 오류/손상/환경 혼용을 자동 복구하지 않는다.
- 허용 명령은 `health.get`, `library.register`, `library.unregister`, `library.list`다. 각 명령의 정해진 매개변수 이외 필드는 거부하며 파일 스캔·AI·임베딩·네트워크 서버를 시작하지 않는다. 예외·인자·경로·환경 변수·비밀키 원문을 오류/로그에 출력하지 않는다. 등록 경로 자체는 사용자가 확인하는 결과 데이터에만 포함한다.

R03-02의 등록은 경로를 검증한 뒤 실제 UUID와 참조만 저장하고 중복 ID를 재사용한다. 해제는 enabled 비활성화로 원본·이력을 유지한다. 목록은 활성 UUID 커서 페이지로 조회한다. 쓰기는 데스크톱의 명시적 등록/해제 동작으로 요청하며 스캔은 R03-03 이후 범위다.

내부 검증:

```powershell
npm run test:core
npm run check
```

검사 러너는 기본적으로 `python` 실행 파일을 사용한다. 다른 인터프리터가 필요하면 `AI_ASSET_HUB_PYTHON`에 실행 파일 경로를 지정한다. `-B`로 바이트코드 파일 생성을 막으며 셸 없이 자식 프로세스를 시작한다. Python 실행 실패·타임아웃·테스트 실패는 검사 실패로 반환한다.

앱은 5초 간격으로 읽기 전용 health를 확인한다. 연결 실패 시 자동 재시작하지 않고 사용자의 다시 연결을 기다린다. 재연결은 Core/DB만 준비하며 분석 작업을 생성하거나 재개하지 않는다. 빌드·설치 검증 방법은 [DEPLOYMENT](../docs/DEPLOYMENT.md)를 참고한다.
