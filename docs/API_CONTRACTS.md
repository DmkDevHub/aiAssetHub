# API_CONTRACTS — 내부 유스케이스 계약 초안

> 이 표는 아직 배포된 엔드포인트가 아닌 **구현 대상 인터페이스 계약**이다. UI/Tauri/Sidecar 통신은 설치본의 보안과 호환성에 맞춰 실제 전송 형태를 확정한다.

## Core 명령 (논리 API)
| 명령 | 주요 입력 | 출력/부작용 |
|---|---|---|
| `health.get` | 없음 | Core/DB/버전 실측 상태 |
| `library.register` | `path`, `display_name?` | library ID; 스캔 시작. **AI 호출 없음** |
| `library.scan` | `library_id`, `recursive` | 스캔 작업 ID; 기본 메타데이터만 |
| `library.list` | 없음 | 등록 폴더 |
| `asset.list` | `scope`, `filters`, `sort`, `page` | 실제 에셋 목록 |
| `asset.get` | `asset_id` | 파일/사용자/분석 상세 |
| `asset.update_metadata` | `asset_id`, `tags`, `description?` | 보정 저장; 원본 파일 불변 |
| `analysis.preview` | `scope`, `mode`, `model_id` | 대상 ID/수, 전송 내용, 예상 비용 |
| `analysis.start` | `preview_token?`, `scope`, `mode`, `model_id`, `approval` | 작업 ID; **명시적 실행 요청 필수** |
| `analysis.cancel` | `job_id` | 취소 요청 수락 상태 |
| `analysis.jobs` | `job_id?` | 실측 진행률·에러 |
| `model.list` | 없음 | 사용 가능한 모델과 능력 |
| `model.test` | `model_id` | 연결 테스트 결과(유료 호출 여부 고지) |
| `search.assets` | `query`, `mode`, `filters`, `limit` | 결과/출처; 암묵적 분석 금지 |
| `unity.preview_operation` | `asset_ids`, `target`, `action`, `options` | 계획/경로 충돌/확인 필요 여부 |
| `unity.execute_operation` | `plan_id`, `approved` | 작업 ID; 승인 정책 검증 |
| `unity.get_operation` | `operation_id` | 에디터 실측 결과 |

## 공통 응답
```json
{
  "request_id": "request-uuid",
  "ok": true,
  "data": {},
  "error": null,
  "timestamp": "ISO-8601"
}
```
에러 시 `ok=false`, `error={"code":"...","message":"...","retryable":false}`를 사용한다. 요청 ID는 중복 실행 방지·로그 연결에 사용.

## 계약 기본 규칙
- 입력 ID, 허용 폴더 경로, 파일 확장자/타입, 모델 지원 기능, 단일 요청 크기를 검증.
- 폴더 등록·검색은 분석을 트리거하지 않음; `analysis.start`만 명시적으로 분석 생성.
- UI 진행 상태는 직접 상태 조회/이벤트로 전파; 예상값·더미 성공 데이터를 표시하지 않음.
- MCP 서버는 위 유스케이스를 호출하되 Core DB와 도메인 규칙을 우회하지 않음.
- 취소/타임아웃/부분 성공을 응답 스키마에 정직하게 반영.

## M01 UI 작업 이벤트 수신 계약 (R01-06)

`src/stores/operations.ts`의 `receiveOperation(event)`는 UI 메모리 표시 전용이며 명령·재시도·분석을 실행하지 않는다. Core 통신 방식/DB 스키마는 변경하지 않는다.

| 필드 | 규칙 |
|---|---|
| `id` | 실제 명령/작업의 상관 ID, 비어 있지 않은 200자 이내 문자열. UI/로그에는 표시하지 않음 |
| `kind` | `appearance.change`, `gallery.view`, `library.scan`, `analysis.run`, `unity.apply` |
| `state` | `running`, `succeeded`, `failed`, `cancelled` |
| `progress?` | 실측 `processed`/`total` 안전한 정수, `0 ≤ processed ≤ total`. 같은 작업의 총수 변경·역행 거부. 성공 이벤트는 전체 완료 건수를 명시 |
| `errorCode?` | `PERMISSION_DENIED`, `CORE_UNAVAILABLE`, 그 외는 고정 `COMMAND_FAILED`로 정규화. 원문 메시지/경로/비밀정보를 전달하지 않음 |

- 수신 성공은 `true`, 잘못된 입력·종료 상태에 대한 후속 갱신·용량 부족은 `false`다. 어댑터는 실패 반환을 처리해야 한다. 실행 중/미확인 오류를 덮어쓰지 않으며 최대 20개 상태를 보존한다.
- 0/0건 완료는 허용하며 추정 백분율을 생성하지 않는다. 제공하지 않은 진행 수는 생성하지 않는다. 종료 이벤트는 실제 실행 결과에 근거해 전달하며 성공·실패를 추측하지 않는다.
- `executeUiCommand`는 현재 로컬 테마/보기 변경 콜백만 감싸고 `ui-command-*` 상관 ID를 만든다. 이것은 에셋/모델/백엔드 작업 ID가 아니다. 콜백 종료 후 성공, 예외 시 안전한 실패 문구를 기록하며 자동 재시도하지 않는다. 이력 공간이 없으면 콜백을 실행하지 않고 `false`를 반환한다.
- 실제 Core/스캔/분석/Unity 송수신 연결은 후속 마일스톤이며 현재 테스트 fixture가 그 성공을 보증하지 않는다.
