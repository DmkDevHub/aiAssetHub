# TAXONOMY — R08A-01 대표 유형 계약

## 구현 범위
Python Core `taxonomy.py`의 `asset-types.v1`: A01~A14 대분류 14개, 중분류 59개, 소분류 초기 예시 3개(인간 캐릭터 모델/걷기 모션/금속 충돌 효과음). 모든 세부 종류를 완성한 사전은 아니다. 각 항목은 안정 코드·부모·한영 이름·별칭·활성 상태를 가진다.

순수 메모리 계약/검증 기반이며 DB 초기 데이터·에셋 분류를 자동 생성하지 않는다. 앱/MCP의 분류 지정·조회, 사전 저장/교체·사용 중 항목의 비활성/대체는 후속 범위다.

## 입출력과 실패
- `contract()`: version/categories 복사본. code/parent/labels/aliases/active/depth를 반환하며 응답 수정이 사전에 영향을 주지 않는다.
- `resolve(value)`: 코드·한영 이름·등록 별칭을 NFKC/casefold/공백 정규화해 해석한다. 알 수 없는 값·파일명은 추측하지 않는다.
- `path(value)`: 활성 대→중→소 코드 배열. 부모 누락·코드와 부모 불일치·자기/순환 부모·4단계 이상을 거부한다.
- `assignment(primary=None,navigation=(),version=...)`: 대표 유형 하나 또는 null·탐색 최대 32개·정확한 사전 버전을 검증한다. 대표와 같은 계층의 상하위/동일 탐색을 제외하고 탐색끼리는 가장 구체적인 항목만 남겨 코드순으로 반환한다. 역할/스타일 등 독립 축은 이 함수에 혼합하지 않는다.
- 오류는 입력을 반사하지 않는 고정 TaxonomyError 코드다: INVALID_CATEGORY/INVALID_PARENT/AMBIGUOUS_CATEGORY/CATEGORY_UNAVAILABLE/INVALID_CLASSIFICATION/TAXONOMY_VERSION_MISMATCH.

## 적용 사례와 경계
대표 A02.01.01에 탐색 A02/A02.01을 지정하면 중복을 제거한다. 별개 분류 A09.01과 A03.02.01은 유지한다. 이는 분류 연결 정규화이며 논리 에셋을 복제하지 않는다. 사용자 확정 우선순위/엔진 호환/파일 종류 추론은 아직 포함하지 않는다.

사전 ID의 삭제/재사용 금지, 변경 시 버전 증가 및 과거 결과 보존을 실제 DB/관리 API에 적용하는 작업은 R08A-02~05에서 연결한다. 이 모듈은 원본 파일·DB·AI·임베딩을 호출하지 않는다.
