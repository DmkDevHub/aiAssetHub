# 스마트 그룹·관련 추천 계약

## R08I-01 — 저장 조건
`catalog.smart.list({after_id})`, `.get({group_id})`, `.save({group_id,name,description,definition,expected_revision})`, `.delete({group_id,expected_revision})`, `.evaluate({group_id,query,criteria,sort,after_id})`는 desktop main 창의 고정 metadata_request를 통과한다. MCP 도구/분석 권한을 추가하지 않는다.

정의는 `{schema:'smart-group.v1',query,criteria,include_groups}`다. criteria는 기존 CatalogQuery의 같은 축 OR/다른 축 AND·미확인/범위 조건을 재사용하고 include_groups는 다른 스마트 그룹 결과와 AND 교집합한다. 실제 등록/소속/제작/태그 UUID와 분류 코드를 저장/평가 시 검사한다. 사라진 참조는 실패하며 전체 결과로 완화하지 않는다. 자기/순환/없는 그룹·깊이8 초과·참조8개 초과를 거부한다. 32그룹·정의6000 UTF-8바이트·query256자/16단어·현재 인덱스10000에셋/평가50000쌍 상한이다.

기존 settings의 catalog.smart-groups.v1에 버전·실제 UUID·이름/설명/정의/개별 revision·전체 revision을 저장한다. 신규 DB 마이그레이션/실제 소속 행은 없다. 모든 저장은 Python Core WriteScope에서 충돌 검사와 collection_history를 원자 기록한다. 다른 그룹이 참조하는 조건은 삭제할 수 없다. 이력의 필터/설명은 로컬 DB/백업에 남으며 일반 진단에 복제하지 않는다. 평가만으로 DB/원본·검색 인덱스·Job/벡터를 쓰지 않는다.

평가 결과는 현재 활성 라이브러리의 공개 catalog_documents/저장 메타데이터에 따라 바뀐다. query/criteria 추가 조건도 AND 적용하고 정렬 후200개씩 반환한다. 커서는 조건/전역 revision/정렬·현재 DB 변경 stamp를 포함해 변경 시 METADATA_CONFLICT로 실패한다. OS 실파일/권한 상태는 스캔 당시 기록이며 평가가 파일을 읽거나 재스캔하지 않는다.

갤러리 필터의 ‘스마트 그룹’에서 현재 검색 조건을 초안으로 담아 이름/설명/다른 조건을 지정하고 명시 저장한다. 목록 불러오기/조건 편집·취소/삭제/탐색·해제를 제공한다. 갤러리의 현재 키워드/필터와 저장 조건은 교집합이며 선택 중 의미 질의 실행은 비활성화한다. 오류는 빈 결과/명시 오류로 표시하고 조건을 자동 해제하지 않는다. 단순 목록·평가는 스캔/분석/임베딩을 실행하지 않는다.

## R08I-02 — 추천과 확정 관계
`catalog.related({asset_id,mode,criteria,limit})`는 현재 활성 등록 에셋의 공개 인덱스/메타데이터와 준비된 벡터를 읽는 main-window 전용 명령이다. mode는 metadata/stored_vectors/hybrid, limit는1~20이고 criteria는 기존 복합 필터다. 10000개 후보 상한이며 자기 자신·스캔상 누락·해제 라이브러리·이미 양방향 중 어느 쪽으로든 저장된 관계가 있는 에셋을 후보에서 제외한다. 실제 파일의 실시간 존재를 확인하는 스캔이 아니다.

metadata는 사용자 태그·직접 그룹/활성 패키지·분류/독립 축·직접/패키지 제작 주체의 실제 ID/코드 토큰 Jaccard다. 공통 근거 종류와 개수를 제공하며 원문 연락/URL/구매/권리 조건/증빙은 읽기 결과에 포함하지 않는다. stored_vectors는 현재 선택 profile.version/차원·활성 분석 결과/원본 fingerprint/공개 메타데이터 지문이 맞는 저장 벡터만 기존 Embeddings.ready로 확인하고 코사인 양수 결과를 정렬한다. 네트워크 model inspect/fresh/embed·새 질의 벡터를 만들지 않는다. source 벡터가 없거나 오래됐으면 vectorStatus=source-vector-unavailable이고 해당 모드는 빈 결과다. hybrid는 metadata와 stored_vectors 순위를 reciprocal rank(60+rank)로 합산하며 벡터 미준비 시 메타데이터 근거만 제공한다. 점수는 확률·권리 허가·실제 호환 보증이 아니다.

응답은 related-assets.v1, 실제 assetId/items(id/name/score/metadataScore/semanticScore/reasons/confirmed=false), vectorStatus/profileVersion, inferenceCalled=false, relationshipCreated=false다. 어떤 근거도 없는 대상을 채워 넣지 않는다. 데이터 stamp가 읽는 동안 바뀌면 METADATA_CONFLICT로 재조회를 요구한다. stored profile의 실제 공급자가 바뀌었는지 새 네트워크 검사를 하지 않는다는 한계가 있으며 현재 저장 계약/지문 기준이다.

관계·이력 탭의 ‘관련 에셋 추천’에서 명시 조회하고 ‘관련 관계 초안에 추가’로 related 초안만 만든다. 기존 ‘관계 저장’에서 revision을 검사한 뒤 확정한다. 추천을 조회하거나 기준을 변경하는 것만으로 관계/이력/벡터를 쓰지 않는다. 기존 사용자 관계/방향·파생 순환·16개 상한·동시 편집/실패 보존 정책을 재사용한다. 새 의미 계산이 필요하면 기존 임베딩 설정/명시 실행 흐름을 사용하고 자동 생성/재분석/유료 폴백을 제공하지 않는다. 화면 전환 뒤 늦은 응답을 폐기하며, 미확정/준비 부족과 저장된 관계를 구분해 표시한다.

추천 응답은 기존16KiB 통신의 여유를 위해12000 UTF-8바이트로 제한하고 초과 시 CATALOG_LIMIT로 실패한다. UI의 추천 개수(기본10, 최대20)를 줄여 다시 조회할 수 있다. 표시명은160자까지의 공개 이름이며 순위/근거를 조용히 누락하는 방식으로 한도를 맞추지 않는다.
