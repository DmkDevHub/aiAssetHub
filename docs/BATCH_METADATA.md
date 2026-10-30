# M08G — 일괄 편집·교환·동일 내용 후보 계약

## 사용자 흐름과 경계

갤러리 선택 → 일괄 항목/값 입력 → 실제 전후 값·충돌 검토(전체 페이지) → 승인 체크 → 원자 적용이다. 새 UI는 기존 직접 일괄 태그/그룹 진입점을 통합했다. 기존 API는 호환을 위해 보존하며 새 기능은 main 창의 고정 metadata_request 허용 목록만 사용한다. MCP의5개 읽기 도구/권한은 확장하지 않는다. 스캔·조회·검토는 AI/임베딩/해시 작업을 생성하지 않는다. 새 의존성과 DB 마이그레이션은 없다.

## 일괄 검토·적용

`bulk.preview({request,after_id,plan_token})`의 request는 실제 `asset_ids`(1~100개, 중복 없음), `changes`, 선택적 `expected` 버전 맵이다. 첫 페이지의 커서/토큰은 null, 이후는 응답의 값을 사용한다. 한 페이지는1대상으로 전후 값·필드 버전·충돌을 반환한다. 모든 페이지는 같은 토큰을 요구하고 대상/공유 참조/사전/인덱스 파일 상태/활성 및 최근 분석이 바뀌면 재검토가 필요하다. expected가 주어진 필드의 버전 불일치는 충돌로 표시한다. 미리보기는 SQLite 읽기 트랜잭션만 사용하며 DB 변경량0·원본 내용 읽기0이다.

`bulk.apply({request,plan_token,confirmed:true})`는 BEGIN IMMEDIATE 안에서 같은 계획을 재계산하고 충돌이 없을 때 전체를 적용한다. 기존 편집기의 검증·불변 전후 이력·출처 감사를 재사용하며 중첩 쓰기는 SAVEPOINT로 합성한다. 중간 실패는 값/참조/이력/감사 전부 롤백한다. 부분 적용은 제공하지 않는다. 이미 적용한 토큰의 재전송은 버전 충돌이므로 임의 중복 출처를 만들지 않는다. 통신 실패로 최종 결과를 받지 못한 경우에는 저장 여부를 단정하지 않고 최신 값으로 다시 검토한다.

| 필드 | 변경 계약 | 보존·검증 |
|---|---|---|
| groups | set 또는 add/remove 실제 그룹 ID | 소속 버전·그룹 버전, 최대32개 |
| classification | 대표/탐색/축/사전 버전의 명시 patch | 기존 미지정 필드 유지, 실제 활성 사전/코드 검증 |
| creators | set 또는 add/remove {creator_id,role} | creator/producer/distributor, 실제 활성 주체·소속 버전, 최대16개 |
| sources | append 공개 site/productName 또는 records로 기존 실제 ID의 공개 값 수정 | append8개/총16개, 실제 소유자·버전, 기존 URL/구매/라이선스 보존; 기존 출처 삭제 없음 |
| tags | set 또는 add/remove 사용자 태그 | NFKC/casefold·사전 활성 상태, 최대32개/총512자; AI 태그/불변 결과는 보존 |
| basic | title/description/aliases | 원본 이름/경로 무변경, 기존 사용자 편집 제한·revision |
| packages | set 또는 add/remove 실제 패키지 ID | 최대16개·실제 활성 패키지/소속 버전, 기존 구매 스냅샷 규칙 |
| relations | 실제 targetId/kind 목록 | 최대16개·활성 대상/자기/중복·전체 합성 그래프 순환 거부 |

일괄 UI는 첫5종을 제공하며 기본 정보/패키지/관계의 가져오기는 같은 내부 적용 계층을 사용한다. 관계 변경은 최종 전체 그래프를 검증하므로 파일의 여러 행이 함께 만드는 순환도 거부한다. FTS 갱신과 임베딩 stale은 기존 공개 투영/지문 정책을 따르고 자동 모델 호출은 없다.

## public-only JSON/CSV 교환

`exchange.export({asset_ids,fields,format})`는 위8종 중 선택한 필드와 실제 ID/버전을 `metadata-exchange.v1`로 직렬화한다. 형식은 json/csv, 최대20개 에셋·문서6000 UTF-8바이트다. 기존16KiB IPC 안에 문자열 이스케이프와 공통 응답을 넣고 내보낸 문서를 그대로 다시 가져올 수 있는 경계다. 초과 시 대상/필드를 줄이도록 명시 오류를 반환한다. 응답은 content/assetCount/privateFieldsExcluded=true이고 DB/원본은 수정하지 않는다.

JSON 문서 키는 schema_version,fields,assets이고 각 행은 asset_id,values,versions다. CSV는 고정 열 schema_version,asset_id,fields,values,versions이며 fields/values/versions는 JSON 셀이다. 실제 사용자 값은 '{'로 시작하는 JSON object 셀 안에 있으므로 '=','+','-','@'로 시작하는 값·공백·개행/따옴표도 Excel 수식 시작 셀로 해석되지 않는다. 임의의 일반 CSV/Excel 스키마 변환은 하지 않는다. 중첩 JSON 텍스트는 변조 없이 왕복한다.

개인정보 교환은 이 단계에서 제공하지 않는다. 제작 주체는 ID/역할, 출처는 실제 ID/site/productName만 포함하며 연락처·URL·구매·증빙·라이선스 메모·원본 경로·모델/API 키·원본 내용은 선택 필드에 없다. 기본 정보에 사용자가 직접 작성한 공개 설명/별칭은 사용자 값 그대로 포함한다. 출처 버전은 ID/revision/enabled의 지문이며 비공개 값의 해시를 문서 버전으로 내보내지 않는다.

`exchange.preview({content,format,use_current_versions,after_id,plan_token})`는 문서 버전/키/크기·JSON 중복 키/유한 값·CSV 헤더/행·실제 ID/참조/출처 소유자·필드 값/버전·순환을 검증한다. 파일 버전이 다르면 기본적으로 충돌이다. 사용자가 현재 값 기준 재검토를 선택한 경우에만 입력 버전은 검증하되 현재 상태로 새 전후 계획을 만든다. 새 계획도 모든 페이지 확인과 승인 체크가 필요하다. `exchange.apply({...content,format,use_current_versions,plan_token,confirmed:true})`가 전체를 원자 적용한다. 사전 검토 중 바뀐 상태나 실패는 전체 저장을 막는다. 공개 출처 필드 수정으로 기존 비공개 URL/구매를 지우지 않는다. 없는 에셋/그룹/제작 주체를 생성하거나 폴더 등록·URL 접속·AI를 실행하지 않는다.

UI는 텍스트 입력/선택 파일 읽기와 내보내기 문서/저장 링크를 제공한다. 실제 OS 파일 선택·저장 창과 시각 배치는 내부 DOM 검증으로 확인하지 않으며 미검증으로 남긴다.

## 명시 해시·중복 후보

`duplicates.start({asset_ids,confirmed:true})`만 해시 작업을 만든다. 선택 에셋의 활성 등록 범위에 속한 고유 실제 구성 파일을 최대100개, 파일당1GiB까지1MiB 단위로 읽는다. 원본은 읽기 전용이며 SHA-256만 asset_files 캐시에 저장한다. 별도 Core 소유 SQLite 연결의 작업 스레드로 수행하고 진행은 실제 파일 처리 수다. 결과/벡터를 생성하거나 파일을 복제/수정/이동/삭제하지 않는다.

원본 인덱스 크기/mtime, 등록 루트·리파스·열린 Windows 핸들 최종 경로, 읽기 전후 크기/mtime/device/inode, 현재 경로의 파일 정체성을 검사한다. 파일 변경·권한·누락·크기 한도·취소는 고정 코드로 실패/취소하며 성공 SHA로 저장하지 않는다. 취소는 다음 청크/파일에서 멈추고 이미 완료한 해시는 보존한다. 해시 캐시 갱신은 기존 분석의 입력 stale 판단에 반영될 수 있지만 분석 이력/성공 결과/사용자 결정은 수정하지 않는다.

`duplicates.list({})`는 최근20개 실제 작업, `duplicates.status({job_id,after_id})`는 실제 카운트와 파일4개 페이지, `duplicates.cancel({job_id})`는 활성 취소 또는 중단 작업의 명시 정리를 제공한다. 재시작 후 queued/running은 needsRecovery로 표시하고 자동 재개하지 않는다. 작업/상태는 Core settings에 기록하며 진단 감사에는 ID/개수만 남긴다.

`duplicates.candidates({job_id,after_hash,after_file_id})`는 해당 작업에서 실제 성공한 SHA-256·크기가 같은2개 이상의 고유 파일만 후보로 반환한다. 조회는 파일 내용을 다시 읽거나 해시 작업을 시작하지 않는다. 현재 stat/파일 정체성/캐시가 달라지거나 누락/비활성/리파스이면 staleCount로 제외한다. 한 응답은 후보 그룹1개·파일4개이고 그룹 내 파일 페이지를 먼저 모두 조회한 뒤 다음 해시 그룹으로 이동한다. 논리 소속은 실제 ID 최대16개와 총수를 표시한다. 동일 내용이 같은 논리 에셋·구매/라이선스 권리를 의미하지 않으므로 두 동일성은 not-determined이며 자동 병합/삭제 API는 없다.

캐시 비교는 현재 stat/파일 정체성 확인이며 파일시스템 원자 스냅샷이 아니다. 동일 inode에서 내용을 바꾸고 크기/mtime을 의도적으로 원복하는 변경까지 조회만으로 감지하지는 못한다. 새 내용의 확정은 사용자가 명시적으로 다시 해시 계산한다. 대량 성능·실제 OS 화면은 미검증이다.
