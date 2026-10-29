-- Additive catalog foundation. Existing asset IDs, paths, tags and AI history remain intact.
CREATE TABLE classification_dictionaries (
 version TEXT PRIMARY KEY, kind TEXT NOT NULL CHECK(kind IN ('type','facet')), payload_json TEXT NOT NULL CHECK(json_valid(payload_json)), UNIQUE(version,kind)
);
CREATE TABLE classification_terms (
 version TEXT NOT NULL, kind TEXT NOT NULL, axis TEXT NOT NULL CHECK(axis IN ('type','role','style','genre','view','dimension','engine')),
 code TEXT NOT NULL, parent_code TEXT, ko TEXT NOT NULL, en TEXT NOT NULL, aliases_json TEXT NOT NULL CHECK(json_valid(aliases_json)),
 active INTEGER NOT NULL CHECK(active IN (0,1)), replacement_code TEXT,
 PRIMARY KEY(version,axis,code), CHECK((axis='type' AND kind='type') OR (axis!='type' AND kind='facet')),
 FOREIGN KEY(version,kind) REFERENCES classification_dictionaries(version,kind),
 FOREIGN KEY(version,axis,parent_code) REFERENCES classification_terms(version,axis,code),
 FOREIGN KEY(version,axis,replacement_code) REFERENCES classification_terms(version,axis,code) DEFERRABLE INITIALLY DEFERRED
);
CREATE TABLE asset_classification_selections (
 asset_id TEXT PRIMARY KEY REFERENCES assets(id), type_version TEXT NOT NULL REFERENCES classification_dictionaries(version),
 primary_code TEXT, primary_axis TEXT NOT NULL DEFAULT 'type' CHECK(primary_axis='type'),
 FOREIGN KEY(type_version,primary_axis,primary_code) REFERENCES classification_terms(version,axis,code)
);
CREATE TABLE asset_classification_links (
 asset_id TEXT NOT NULL REFERENCES assets(id), version TEXT NOT NULL, axis TEXT NOT NULL, code TEXT NOT NULL,
 PRIMARY KEY(asset_id,version,axis,code), FOREIGN KEY(version,axis,code) REFERENCES classification_terms(version,axis,code)
);
CREATE TABLE asset_file_members (
 asset_id TEXT NOT NULL REFERENCES assets(id), file_id TEXT NOT NULL REFERENCES asset_files(id),
 role TEXT NOT NULL CHECK(role IN ('source','dependency','preview','evidence')), PRIMARY KEY(asset_id,file_id,role)
);
INSERT INTO asset_file_members SELECT asset_id,id,'source' FROM asset_files;
CREATE TABLE asset_components (
 id TEXT PRIMARY KEY, file_id TEXT NOT NULL REFERENCES asset_files(id), input_fingerprint TEXT NOT NULL CHECK(length(input_fingerprint)=64 AND input_fingerprint NOT GLOB '*[^0-9a-f]*'),
 kind TEXT NOT NULL CHECK(kind IN ('mesh','material','skeleton','animation','sprite_frame')),
 locator_json TEXT NOT NULL CHECK(json_valid(locator_json)), identity_version INTEGER NOT NULL CHECK(identity_version=1),
 UNIQUE(file_id,input_fingerprint,kind,locator_json)
);
CREATE TABLE metadata_claims (
 id TEXT PRIMARY KEY, asset_id TEXT NOT NULL REFERENCES assets(id), field TEXT NOT NULL CHECK(length(field) BETWEEN 1 AND 64),
 source TEXT NOT NULL CHECK(source IN ('file','parser','ai')), value_json TEXT NOT NULL CHECK(json_valid(value_json)),
 evidence_file_id TEXT REFERENCES asset_files(id), analysis_result_id TEXT, schema_version TEXT NOT NULL CHECK(length(schema_version) BETWEEN 1 AND 64), created_at TEXT NOT NULL,
 CHECK((source='ai' AND analysis_result_id IS NOT NULL AND evidence_file_id IS NULL) OR (source!='ai' AND evidence_file_id IS NOT NULL AND analysis_result_id IS NULL)),
 FOREIGN KEY(asset_id,analysis_result_id) REFERENCES analysis_results(asset_id,id), UNIQUE(asset_id,field,id)
);
CREATE TABLE metadata_decisions (
 asset_id TEXT NOT NULL REFERENCES assets(id), field TEXT NOT NULL CHECK(length(field) BETWEEN 1 AND 64),
 action TEXT NOT NULL CHECK(action IN ('set','clear','adopt')), value_json TEXT NOT NULL CHECK(json_valid(value_json)), claim_id TEXT,
 revision INTEGER NOT NULL CHECK(revision>0), updated_at TEXT NOT NULL,
 PRIMARY KEY(asset_id,field), CHECK((action='adopt' AND claim_id IS NOT NULL) OR (action!='adopt' AND claim_id IS NULL)),
 CHECK(action!='clear' OR value_json='null'), FOREIGN KEY(asset_id,field,claim_id) REFERENCES metadata_claims(asset_id,field,id)
);
CREATE TABLE metadata_decision_history (
 id INTEGER PRIMARY KEY, asset_id TEXT NOT NULL REFERENCES assets(id), field TEXT NOT NULL,
 revision INTEGER NOT NULL, action TEXT NOT NULL, before_json TEXT CHECK(before_json IS NULL OR json_valid(before_json)),
 after_json TEXT NOT NULL CHECK(json_valid(after_json)), created_at TEXT NOT NULL, UNIQUE(asset_id,field,revision)
);
CREATE INDEX metadata_claims_field ON metadata_claims(asset_id,field,created_at);
CREATE INDEX classification_lookup ON asset_classification_links(version,axis,code,asset_id);
CREATE INDEX component_file ON asset_components(file_id,input_fingerprint);
CREATE TRIGGER metadata_claim_member BEFORE INSERT ON metadata_claims WHEN NEW.evidence_file_id IS NOT NULL BEGIN
 SELECT CASE WHEN NOT EXISTS(SELECT 1 FROM asset_file_members WHERE asset_id=NEW.asset_id AND file_id=NEW.evidence_file_id) THEN RAISE(ABORT,'FILE_NOT_MEMBER') END;
END;
CREATE TRIGGER decision_initial BEFORE INSERT ON metadata_decisions WHEN NEW.revision!=1 AND NOT EXISTS(SELECT 1 FROM metadata_decisions WHERE asset_id=NEW.asset_id AND field=NEW.field) BEGIN
 SELECT RAISE(ABORT,'METADATA_CONFLICT');
END;
CREATE TRIGGER decision_revision BEFORE UPDATE ON metadata_decisions WHEN NEW.revision!=OLD.revision+1 OR NEW.asset_id!=OLD.asset_id OR NEW.field!=OLD.field BEGIN
 SELECT RAISE(ABORT,'METADATA_CONFLICT');
END;
CREATE TRIGGER decision_history_insert AFTER INSERT ON metadata_decisions BEGIN
 INSERT INTO metadata_decision_history(asset_id,field,revision,action,before_json,after_json,created_at)
 VALUES(NEW.asset_id,NEW.field,NEW.revision,NEW.action,(SELECT json_object('source',source,'value',json(value_json),'claimId',id) FROM metadata_claims WHERE asset_id=NEW.asset_id AND field=NEW.field ORDER BY CASE WHEN source='ai' THEN 0 ELSE 1 END DESC,rowid DESC LIMIT 1),json_object('action',NEW.action,'value',json(NEW.value_json),'claimId',NEW.claim_id),NEW.updated_at);
END;
CREATE TRIGGER decision_history_update AFTER UPDATE ON metadata_decisions BEGIN
 INSERT INTO metadata_decision_history(asset_id,field,revision,action,before_json,after_json,created_at)
 VALUES(NEW.asset_id,NEW.field,NEW.revision,NEW.action,json_object('action',OLD.action,'value',json(OLD.value_json),'claimId',OLD.claim_id),json_object('action',NEW.action,'value',json(NEW.value_json),'claimId',NEW.claim_id),NEW.updated_at);
END;
CREATE TRIGGER classification_dictionaries_no_update BEFORE UPDATE ON classification_dictionaries BEGIN
 SELECT RAISE(ABORT,'METADATA_IMMUTABLE');
END;
CREATE TRIGGER classification_dictionaries_no_delete BEFORE DELETE ON classification_dictionaries BEGIN
 SELECT RAISE(ABORT,'METADATA_IMMUTABLE');
END;
CREATE TRIGGER classification_terms_no_update BEFORE UPDATE ON classification_terms BEGIN
 SELECT RAISE(ABORT,'METADATA_IMMUTABLE');
END;
CREATE TRIGGER classification_terms_no_delete BEFORE DELETE ON classification_terms BEGIN
 SELECT RAISE(ABORT,'METADATA_IMMUTABLE');
END;
CREATE TRIGGER metadata_claims_no_update BEFORE UPDATE ON metadata_claims BEGIN
 SELECT RAISE(ABORT,'METADATA_IMMUTABLE');
END;
CREATE TRIGGER metadata_claims_no_delete BEFORE DELETE ON metadata_claims BEGIN
 SELECT RAISE(ABORT,'METADATA_IMMUTABLE');
END;
CREATE TRIGGER metadata_decision_history_no_update BEFORE UPDATE ON metadata_decision_history BEGIN
 SELECT RAISE(ABORT,'METADATA_IMMUTABLE');
END;
CREATE TRIGGER metadata_decision_history_no_delete BEFORE DELETE ON metadata_decision_history BEGIN
 SELECT RAISE(ABORT,'METADATA_IMMUTABLE');
END;
CREATE TRIGGER asset_components_no_update BEFORE UPDATE ON asset_components BEGIN
 SELECT RAISE(ABORT,'METADATA_IMMUTABLE');
END;
CREATE TRIGGER asset_components_no_delete BEFORE DELETE ON asset_components BEGIN
 SELECT RAISE(ABORT,'METADATA_IMMUTABLE');
END;
CREATE TRIGGER decision_no_delete BEFORE DELETE ON metadata_decisions BEGIN
 SELECT RAISE(ABORT,'USE_EXPLICIT_CLEAR');
END;
CREATE TRIGGER dictionary_payload BEFORE INSERT ON classification_dictionaries BEGIN
 SELECT CASE WHEN json_extract(NEW.payload_json,'$.version') IS NOT NEW.version OR json_type(NEW.payload_json,CASE WHEN NEW.kind='type' THEN '$.categories' ELSE '$.terms' END) IS NOT 'array' THEN RAISE(ABORT,'INVALID_DICTIONARY') END;
END;
CREATE TRIGGER term_payload BEFORE INSERT ON classification_terms BEGIN
 SELECT CASE WHEN NOT EXISTS(SELECT 1 FROM classification_dictionaries d,json_each(d.payload_json,CASE WHEN NEW.kind='type' THEN '$.categories' ELSE '$.terms' END) j WHERE d.version=NEW.version AND json_extract(j.value,'$.code')=NEW.code AND coalesce(json_extract(j.value,'$.axis'),'type')=NEW.axis AND json_extract(j.value,'$.parent') IS NEW.parent_code AND coalesce(json_extract(j.value,'$.labels.ko'),json_extract(j.value,'$.ko'))=NEW.ko AND coalesce(json_extract(j.value,'$.labels.en'),json_extract(j.value,'$.en'))=NEW.en AND coalesce(json_extract(j.value,'$.aliases'),'[]')=json(NEW.aliases_json) AND json_extract(j.value,'$.active')=NEW.active AND json_extract(j.value,'$.replacement') IS NEW.replacement_code) THEN RAISE(ABORT,'TERM_SNAPSHOT_MISMATCH') END;
END;
CREATE TRIGGER classification_link_active BEFORE INSERT ON asset_classification_links BEGIN
 SELECT CASE WHEN EXISTS(SELECT 1 FROM classification_terms WHERE version=NEW.version AND axis=NEW.axis AND active=0 AND (code=NEW.code OR (axis='type' AND NEW.code LIKE code||'.%'))) THEN RAISE(ABORT,'CATEGORY_UNAVAILABLE') END;
 SELECT CASE WHEN NEW.axis='type' AND (EXISTS(SELECT 1 FROM asset_classification_selections WHERE asset_id=NEW.asset_id AND type_version=NEW.version AND (primary_code=NEW.code OR primary_code LIKE NEW.code||'.%' OR NEW.code LIKE primary_code||'.%')) OR EXISTS(SELECT 1 FROM asset_classification_links WHERE asset_id=NEW.asset_id AND version=NEW.version AND axis='type' AND (code=NEW.code OR code LIKE NEW.code||'.%' OR NEW.code LIKE code||'.%'))) THEN RAISE(ABORT,'DUPLICATE_CLASSIFICATION') END;
END;
CREATE TRIGGER classification_primary_insert BEFORE INSERT ON asset_classification_selections WHEN NEW.primary_code IS NOT NULL BEGIN
 SELECT CASE WHEN EXISTS(SELECT 1 FROM classification_terms WHERE version=NEW.type_version AND axis='type' AND active=0 AND (code=NEW.primary_code OR NEW.primary_code LIKE code||'.%')) OR EXISTS(SELECT 1 FROM asset_classification_links WHERE asset_id=NEW.asset_id AND version=NEW.type_version AND axis='type' AND (code=NEW.primary_code OR code LIKE NEW.primary_code||'.%' OR NEW.primary_code LIKE code||'.%')) THEN RAISE(ABORT,'INVALID_PRIMARY_CLASSIFICATION') END;
END;
CREATE TRIGGER classification_primary_update BEFORE UPDATE ON asset_classification_selections WHEN NEW.primary_code IS NOT NULL BEGIN
 SELECT CASE WHEN EXISTS(SELECT 1 FROM classification_terms WHERE version=NEW.type_version AND axis='type' AND active=0 AND (code=NEW.primary_code OR NEW.primary_code LIKE code||'.%')) OR EXISTS(SELECT 1 FROM asset_classification_links WHERE asset_id=NEW.asset_id AND version=NEW.type_version AND axis='type' AND (code=NEW.primary_code OR code LIKE NEW.primary_code||'.%' OR NEW.primary_code LIKE code||'.%')) THEN RAISE(ABORT,'INVALID_PRIMARY_CLASSIFICATION') END;
END;
INSERT INTO classification_dictionaries VALUES ('asset-types.v1','type','{"version":"asset-types.v1","categories":[{"code":"A01","parent":null,"labels":{"ko":"2D 그래픽","en":"2D Graphics"},"aliases":[],"active":true,"depth":1},{"code":"A01.01","parent":"A01","labels":{"ko":"스프라이트","en":"Sprite"},"aliases":[],"active":true,"depth":2},{"code":"A01.02","parent":"A01","labels":{"ko":"배경 이미지","en":"Background Image"},"aliases":[],"active":true,"depth":2},{"code":"A01.03","parent":"A01","labels":{"ko":"일러스트","en":"Illustration"},"aliases":[],"active":true,"depth":2},{"code":"A01.04","parent":"A01","labels":{"ko":"아이콘","en":"Icon"},"aliases":[],"active":true,"depth":2},{"code":"A01.05","parent":"A01","labels":{"ko":"아틀라스","en":"Atlas"},"aliases":[],"active":true,"depth":2},{"code":"A02","parent":null,"labels":{"ko":"3D 모델","en":"3D Model"},"aliases":[],"active":true,"depth":1},{"code":"A02.01","parent":"A02","labels":{"ko":"캐릭터 모델","en":"Character Model"},"aliases":[],"active":true,"depth":2},{"code":"A02.01.01","parent":"A02.01","labels":{"ko":"인간 캐릭터 모델","en":"Human Character Model"},"aliases":["humanoid character model"],"active":true,"depth":3},{"code":"A02.02","parent":"A02","labels":{"ko":"무기 모델","en":"Weapon Model"},"aliases":[],"active":true,"depth":2},{"code":"A02.03","parent":"A02","labels":{"ko":"건축물 모델","en":"Building Model"},"aliases":[],"active":true,"depth":2},{"code":"A02.04","parent":"A02","labels":{"ko":"소품 모델","en":"Prop Model"},"aliases":[],"active":true,"depth":2},{"code":"A02.05","parent":"A02","labels":{"ko":"탈것 모델","en":"Vehicle Model"},"aliases":[],"active":true,"depth":2},{"code":"A03","parent":null,"labels":{"ko":"애니메이션","en":"Animation"},"aliases":[],"active":true,"depth":1},{"code":"A03.01","parent":"A03","labels":{"ko":"2D 애니메이션","en":"2D Animation"},"aliases":[],"active":true,"depth":2},{"code":"A03.02","parent":"A03","labels":{"ko":"3D 모션","en":"3D Motion"},"aliases":[],"active":true,"depth":2},{"code":"A03.02.01","parent":"A03.02","labels":{"ko":"걷기 모션","en":"Walk Motion"},"aliases":["walking animation","보행 모션"],"active":true,"depth":3},{"code":"A03.03","parent":"A03","labels":{"ko":"리깅","en":"Rigging"},"aliases":[],"active":true,"depth":2},{"code":"A03.04","parent":"A03","labels":{"ko":"표정 애니메이션","en":"Facial Animation"},"aliases":[],"active":true,"depth":2},{"code":"A04","parent":null,"labels":{"ko":"텍스처·머티리얼","en":"Textures and Materials"},"aliases":[],"active":true,"depth":1},{"code":"A04.01","parent":"A04","labels":{"ko":"PBR 맵","en":"PBR Map"},"aliases":[],"active":true,"depth":2},{"code":"A04.02","parent":"A04","labels":{"ko":"표면 텍스처","en":"Surface Texture"},"aliases":[],"active":true,"depth":2},{"code":"A04.03","parent":"A04","labels":{"ko":"머티리얼","en":"Material"},"aliases":[],"active":true,"depth":2},{"code":"A04.04","parent":"A04","labels":{"ko":"셰이더","en":"Shader"},"aliases":[],"active":true,"depth":2},{"code":"A05","parent":null,"labels":{"ko":"시각 효과(VFX)","en":"Visual Effects"},"aliases":[],"active":true,"depth":1},{"code":"A05.01","parent":"A05","labels":{"ko":"파티클","en":"Particle"},"aliases":[],"active":true,"depth":2},{"code":"A05.02","parent":"A05","labels":{"ko":"마법 효과","en":"Magic Effect"},"aliases":[],"active":true,"depth":2},{"code":"A05.03","parent":"A05","labels":{"ko":"폭발 효과","en":"Explosion Effect"},"aliases":[],"active":true,"depth":2},{"code":"A05.04","parent":"A05","labels":{"ko":"날씨 효과","en":"Weather Effect"},"aliases":[],"active":true,"depth":2},{"code":"A05.05","parent":"A05","labels":{"ko":"상태 효과","en":"Status Effect"},"aliases":[],"active":true,"depth":2},{"code":"A06","parent":null,"labels":{"ko":"오디오","en":"Audio"},"aliases":[],"active":true,"depth":1},{"code":"A06.01","parent":"A06","labels":{"ko":"BGM","en":"Background Music"},"aliases":[],"active":true,"depth":2},{"code":"A06.02","parent":"A06","labels":{"ko":"효과음","en":"Sound Effect"},"aliases":[],"active":true,"depth":2},{"code":"A06.02.01","parent":"A06.02","labels":{"ko":"금속 충돌 효과음","en":"Metal Impact Sound"},"aliases":["metal hit","금속 타격음"],"active":true,"depth":3},{"code":"A06.03","parent":"A06","labels":{"ko":"음성","en":"Voice"},"aliases":[],"active":true,"depth":2},{"code":"A06.04","parent":"A06","labels":{"ko":"환경음","en":"Ambience"},"aliases":[],"active":true,"depth":2},{"code":"A07","parent":null,"labels":{"ko":"UI·UX","en":"UI and UX"},"aliases":[],"active":true,"depth":1},{"code":"A07.01","parent":"A07","labels":{"ko":"버튼","en":"Button"},"aliases":[],"active":true,"depth":2},{"code":"A07.02","parent":"A07","labels":{"ko":"패널","en":"Panel"},"aliases":[],"active":true,"depth":2},{"code":"A07.03","parent":"A07","labels":{"ko":"HUD","en":"Heads-Up Display"},"aliases":[],"active":true,"depth":2},{"code":"A07.04","parent":"A07","labels":{"ko":"인벤토리 UI","en":"Inventory UI"},"aliases":[],"active":true,"depth":2},{"code":"A07.05","parent":"A07","labels":{"ko":"메뉴","en":"Menu"},"aliases":[],"active":true,"depth":2},{"code":"A08","parent":null,"labels":{"ko":"환경·월드","en":"Environment and World"},"aliases":[],"active":true,"depth":1},{"code":"A08.01","parent":"A08","labels":{"ko":"타일셋","en":"Tileset"},"aliases":[],"active":true,"depth":2},{"code":"A08.02","parent":"A08","labels":{"ko":"지형","en":"Terrain"},"aliases":[],"active":true,"depth":2},{"code":"A08.03","parent":"A08","labels":{"ko":"맵","en":"Map"},"aliases":[],"active":true,"depth":2},{"code":"A08.04","parent":"A08","labels":{"ko":"스카이박스","en":"Skybox"},"aliases":[],"active":true,"depth":2},{"code":"A09","parent":null,"labels":{"ko":"캐릭터·아바타","en":"Characters and Avatars"},"aliases":[],"active":true,"depth":1},{"code":"A09.01","parent":"A09","labels":{"ko":"캐릭터 세트","en":"Character Set"},"aliases":[],"active":true,"depth":2},{"code":"A09.02","parent":"A09","labels":{"ko":"외형","en":"Appearance"},"aliases":[],"active":true,"depth":2},{"code":"A09.03","parent":"A09","labels":{"ko":"의상","en":"Clothing"},"aliases":[],"active":true,"depth":2},{"code":"A09.04","parent":"A09","labels":{"ko":"장비 구성","en":"Equipment Set"},"aliases":[],"active":true,"depth":2},{"code":"A10","parent":null,"labels":{"ko":"게임플레이 데이터","en":"Gameplay Data"},"aliases":[],"active":true,"depth":1},{"code":"A10.01","parent":"A10","labels":{"ko":"카드 데이터","en":"Card Data"},"aliases":[],"active":true,"depth":2},{"code":"A10.02","parent":"A10","labels":{"ko":"아이템 데이터","en":"Item Data"},"aliases":[],"active":true,"depth":2},{"code":"A10.03","parent":"A10","labels":{"ko":"스킬 데이터","en":"Skill Data"},"aliases":[],"active":true,"depth":2},{"code":"A10.04","parent":"A10","labels":{"ko":"능력치","en":"Stats"},"aliases":[],"active":true,"depth":2},{"code":"A10.05","parent":"A10","labels":{"ko":"퀘스트","en":"Quest"},"aliases":[],"active":true,"depth":2},{"code":"A11","parent":null,"labels":{"ko":"폰트·텍스트","en":"Fonts and Text"},"aliases":[],"active":true,"depth":1},{"code":"A11.01","parent":"A11","labels":{"ko":"폰트","en":"Font"},"aliases":[],"active":true,"depth":2},{"code":"A11.02","parent":"A11","labels":{"ko":"대사","en":"Dialogue"},"aliases":[],"active":true,"depth":2},{"code":"A11.03","parent":"A11","labels":{"ko":"자막","en":"Subtitle"},"aliases":[],"active":true,"depth":2},{"code":"A11.04","parent":"A11","labels":{"ko":"다국어 데이터","en":"Localization Data"},"aliases":[],"active":true,"depth":2},{"code":"A12","parent":null,"labels":{"ko":"코드·기능","en":"Code and Functionality"},"aliases":[],"active":true,"depth":1},{"code":"A12.01","parent":"A12","labels":{"ko":"스크립트","en":"Script"},"aliases":[],"active":true,"depth":2},{"code":"A12.02","parent":"A12","labels":{"ko":"플러그인","en":"Plugin"},"aliases":[],"active":true,"depth":2},{"code":"A12.03","parent":"A12","labels":{"ko":"게임 시스템","en":"Game System"},"aliases":[],"active":true,"depth":2},{"code":"A13","parent":null,"labels":{"ko":"씬·프리팹","en":"Scenes and Prefabs"},"aliases":[],"active":true,"depth":1},{"code":"A13.01","parent":"A13","labels":{"ko":"씬","en":"Scene"},"aliases":[],"active":true,"depth":2},{"code":"A13.02","parent":"A13","labels":{"ko":"프리팹","en":"Prefab"},"aliases":[],"active":true,"depth":2},{"code":"A13.03","parent":"A13","labels":{"ko":"재사용 오브젝트","en":"Reusable Object"},"aliases":[],"active":true,"depth":2},{"code":"A13.04","parent":"A13","labels":{"ko":"템플릿","en":"Template"},"aliases":[],"active":true,"depth":2},{"code":"A14","parent":null,"labels":{"ko":"패키지·프로젝트","en":"Packages and Projects"},"aliases":[],"active":true,"depth":1},{"code":"A14.01","parent":"A14","labels":{"ko":"에셋 팩","en":"Asset Pack"},"aliases":[],"active":true,"depth":2},{"code":"A14.02","parent":"A14","labels":{"ko":"Unity 패키지","en":"Unity Package"},"aliases":[],"active":true,"depth":2},{"code":"A14.03","parent":"A14","labels":{"ko":"프로젝트","en":"Project"},"aliases":[],"active":true,"depth":2}]}');
INSERT INTO classification_terms VALUES ('asset-types.v1','type','type','A01',NULL,'2D 그래픽','2D Graphics','[]',1,NULL);
INSERT INTO classification_terms VALUES ('asset-types.v1','type','type','A01.01','A01','스프라이트','Sprite','[]',1,NULL);
INSERT INTO classification_terms VALUES ('asset-types.v1','type','type','A01.02','A01','배경 이미지','Background Image','[]',1,NULL);
INSERT INTO classification_terms VALUES ('asset-types.v1','type','type','A01.03','A01','일러스트','Illustration','[]',1,NULL);
INSERT INTO classification_terms VALUES ('asset-types.v1','type','type','A01.04','A01','아이콘','Icon','[]',1,NULL);
INSERT INTO classification_terms VALUES ('asset-types.v1','type','type','A01.05','A01','아틀라스','Atlas','[]',1,NULL);
INSERT INTO classification_terms VALUES ('asset-types.v1','type','type','A02',NULL,'3D 모델','3D Model','[]',1,NULL);
INSERT INTO classification_terms VALUES ('asset-types.v1','type','type','A02.01','A02','캐릭터 모델','Character Model','[]',1,NULL);
INSERT INTO classification_terms VALUES ('asset-types.v1','type','type','A02.01.01','A02.01','인간 캐릭터 모델','Human Character Model','["humanoid character model"]',1,NULL);
INSERT INTO classification_terms VALUES ('asset-types.v1','type','type','A02.02','A02','무기 모델','Weapon Model','[]',1,NULL);
INSERT INTO classification_terms VALUES ('asset-types.v1','type','type','A02.03','A02','건축물 모델','Building Model','[]',1,NULL);
INSERT INTO classification_terms VALUES ('asset-types.v1','type','type','A02.04','A02','소품 모델','Prop Model','[]',1,NULL);
INSERT INTO classification_terms VALUES ('asset-types.v1','type','type','A02.05','A02','탈것 모델','Vehicle Model','[]',1,NULL);
INSERT INTO classification_terms VALUES ('asset-types.v1','type','type','A03',NULL,'애니메이션','Animation','[]',1,NULL);
INSERT INTO classification_terms VALUES ('asset-types.v1','type','type','A03.01','A03','2D 애니메이션','2D Animation','[]',1,NULL);
INSERT INTO classification_terms VALUES ('asset-types.v1','type','type','A03.02','A03','3D 모션','3D Motion','[]',1,NULL);
INSERT INTO classification_terms VALUES ('asset-types.v1','type','type','A03.02.01','A03.02','걷기 모션','Walk Motion','["walking animation", "보행 모션"]',1,NULL);
INSERT INTO classification_terms VALUES ('asset-types.v1','type','type','A03.03','A03','리깅','Rigging','[]',1,NULL);
INSERT INTO classification_terms VALUES ('asset-types.v1','type','type','A03.04','A03','표정 애니메이션','Facial Animation','[]',1,NULL);
INSERT INTO classification_terms VALUES ('asset-types.v1','type','type','A04',NULL,'텍스처·머티리얼','Textures and Materials','[]',1,NULL);
INSERT INTO classification_terms VALUES ('asset-types.v1','type','type','A04.01','A04','PBR 맵','PBR Map','[]',1,NULL);
INSERT INTO classification_terms VALUES ('asset-types.v1','type','type','A04.02','A04','표면 텍스처','Surface Texture','[]',1,NULL);
INSERT INTO classification_terms VALUES ('asset-types.v1','type','type','A04.03','A04','머티리얼','Material','[]',1,NULL);
INSERT INTO classification_terms VALUES ('asset-types.v1','type','type','A04.04','A04','셰이더','Shader','[]',1,NULL);
INSERT INTO classification_terms VALUES ('asset-types.v1','type','type','A05',NULL,'시각 효과(VFX)','Visual Effects','[]',1,NULL);
INSERT INTO classification_terms VALUES ('asset-types.v1','type','type','A05.01','A05','파티클','Particle','[]',1,NULL);
INSERT INTO classification_terms VALUES ('asset-types.v1','type','type','A05.02','A05','마법 효과','Magic Effect','[]',1,NULL);
INSERT INTO classification_terms VALUES ('asset-types.v1','type','type','A05.03','A05','폭발 효과','Explosion Effect','[]',1,NULL);
INSERT INTO classification_terms VALUES ('asset-types.v1','type','type','A05.04','A05','날씨 효과','Weather Effect','[]',1,NULL);
INSERT INTO classification_terms VALUES ('asset-types.v1','type','type','A05.05','A05','상태 효과','Status Effect','[]',1,NULL);
INSERT INTO classification_terms VALUES ('asset-types.v1','type','type','A06',NULL,'오디오','Audio','[]',1,NULL);
INSERT INTO classification_terms VALUES ('asset-types.v1','type','type','A06.01','A06','BGM','Background Music','[]',1,NULL);
INSERT INTO classification_terms VALUES ('asset-types.v1','type','type','A06.02','A06','효과음','Sound Effect','[]',1,NULL);
INSERT INTO classification_terms VALUES ('asset-types.v1','type','type','A06.02.01','A06.02','금속 충돌 효과음','Metal Impact Sound','["metal hit", "금속 타격음"]',1,NULL);
INSERT INTO classification_terms VALUES ('asset-types.v1','type','type','A06.03','A06','음성','Voice','[]',1,NULL);
INSERT INTO classification_terms VALUES ('asset-types.v1','type','type','A06.04','A06','환경음','Ambience','[]',1,NULL);
INSERT INTO classification_terms VALUES ('asset-types.v1','type','type','A07',NULL,'UI·UX','UI and UX','[]',1,NULL);
INSERT INTO classification_terms VALUES ('asset-types.v1','type','type','A07.01','A07','버튼','Button','[]',1,NULL);
INSERT INTO classification_terms VALUES ('asset-types.v1','type','type','A07.02','A07','패널','Panel','[]',1,NULL);
INSERT INTO classification_terms VALUES ('asset-types.v1','type','type','A07.03','A07','HUD','Heads-Up Display','[]',1,NULL);
INSERT INTO classification_terms VALUES ('asset-types.v1','type','type','A07.04','A07','인벤토리 UI','Inventory UI','[]',1,NULL);
INSERT INTO classification_terms VALUES ('asset-types.v1','type','type','A07.05','A07','메뉴','Menu','[]',1,NULL);
INSERT INTO classification_terms VALUES ('asset-types.v1','type','type','A08',NULL,'환경·월드','Environment and World','[]',1,NULL);
INSERT INTO classification_terms VALUES ('asset-types.v1','type','type','A08.01','A08','타일셋','Tileset','[]',1,NULL);
INSERT INTO classification_terms VALUES ('asset-types.v1','type','type','A08.02','A08','지형','Terrain','[]',1,NULL);
INSERT INTO classification_terms VALUES ('asset-types.v1','type','type','A08.03','A08','맵','Map','[]',1,NULL);
INSERT INTO classification_terms VALUES ('asset-types.v1','type','type','A08.04','A08','스카이박스','Skybox','[]',1,NULL);
INSERT INTO classification_terms VALUES ('asset-types.v1','type','type','A09',NULL,'캐릭터·아바타','Characters and Avatars','[]',1,NULL);
INSERT INTO classification_terms VALUES ('asset-types.v1','type','type','A09.01','A09','캐릭터 세트','Character Set','[]',1,NULL);
INSERT INTO classification_terms VALUES ('asset-types.v1','type','type','A09.02','A09','외형','Appearance','[]',1,NULL);
INSERT INTO classification_terms VALUES ('asset-types.v1','type','type','A09.03','A09','의상','Clothing','[]',1,NULL);
INSERT INTO classification_terms VALUES ('asset-types.v1','type','type','A09.04','A09','장비 구성','Equipment Set','[]',1,NULL);
INSERT INTO classification_terms VALUES ('asset-types.v1','type','type','A10',NULL,'게임플레이 데이터','Gameplay Data','[]',1,NULL);
INSERT INTO classification_terms VALUES ('asset-types.v1','type','type','A10.01','A10','카드 데이터','Card Data','[]',1,NULL);
INSERT INTO classification_terms VALUES ('asset-types.v1','type','type','A10.02','A10','아이템 데이터','Item Data','[]',1,NULL);
INSERT INTO classification_terms VALUES ('asset-types.v1','type','type','A10.03','A10','스킬 데이터','Skill Data','[]',1,NULL);
INSERT INTO classification_terms VALUES ('asset-types.v1','type','type','A10.04','A10','능력치','Stats','[]',1,NULL);
INSERT INTO classification_terms VALUES ('asset-types.v1','type','type','A10.05','A10','퀘스트','Quest','[]',1,NULL);
INSERT INTO classification_terms VALUES ('asset-types.v1','type','type','A11',NULL,'폰트·텍스트','Fonts and Text','[]',1,NULL);
INSERT INTO classification_terms VALUES ('asset-types.v1','type','type','A11.01','A11','폰트','Font','[]',1,NULL);
INSERT INTO classification_terms VALUES ('asset-types.v1','type','type','A11.02','A11','대사','Dialogue','[]',1,NULL);
INSERT INTO classification_terms VALUES ('asset-types.v1','type','type','A11.03','A11','자막','Subtitle','[]',1,NULL);
INSERT INTO classification_terms VALUES ('asset-types.v1','type','type','A11.04','A11','다국어 데이터','Localization Data','[]',1,NULL);
INSERT INTO classification_terms VALUES ('asset-types.v1','type','type','A12',NULL,'코드·기능','Code and Functionality','[]',1,NULL);
INSERT INTO classification_terms VALUES ('asset-types.v1','type','type','A12.01','A12','스크립트','Script','[]',1,NULL);
INSERT INTO classification_terms VALUES ('asset-types.v1','type','type','A12.02','A12','플러그인','Plugin','[]',1,NULL);
INSERT INTO classification_terms VALUES ('asset-types.v1','type','type','A12.03','A12','게임 시스템','Game System','[]',1,NULL);
INSERT INTO classification_terms VALUES ('asset-types.v1','type','type','A13',NULL,'씬·프리팹','Scenes and Prefabs','[]',1,NULL);
INSERT INTO classification_terms VALUES ('asset-types.v1','type','type','A13.01','A13','씬','Scene','[]',1,NULL);
INSERT INTO classification_terms VALUES ('asset-types.v1','type','type','A13.02','A13','프리팹','Prefab','[]',1,NULL);
INSERT INTO classification_terms VALUES ('asset-types.v1','type','type','A13.03','A13','재사용 오브젝트','Reusable Object','[]',1,NULL);
INSERT INTO classification_terms VALUES ('asset-types.v1','type','type','A13.04','A13','템플릿','Template','[]',1,NULL);
INSERT INTO classification_terms VALUES ('asset-types.v1','type','type','A14',NULL,'패키지·프로젝트','Packages and Projects','[]',1,NULL);
INSERT INTO classification_terms VALUES ('asset-types.v1','type','type','A14.01','A14','에셋 팩','Asset Pack','[]',1,NULL);
INSERT INTO classification_terms VALUES ('asset-types.v1','type','type','A14.02','A14','Unity 패키지','Unity Package','[]',1,NULL);
INSERT INTO classification_terms VALUES ('asset-types.v1','type','type','A14.03','A14','프로젝트','Project','[]',1,NULL);
INSERT INTO classification_dictionaries VALUES ('asset-facets.v1','facet','{"version":"asset-facets.v1","terms":[{"axis":"role","code":"role.player","ko":"플레이어","en":"Player","active":true,"replacement":null},{"axis":"role","code":"role.monster","ko":"몬스터","en":"Monster","active":true,"replacement":null},{"axis":"role","code":"role.npc","ko":"NPC","en":"Non-Player Character","active":true,"replacement":null},{"axis":"role","code":"role.weapon","ko":"무기","en":"Weapon","active":true,"replacement":null},{"axis":"role","code":"role.item","ko":"아이템","en":"Item","active":true,"replacement":null},{"axis":"role","code":"role.environment","ko":"환경","en":"Environment","active":true,"replacement":null},{"axis":"role","code":"role.card","ko":"카드","en":"Card","active":true,"replacement":null},{"axis":"style","code":"style.pixel","ko":"픽셀아트","en":"Pixel Art","active":true,"replacement":null},{"axis":"style","code":"style.anime","ko":"애니메풍","en":"Anime","active":true,"replacement":null},{"axis":"style","code":"style.cartoon","ko":"카툰","en":"Cartoon","active":true,"replacement":null},{"axis":"style","code":"style.realistic","ko":"실사풍","en":"Realistic","active":true,"replacement":null},{"axis":"style","code":"style.low_poly","ko":"로우폴리","en":"Low Poly","active":true,"replacement":null},{"axis":"genre","code":"genre.fantasy","ko":"판타지","en":"Fantasy","active":true,"replacement":null},{"axis":"genre","code":"genre.sci_fi","ko":"SF","en":"Sci-Fi","active":true,"replacement":null},{"axis":"genre","code":"genre.modern","ko":"현대","en":"Modern","active":true,"replacement":null},{"axis":"genre","code":"genre.horror","ko":"공포","en":"Horror","active":true,"replacement":null},{"axis":"view","code":"view.top_down","ko":"탑다운","en":"Top-Down","active":true,"replacement":null},{"axis":"view","code":"view.side","ko":"측면","en":"Side-View","active":true,"replacement":null},{"axis":"view","code":"view.isometric","ko":"아이소메트릭","en":"Isometric","active":true,"replacement":null},{"axis":"view","code":"view.first_person","ko":"1인칭","en":"First-Person","active":true,"replacement":null},{"axis":"dimension","code":"dimension.2d","ko":"2D","en":"2D","active":true,"replacement":null},{"axis":"dimension","code":"dimension.2_5d","ko":"2.5D","en":"2.5D","active":true,"replacement":null},{"axis":"dimension","code":"dimension.3d","ko":"3D","en":"3D","active":true,"replacement":null},{"axis":"engine","code":"engine.unity","ko":"Unity","en":"Unity","active":true,"replacement":null},{"axis":"engine","code":"engine.godot","ko":"Godot","en":"Godot","active":true,"replacement":null},{"axis":"engine","code":"engine.unreal","ko":"Unreal","en":"Unreal","active":true,"replacement":null},{"axis":"engine","code":"engine.generic","ko":"범용","en":"Generic","active":true,"replacement":null}]}');
INSERT INTO classification_terms VALUES ('asset-facets.v1','facet','role','role.player',NULL,'플레이어','Player','[]',1,NULL);
INSERT INTO classification_terms VALUES ('asset-facets.v1','facet','role','role.monster',NULL,'몬스터','Monster','[]',1,NULL);
INSERT INTO classification_terms VALUES ('asset-facets.v1','facet','role','role.npc',NULL,'NPC','Non-Player Character','[]',1,NULL);
INSERT INTO classification_terms VALUES ('asset-facets.v1','facet','role','role.weapon',NULL,'무기','Weapon','[]',1,NULL);
INSERT INTO classification_terms VALUES ('asset-facets.v1','facet','role','role.item',NULL,'아이템','Item','[]',1,NULL);
INSERT INTO classification_terms VALUES ('asset-facets.v1','facet','role','role.environment',NULL,'환경','Environment','[]',1,NULL);
INSERT INTO classification_terms VALUES ('asset-facets.v1','facet','role','role.card',NULL,'카드','Card','[]',1,NULL);
INSERT INTO classification_terms VALUES ('asset-facets.v1','facet','style','style.pixel',NULL,'픽셀아트','Pixel Art','[]',1,NULL);
INSERT INTO classification_terms VALUES ('asset-facets.v1','facet','style','style.anime',NULL,'애니메풍','Anime','[]',1,NULL);
INSERT INTO classification_terms VALUES ('asset-facets.v1','facet','style','style.cartoon',NULL,'카툰','Cartoon','[]',1,NULL);
INSERT INTO classification_terms VALUES ('asset-facets.v1','facet','style','style.realistic',NULL,'실사풍','Realistic','[]',1,NULL);
INSERT INTO classification_terms VALUES ('asset-facets.v1','facet','style','style.low_poly',NULL,'로우폴리','Low Poly','[]',1,NULL);
INSERT INTO classification_terms VALUES ('asset-facets.v1','facet','genre','genre.fantasy',NULL,'판타지','Fantasy','[]',1,NULL);
INSERT INTO classification_terms VALUES ('asset-facets.v1','facet','genre','genre.sci_fi',NULL,'SF','Sci-Fi','[]',1,NULL);
INSERT INTO classification_terms VALUES ('asset-facets.v1','facet','genre','genre.modern',NULL,'현대','Modern','[]',1,NULL);
INSERT INTO classification_terms VALUES ('asset-facets.v1','facet','genre','genre.horror',NULL,'공포','Horror','[]',1,NULL);
INSERT INTO classification_terms VALUES ('asset-facets.v1','facet','view','view.top_down',NULL,'탑다운','Top-Down','[]',1,NULL);
INSERT INTO classification_terms VALUES ('asset-facets.v1','facet','view','view.side',NULL,'측면','Side-View','[]',1,NULL);
INSERT INTO classification_terms VALUES ('asset-facets.v1','facet','view','view.isometric',NULL,'아이소메트릭','Isometric','[]',1,NULL);
INSERT INTO classification_terms VALUES ('asset-facets.v1','facet','view','view.first_person',NULL,'1인칭','First-Person','[]',1,NULL);
INSERT INTO classification_terms VALUES ('asset-facets.v1','facet','dimension','dimension.2d',NULL,'2D','2D','[]',1,NULL);
INSERT INTO classification_terms VALUES ('asset-facets.v1','facet','dimension','dimension.2_5d',NULL,'2.5D','2.5D','[]',1,NULL);
INSERT INTO classification_terms VALUES ('asset-facets.v1','facet','dimension','dimension.3d',NULL,'3D','3D','[]',1,NULL);
INSERT INTO classification_terms VALUES ('asset-facets.v1','facet','engine','engine.unity',NULL,'Unity','Unity','[]',1,NULL);
INSERT INTO classification_terms VALUES ('asset-facets.v1','facet','engine','engine.godot',NULL,'Godot','Godot','[]',1,NULL);
INSERT INTO classification_terms VALUES ('asset-facets.v1','facet','engine','engine.unreal',NULL,'Unreal','Unreal','[]',1,NULL);
INSERT INTO classification_terms VALUES ('asset-facets.v1','facet','engine','engine.generic',NULL,'범용','Generic','[]',1,NULL);

CREATE TRIGGER file_member_on_scan AFTER INSERT ON asset_files BEGIN
 INSERT INTO asset_file_members VALUES (NEW.asset_id,NEW.id,'source');
END;
CREATE TRIGGER decision_adopt_insert BEFORE INSERT ON metadata_decisions WHEN NEW.action='adopt' BEGIN
 SELECT CASE WHEN NOT EXISTS(SELECT 1 FROM metadata_claims WHERE id=NEW.claim_id AND asset_id=NEW.asset_id AND field=NEW.field AND value_json=NEW.value_json) THEN RAISE(ABORT,'CLAIM_MISMATCH') END;
END;
CREATE TRIGGER decision_adopt_update BEFORE UPDATE ON metadata_decisions WHEN NEW.action='adopt' BEGIN
 SELECT CASE WHEN NOT EXISTS(SELECT 1 FROM metadata_claims WHERE id=NEW.claim_id AND asset_id=NEW.asset_id AND field=NEW.field AND value_json=NEW.value_json) THEN RAISE(ABORT,'CLAIM_MISMATCH') END;
END;
