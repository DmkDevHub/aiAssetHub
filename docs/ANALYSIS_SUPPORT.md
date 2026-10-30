# R08F-01 — 유형별 분석 지원 계약

`analysis_contract.py`의 `asset-analysis.v1`은 현재 구현된 경로만 선언한다. 파일 확장자로 대표 분류를 지정하지 않는다. A01~A14 지원 행렬의 이미지 설명은 A01(2D), A04(텍스처), A07(UI), A08(환경 이미지), A09(캐릭터 이미지)의 PNG/JPEG 표현에 한정한다. 3D/애니메이션/VFX/오디오/데이터/폰트/코드/씬/패키지의 고유 형식 분석과 모든 유형의 구조화 분류 제안은 미지원이다. 복합 에셋의 전체 의미·호환성을 이미지 설명으로 확정하지 않는다. 실제 실행 허용은 분류가 아니라 입력 PNG/JPEG와 검증된 image 모델을 기준으로 한다.

PNG/JPG/JPEG는 지원 후보이며 실제 디코드·권한·픽셀 검사는 실행 시 수행한다. 알려진 다른 확장자는 `unsupported`, 목록에 없는 확장자와 확장자 없음은 `unknown`이다. 미확인은 지원으로 승격하지 않는다. 기존 `unsupportedCount`는 미확인을 포함하고 `unknownFormatCount`는 그 부분집합이다. 다중 파일·클립 집계 분석은 미지원이며 현재 원본 단일 파일 경로를 보존한다.

입력 `bounded-image.v1`, 출력 `asset-description.v2`, 출력 JSON 스키마/프롬프트 SHA-256, DB에 저장된 유형/독립 축 사전의 버전·내용 SHA-256을 사전 검토 snapshot에 기록한다. 검증된 모델의 기존 profileVersion과 함께 작업/실행의 model_snapshot_json에 보존한다. 출력은 기존 description/tags이며 새 구조화 추론은 R08F-02 이후다. 새 DB 마이그레이션이나 의존성은 없다.

검토 입력 지문은 대상 ID·크기·mtime_ns·가용성 목록의 SHA-256이다. 검토 중 파일 전체를 읽었다는 뜻이 아니며 같은 크기/mtime으로 바꾼 내용을 탐지하는 보장은 없다. 승인 후 실행에서는 기존 안전 입력 경로로 읽은 원본 바이트 SHA-256을 analysis_runs.input_fingerprint에 저장한다. 입력은 20MB·16M 픽셀 한도, 파생 JPEG는 최대 변 512px다. 전송 대상은 파생 JPEG와 고정 프롬프트이며 원본 파일·분류 사전/메타데이터는 공급자 요청에 포함하지 않는다.

기존 검토의 비용 상한·외부/유료 여부·작업별 승인·예산 예약 정책을 유지한다. 계약/스키마/프롬프트/사전 변경은 planToken을 바꾸므로 시작 전 재검토가 필요하다. 대기 중 계약이 바뀌어도 모델 호출 전에 ANALYSIS_PLAN_CHANGED로 실패한다. 구버전 작업에 계약이 없을 때는 기존 동작을 유지한다. 조회/검토는 작업·임베딩·추론을 만들지 않는다. 실제 모델 추가·설치·다운로드는 수행하지 않는다.

## R08F-02 구현 갱신
출력은 asset-description.v3이다. 이미지 분류·역할·스타일·색상·소재는 선택적 미확정 제안이며 임의 필드/사전 밖 코드는 거부한다. 기본 공개 사전의 코드/영문 이름만 고정 프롬프트에 포함하고 사용자 메타데이터는 전송하지 않는다. 이미지 원본의 파서 관측은 features.technical, 모델 제안은 features.suggestions에 저장한다. 이전 R08F-01의 구조화 제안 미지원 기록은 당시 경계이며 이 절이 이미지 경로를 갱신한다.

## R08F-03 구현 갱신
기술 탭의 명시 수집은 PCM WAV를 20MB 이내로 읽고 길이/채널/샘플레이트/샘플 프레임을 관측한다. 잘린 PCM은 성공하지 않는다. 오디오 AI는 OpenRouter audio 검증 모델에 한정하고 로컬 Ollama 오디오 전송은 차단한다. 수동 입력 선택 audio→사전 검토→외부/유료 승인 후에만 원본 PCM WAV 전체(최대60초)와 고정 프롬프트를 전송한다. 비용은 contextLength 전체에 max(prompt,audio) 단가를 적용하고 completion 상한을 더해 보수적으로 예약한다. 처리할 수 없는 비영점 추가 과금 항목은 검토를 거부한다. 음원 분류/분위기/전사는 AI 제안이며 기술 측정으로 표시하지 않는다. 실제 외부 오디오 추론 검증은 없으며 테스트는 합성 WAV+모의 HTTPS 응답이다.
규격: [Python wave](https://docs.python.org/3/library/wave.html), [OpenRouter 공식 오디오 안내](https://openrouter.ai/blog/tutorials/transcription-on-openrouter/).
