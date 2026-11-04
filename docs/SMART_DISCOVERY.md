# 스마트 그룹·관련 추천 계약

## R08I-01 — 저장 조건
`catalog.smart.list({after_id})`, `.get({group_id})`, `.save({group_id,name,description,definition,expected_revision})`, `.delete({group_id,expected_revision})`, `.evaluate({group_id,query,criteria,sort,after_id})`는 desktop main 창의 고정 metadata_request를 통과한다. MCP 도구/분석 권한을 추가하지 않는다.

정의는 `{schema:'smart-group.v1',query,criteria,include_groups}`다. criteria는 기존 CatalogQuery의 같은 축 OR/다른 축 AND·미확인/범위 조건을 재사용하고 include_groups는 다른 스마트 그룹 결과와 AND 교집합한다. 실제 등록/소속/제작/태그 UUID와 분류 코드를 저장/평가 시 검사한다. 사라진 참조는 실패하며 전체 결과로 완화하지 않는다. 자기/순환/없는 그룹·깊이8 초과·참조8개 초과를 거부한다. 32그룹·정의6000 UTF-8바이트·query256자/16단어·현재 인덱스10000에셋/평가50000쌍 상한이다.

기존 settings의 catalog.smart-groups.v1에 버전·실제 UUID·이름/설명/정의/개별 revision·전체 revision을 저장한다. 신규 DB 마이그레이션/실제 소속 행은 없다. 모든 저장은 Python Core WriteScope에서 충돌 검사와 collection_history를 원자 기록한다. 다른 그룹이 참조하는 조건은 삭제할 수 없다. 이력의 필터/설명은 로컬 DB/백업에 남으며 일반 진단에 복제하지 않는다. 평가만으로 DB/원본·검색 인덱스·Job/벡터를 쓰지 않는다.

평가 결과는 현재 활성 라이브러리의 공개 catalog_documents/저장 메타데이터에 따라 바뀐다. query/criteria 추가 조건도 AND 적용하고 정렬 후200개씩 반환한다. 커서는 조건/전역 revision/정렬·현재 DB 변경 stamp를 포함해 변경 시 METADATA_CONFLICT로 실패한다. OS 실파일/권한 상태는 스캔 당시 기록이며 평가가 파일을 읽거나 재스캔하지 않는다.

갤러리 필터의 ‘스마트 그룹’에서 현재 검색 조건을 초안으로 담아 이름/설명/다른 조건을 지정하고 명시 저장한다. 목록 불러오기/조건 편집·취소/삭제/탐색·해제를 제공한다. 갤러리의 현재 키워드/필터와 저장 조건은 교집합이며 선택 중 의미 질의 실행은 비활성화한다. 오류는 빈 결과/명시 오류로 표시하고 조건을 자동 해제하지 않는다. 단순 목록·평가는 스캔/분석/임베딩을 실행하지 않는다.
