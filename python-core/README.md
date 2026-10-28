# Python Core — R02-01

Python 3.11 이상과 표준 라이브러리만 사용한다. pip 설치·외부 의존성·가상 환경은 현재 필수가 아니다. 현재 구현은 한 번 실행한 뒤 종료하는 개발용 health 조회이며, 앱 Sidecar·Tauri IPC·MCP 서버가 아니다.

프로젝트 루트의 PowerShell에서 직접 조회:

```powershell
Push-Location python-core
python -B -m ai_asset_hub_core health.get
Pop-Location
```

- stdout에 JSON 응답 한 줄을 출력하고 종료한다. 성공은 종료 코드 0, 요청 오류는 2, 내부 오류는 1이다. `--help`만 일반 도움말을 출력한다.
- `--request-id <UUID>`를 지정하면 유효한 ID를 응답에 유지하며, 생략하면 새 UUID를 만든다. 이것은 요청 상관 ID이며 에셋·모델·작업 ID가 아니다.
- `data.core`는 실행 중인 해당 프로세스의 상태(`ready`)·제품 버전·PID·Python 버전·단조 시계 가동 시간(ms)을 반환한다. 응답은 그 순간의 실측이며 종료 뒤에도 앱에 연결되어 있다는 뜻이 아니다.
- `data.database.status`는 `not_configured`다. DB 연결·스키마·데이터 경로를 만들거나 성공한 것으로 표시하지 않는다.
- `health.get` 이외 명령, 매개변수, 알 수 없는 필드를 거부한다. 파일 스캔·AI·임베딩·DB 쓰기·네트워크 서버를 시작하지 않는다. 예외·인자·경로·환경 변수·비밀키 원문을 응답/로그에 출력하지 않는다.

내부 검증:

```powershell
npm run test:core
npm run check
```

검사 러너는 기본적으로 `python` 실행 파일을 사용한다. 다른 인터프리터가 필요하면 `AI_ASSET_HUB_PYTHON`에 실행 파일 경로를 지정한다. `-B`로 바이트코드 파일 생성을 막으며 셸 없이 자식 프로세스를 시작한다. Python 실행 실패·타임아웃·테스트 실패는 검사 실패로 반환한다.

Tauri의 Core 시작/종료·인증·통신과 UI 실측 연결 표시는 R02-02, SQLite는 R02-03, 설치본 Sidecar는 R02-05에서 연결한다.
