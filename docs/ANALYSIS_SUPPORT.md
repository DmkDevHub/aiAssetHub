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

## R08F-04 구현 갱신
OBJ는 정점/면 인덱스·삼각화 수·UV 수·사용 재질명·mtllib 참조를 파싱한다. glTF2/GLB2는 메시/재질/skin-joint 구조를 검증하고 내장 base64/GLB 버퍼의 float32 POSITION·삼각형 인덱스만 디코드한다. 외부 URI는 읽지 않고 참조로만 보고한다. sparse accessor·다른 primitive 모드의 프리뷰·FBX/BLEND는 미지원이다. glTF 단위는 규격의 meter이며 OBJ 단위/본 정보는 미확인이다. 버퍼에서 읽은 수치와 declared 수치를 구분하고 경계는 노드 변환을 적용하지 않은 mesh-local 좌표다.
입력20MB·정점10만·면10만 한도, 미리보기는 XY 직교 투영의 앞 1만 면 와이어프레임(512px)이다. 표면 렌더·텍스처·노드 변환/포즈를 표현하지 않는다. 3D 수동 입력 선택은 image 모델에 파생 JPEG와 고정 주의 프롬프트만 전송한다. 와이어프레임에서 소재/색상을 추정한 AI 응답은 거부하고 이전 성공을 보존한다. 명시 기술 수집은 실제 파일/지문에 근거한 안정 구성 요소 ID를 저장한다. 전체 glTF 유효성/엔진 임포트 성공을 보증하는 파서는 아니다.
규격: [Khronos glTF2](https://registry.khronos.org/glTF/specs/2.0/glTF-2.0.html).

## R08F-05 구현 갱신
출력 스키마는 asset-description.v4로 증가했다. GIF/APNG는 최대64프레임·전체32M 디코드 픽셀을 읽고 실제 프레임 수/시간/loop 설정을 관측한다. APNG 기본 이미지는 애니메이션 프레임에서 제외한다. 동일한 양수 duration일 때만 FPS를 산정하며 시간 부재는 null이다. 2D 수동 분석은 앞8프레임을 시간순 좌→우/위→아래로 배치한 콘택트 시트를 사용한다. AI action/loopRecommended는 미확정 제안이다.
glTF 클립은 실제 내장 float32 시간 accessor로 지속 시간을 산정하고 루트 노드의 LINEAR/STEP translation 트랙을 디코드한 경우에만 첫/끝 로컬 변위(월드/엔진 루트모션 아님)를 보고한다. 미해결 외부 버퍼·sparse·CUBICSPLINE 루트 이동과 3D 포즈 렌더는 미지원이며 glTF에 정의되지 않는 FPS/루프/엔진 호환은 추측하지 않는다. 기술 수집 시 관측된 프레임/클립 구성 요소만 저장한다.
규격: [Pillow 이미지 시퀀스](https://pillow.readthedocs.io/en/stable/reference/Image.html), [Khronos glTF2 애니메이션](https://registry.khronos.org/glTF/specs/2.0/glTF-2.0.html).

## R08F-06 구현 갱신
현재 계약은 asset-analysis.v2 / bounded-multiformat.v1 / asset-description.v4이다. 텍스트 기술 수집은 UTF-8 32KB 이내 JSON(중복 키 거부)/CSV/코드/Unity·VFX 선언을 읽는다. Python은 AST 선언만 파싱하며 실행/import하지 않는다. 기타 코드는 선언 이름 탐색이며 완전한 언어 의미 파서가 아니다. Unity/VFX YAML은 선언 태그·GUID 참조만 읽고 종속 파일을 열지 않는다.
ZIP은 EOCD 개수128 이하와 디렉터리만 읽고 파일명/선언 크기/위험 경로/암호화를 보고한다. 파일 내용 검증·압축 해제·설치·임포트는 하지 않는다. TTF/OTF는 SFNT 테이블 범위/head 단위/maxp 선언 glyph 수만 읽고 폰트를 렌더하거나 라이선스를 추정하지 않는다. MP4/MOV는 ftyp/mvhd 시간과 트랙 개수 헤더만 읽고 영상 프레임/코덱/동작 의미는 미지원이다. 일반 Unity 압축 패키지/WOFF/WOFF2/지원 밖 코덱은 성공하지 않는다.
수동 text 분석은 최대4KB UTF-8 전체 내용을 검증된 text 모델에 전송한다. 외부라면 원문 전체 전송을 명시하고 작업별 승인을 요구한다. 영상/폰트/ZIP 바이너리는 이 경로로 보내지 않는다. 원문은 비신뢰 데이터로 고정 프롬프트에 감싸고 반환값은 기존 엄격한 출력 검증을 거친다. 실제 외부 키가 텍스트에 포함되면 요청을 차단한다. 모든 기술 헤더 관측은 파일 내용의 완전한 유효성/실행·엔진 호환 증거가 아니다.

## R08F-07 구현 갱신
새 성공 결과의 구조화 제안은 실제 analysis_result ID를 참조하는 불변 AI claim에도 저장한다. 분석은 사용자 classification 결정을 변경하지 않는다. analysis.review는 실제 결과 ID/해당 에셋을 검증하고 현재 분류와 제안 적용 후 값을 반환한다. 비어 있는 제안은 기존 값을 보존하며 대표 분류·역할·스타일만 변경한다. analysis.review.apply는 검토 토큰/revision/명시 승인을 요구한다. 다른 사용자 변경이 있으면 METADATA_CONFLICT로 다시 검토해야 하며 기존 분류 저장 계층의 불변 전후 이력을 사용한다. 그 밖의 AI 색상/소재/동작/전사는 미확정 제안으로 남는다.
기존 전체/미분석/완료/실패/선택 모드·취소·실패 후 과거 성공 보존을 유지하고 혼합 결과는 partialSuccess를 별도 표시한다. 분석 중인 변경도 사용자 결정 우선순위를 바꾸지 않는다. 합성 기술 결과/AI fixtures를 실제 모델 응답으로 표시하지 않는다.
임베딩 입력은 기존 AI 설명/태그와 catalog_search_projection의 공개 메타데이터다. 연락처/원본 경로/출처 URL/구매/증빙/메모는 공개 projection에 포함하지 않는다. 공개 분류·태그·이름/그룹 등 변경 시 문서 지문이 달라져 기존 벡터가 stale로 제외되며 보존된다. 자동 임베딩/삭제/공급자 호출은 없고 명시 생성/재구축만 허용한다. 기존 정책으로 만든 벡터도 새 입력 지문과 맞지 않으면 재확인 상태가 된다.
