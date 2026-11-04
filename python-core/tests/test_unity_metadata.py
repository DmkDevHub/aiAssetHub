import json
import unittest
from unittest.mock import patch
from uuid import uuid4
import test_annotations
import test_technical
from ai_asset_hub_core.unity_metadata import UnityMetadata
from ai_asset_hub_core.license_records import Licenses
from ai_asset_hub_core.mcp_queries import McpQueries
from ai_asset_hub_core.libraries import LibraryError
from ai_asset_hub_core.technical import Technical
from ai_asset_hub_core.asset_management import AssetManagement


class UnityMetadataTests(unittest.TestCase):
    setUp=test_annotations.AnnotationTests.setUp
    tearDown=test_annotations.AnnotationTests.tearDown
    register=test_technical.TechnicalTests.register

    def project(self):
        root=self.base/'project';(root/'Assets').mkdir(parents=True);(root/'ProjectSettings').mkdir()
        (root/'ProjectSettings/ProjectVersion.txt').write_text('m_EditorVersion: 6000.0.23f1\n')
        return root

    def license(self,status='unknown',subject=None):
        return Licenses(self.db).create_record(dict(subject=subject or dict(kind='asset',id=self.id),confirmed=True,
            value=dict(label='Declared license',terms='PRIVATE-TERMS',attribution='PRIVATE-CREDIT',reviewStatus=status,scope='asset',note='PRIVATE-NOTE',source_id=None)))

    def test_public_mcp_metadata_never_claims_rights_compatibility_or_editor_success(self):
        for status in ('unknown','needs_review','user_reviewed'):self.license(status)
        before='\n'.join(self.db.connection.iterdump())
        result=McpQueries(self.db).dispatch('get_asset',dict(asset_id=self.id,schema_version=2))['unityPlanning']
        self.assertEqual(len(result['rights']['declarations']),3);self.assertEqual(result['rights']['permission'],'unknown')
        self.assertTrue(result['rights']['reviewRequired']);self.assertEqual(result['compatibility']['status'],'unknown')
        self.assertFalse(result['executable']);self.assertFalse(result['compatibility']['editorVerified'])
        self.assertNotIn('PRIVATE',json.dumps(result));self.assertEqual('\n'.join(self.db.connection.iterdump()),before)
        self.assertNotIn('unityPlanning',McpQueries(self.db).dispatch('get_asset',dict(asset_id=self.id)))

    def test_real_project_conflicts_and_preview_preserve_project_catalog_and_originals(self):
        project=self.project();destination=project/'Assets/AIAssetHub';destination.mkdir()
        (destination/'나무.png').write_bytes(b'existing destination');(destination/'나무.png.meta').write_bytes(b'existing meta')
        service=UnityMetadata(self.db,[project]);before='\n'.join(self.db.connection.iterdump())
        snapshot={str(p):p.read_bytes() for p in self.base.rglob('*') if p.is_file() and p.suffix not in ('.sqlite','.sqlite-wal','.sqlite-shm')}
        with patch('shutil.copyfile',side_effect=AssertionError('no copy')),patch('subprocess.Popen',side_effect=AssertionError('no Editor')):
            result=service.preview(dict(asset_id=self.id,project_path=str(project)))
        self.assertEqual(result['project']['editorVersion'],'6000.0.23f1');self.assertFalse(result['project']['editorConnected'])
        self.assertEqual(result['files'][0]['conflicts'],['TARGET_EXISTS','META_EXISTS'])
        self.assertIn('TARGET_CONFLICT',result['issues']);self.assertTrue(result['planOnly']);self.assertFalse(result['contentCopied'])
        self.assertEqual('\n'.join(self.db.connection.iterdump()),before)
        for path,raw in snapshot.items():
            from pathlib import Path
            self.assertEqual(Path(path).read_bytes(),raw)
        self.assertEqual(self.db.connection.execute('SELECT count(*) FROM analysis_jobs').fetchone()[0],0)
        self.assertEqual(self.db.connection.execute('SELECT count(*) FROM asset_embeddings').fetchone()[0],0)

    def test_untrusted_invalid_missing_and_reparse_project_inputs_fail_closed(self):
        project=self.project();request=dict(asset_id=self.id,project_path=str(project))
        with patch('pathlib.Path.stat',side_effect=AssertionError('must reject before probe')):
            with self.assertRaisesRegex(LibraryError,'UNITY_PROJECT_NOT_ALLOWED'):UnityMetadata(self.db).preview(request)
        service=UnityMetadata(self.db,[project]);(project/'ProjectSettings/ProjectVersion.txt').write_text('not a project')
        with self.assertRaisesRegex(LibraryError,'UNITY_PROJECT_UNAVAILABLE'):service.preview(request)
        with self.assertRaisesRegex(LibraryError,'INVALID_PARAMS'):service.preview({**request,'confirmed':True})
        with self.assertRaisesRegex(LibraryError,'INVALID_PARAMS'):service.preview({**request,'asset_id':str(uuid4())})
        with patch('ai_asset_hub_core.unity_metadata.no_links',side_effect=ValueError('private-path')):
            with self.assertRaisesRegex(LibraryError,'UNITY_PROJECT_UNAVAILABLE'):service.preview(request)

    def test_missing_unselected_dependencies_and_stale_technical_are_explicit(self):
        project=self.project();self.register('side.mtl',b'material')
        model=self.register('model.obj',b'mtllib side.mtl unknown.mtl\nv 0 0 0\nv 1 0 0\nv 0 1 0\nf 1 2 3\n')
        Technical(self.db).collect(dict(asset_id=model,confirmed=True));service=UnityMetadata(self.db,[project])
        result=service.preview(dict(asset_id=model,project_path=str(project)))
        self.assertIn('DEPENDENCY_NOT_SELECTED',result['issues']);self.assertIn('DEPENDENCY_UNRESOLVED',result['issues'])
        (self.source/'model.obj').unlink();result=service.preview(dict(asset_id=model,project_path=str(project)))
        self.assertIn('SOURCE_UNAVAILABLE',result['issues']);self.assertIn('TECHNICAL_STALE',result['issues'])
        self.assertFalse((project/'Assets/AIAssetHub').exists())

    def test_package_rights_engine_conflicts_and_same_filename_targets(self):
        from ai_asset_hub_core.packages import Packages
        from ai_asset_hub_core.assets import AssetService
        project=self.project();service=Packages(self.db);packages=[]
        for engine in ('Unity','Other'):
            package=service.package_create({'value':dict(name=engine,description='',unit='distribution',version='',purchase=dict(amount=None,currency='',date=''))})
            self.db.connection.execute('UPDATE asset_packages SET defaults_json=? WHERE id=?',(json.dumps(dict(engine=engine)),package['id']))
            packages.append(package['id']);self.license('user_reviewed',dict(kind='package',id=package['id']))
        service.package_assign(dict(asset_id=self.id,package_ids=packages,expected_revision=0))
        nested=self.source/'nested';nested.mkdir();(nested/'나무.png').write_bytes(b'second fixture')
        library=self.db.connection.execute('SELECT library_root_id FROM assets WHERE id=?',(self.id,)).fetchone()[0]
        AssetService(self.db).scan({'library_id':library})
        files=[r[0] for r in self.db.connection.execute('SELECT id FROM asset_files ORDER BY id')]
        AssetManagement(self.db).save_composition(dict(asset_id=self.id,expected_revision=0,value=dict(files=[dict(fileId=f,role='source') for f in files],components=[])))
        result=UnityMetadata(self.db,[project]).preview(dict(asset_id=self.id,project_path=str(project)))
        self.assertIn('ENGINE_DECLARATION_CONFLICT',result['issues']);self.assertIn('TARGET_CONFLICT',result['issues'])
        self.assertTrue(any('DUPLICATE_TARGET' in f['conflicts'] for f in result['files']))
        self.assertEqual(len(result['rights']['declarations']),2);self.assertEqual(result['rights']['permission'],'unknown')
