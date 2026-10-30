import json
import unittest
from unittest.mock import patch
from uuid import uuid4
import test_annotations
import test_technical
from ai_asset_hub_core.technical import Technical
from ai_asset_hub_core.mcp_queries import McpQueries
from ai_asset_hub_core.asset_management import AssetManagement
from ai_asset_hub_core.libraries import LibraryError, LibraryService
from ai_asset_hub_core.assets import AssetService


class McpFileTests(unittest.TestCase):
    setUp=test_annotations.AnnotationTests.setUp
    tearDown=test_annotations.AnnotationTests.tearDown
    register=test_technical.TechnicalTests.register

    def read(self,asset=None,**extra):
        return McpQueries(self.db).dispatch('get_asset_files',dict(asset_id=asset or self.id,schema_version=2,**extra))

    def file_id(self,asset):return self.db.connection.execute('SELECT id FROM asset_files WHERE asset_id=?',(asset,)).fetchone()[0]

    def test_real_parser_metrics_roles_and_registered_dependencies_without_content_reads_or_writes(self):
        dependency=self.register('material.mtl',b'fixture material')
        model=self.register('mesh.obj',b'mtllib material.mtl missing.mtl ../PRIVATE https://secret.invalid/?token=PRIVATE\nv 0 0 0\nv 1 0 0\nv 0 1 0\nf 1 2 3\n')
        Technical(self.db).collect(dict(asset_id=model,confirmed=True))
        before='\n'.join(self.db.connection.iterdump());changes=self.db.connection.total_changes
        with patch('builtins.open',side_effect=AssertionError('no contents')),patch('ai_asset_hub_core.technical.parse',side_effect=AssertionError('no parser')),patch('ai_asset_hub_core.inference.infer',side_effect=AssertionError('no model')),patch('ai_asset_hub_core.embeddings.embed',side_effect=AssertionError('no embedding')):
            result=self.read(model)
        file=result['files'][0];self.assertEqual(file['roles'],['source']);self.assertFalse(file['technical']['stale'])
        self.assertEqual(file['technical']['observation']['value']['vertexCount'],3)
        dependencies=file['dependencies']['items'];self.assertEqual(sorted(d['status'] for d in dependencies),['blocked','blocked','present','unresolved'])
        actual=next(d for d in dependencies if d['status']=='present');self.assertEqual(actual['fileId'],self.file_id(dependency))
        self.assertEqual(result['components'][0]['kind'],'mesh');self.assertFalse(result['components'][0]['stale'])
        self.assertNotIn('PRIVATE',json.dumps(result));self.assertNotIn('secret.invalid',json.dumps(result))
        self.assertEqual('\n'.join(self.db.connection.iterdump()),before);self.assertEqual(self.db.connection.total_changes,changes)
        self.assertEqual(self.db.connection.execute('SELECT count(*) FROM analysis_jobs').fetchone()[0],0)
        self.assertEqual(self.db.connection.execute('SELECT count(*) FROM asset_embeddings').fetchone()[0],0)
        (self.source/'material.mtl').unlink()
        self.assertIn('missing',[d['status'] for d in self.read(model)['files'][0]['dependencies']['items']])
        (self.source/'mesh.obj').write_bytes(b'changed')
        stale=self.read(model);self.assertTrue(stale['files'][0]['technical']['stale']);self.assertTrue(stale['components'][0]['stale'])

    def test_multifile_roles_missing_disabled_roots_and_evidence_exclusion(self):
        audio=self.register('sound.wav',test_technical.wav());Technical(self.db).collect(dict(asset_id=audio,confirmed=True))
        evidence=self.register('PRIVATE-evidence.txt',b'private')
        other=self.base/'other';other.mkdir();(other/'dependency.txt').write_bytes(b'original dependency')
        library=LibraryService(self.db).register({'path':str(other)})['library']['id'];AssetService(self.db).scan({'library_id':library})
        dependency=self.db.connection.execute('SELECT id FROM assets WHERE library_root_id=?',(library,)).fetchone()[0]
        AssetManagement(self.db).save_composition(dict(asset_id=audio,expected_revision=0,value=dict(files=[
            dict(fileId=self.file_id(audio),role='source'),dict(fileId=self.file_id(self.id),role='preview'),
            dict(fileId=self.file_id(evidence),role='evidence'),dict(fileId=self.file_id(dependency),role='dependency')],components=[])))
        result=self.read(audio);self.assertEqual(len(result['files']),3);self.assertEqual(result['availability'],'available')
        self.assertNotIn('PRIVATE',json.dumps(result));self.assertTrue(result['evidenceExcluded'])
        legacy=McpQueries(self.db).dispatch('get_asset_files',{'asset_id':audio});self.assertEqual(len(legacy['files']),1)
        self.assertNotIn('technical',legacy['files'][0])
        (self.source/'나무.png').unlink();LibraryService(self.db).unregister({'library_id':library})
        result=self.read(audio);self.assertEqual(result['availability'],'partial')
        disabled=next(f for f in result['files'] if 'dependency' in f['roles'])
        self.assertEqual(disabled['availability'],'unavailable');self.assertNotIn('path',disabled);self.assertNotIn('ownerAssetId',disabled)
        missing=next(f for f in result['files'] if 'preview' in f['roles']);self.assertEqual(missing['availability'],'missing')

    def test_observed_components_paginate_actual_ids_and_preserve_selected_references(self):
        from ai_asset_hub_core.asset_composition import component
        model=self.register('mesh.obj',b'v 0 0 0\nv 1 0 0\nv 0 1 0\nf 1 2 3\n')
        observed=Technical(self.db).collect(dict(asset_id=model,confirmed=True))['observation'];file=self.file_id(model)
        for index in range(55):
            item=component(file,observed['inputFingerprint'],'material',['material',str(index)])
            self.db.connection.execute('INSERT INTO asset_components VALUES (?,?,?,?,?,1)',(item['id'],file,observed['inputFingerprint'],'material',json.dumps(item['locator'])))
        self.db.connection.execute('UPDATE asset_files SET sha256=? WHERE id=?',(observed['inputFingerprint'],file))
        chosen=self.db.connection.execute('SELECT id FROM asset_components ORDER BY id LIMIT 1').fetchone()[0]
        AssetManagement(self.db).save_composition(dict(asset_id=model,expected_revision=0,value=dict(files=[dict(fileId=file,role='source')],components=[chosen])))
        first=self.read(model);second=self.read(model,after_component_id=first['next_component_cursor'])
        self.assertEqual(len(first['components']),50);self.assertEqual(len(second['components']),6);self.assertIsNone(second['next_component_cursor'])
        self.assertEqual(len({c['id'] for c in first['components']+second['components']}),56)
        self.assertTrue(first['components'][0]['selected'])
        from ai_asset_hub_core.metadata_store import MetadataStore
        MetadataStore(self.db).decide(model,'composition','clear',expected_revision=1,confirmed=True)
        self.assertFalse(any(c['selected'] for c in self.read(model)['components']))
        with self.assertRaisesRegex(LibraryError,'INVALID_PARAMS'):self.read(model,after_component_id='fake')
        with self.assertRaisesRegex(LibraryError,'INVALID_PARAMS'):McpQueries(self.db).dispatch('get_asset_files',dict(asset_id=model,after_component_id=chosen))

    def test_uncollected_unknown_and_unsafe_paths_never_trigger_parsers_or_path_disclosure(self):
        result=self.read();self.assertIsNone(result['files'][0]['technical']['observation']);self.assertIsNone(result['files'][0]['technical']['stale'])
        with patch('ai_asset_hub_core.mcp_files.Path.stat',side_effect=PermissionError('PRIVATE-permission')):
            denied=self.read()['files'][0]
        self.assertEqual(denied['availability'],'unavailable');self.assertIsNone(denied['relativePath']);self.assertNotIn('path',denied)
        outside=self.base/'PRIVATE-outside';outside.write_bytes(b'private')
        self.db.connection.execute('UPDATE asset_files SET absolute_path=? WHERE asset_id=?',(str(outside),self.id))
        result=self.read();file=result['files'][0]
        self.assertEqual(file['availability'],'unavailable');self.assertIsNone(file['relativePath']);self.assertNotIn('path',file)
        self.assertEqual(result['availability'],'unavailable');self.assertNotIn('PRIVATE',json.dumps(result))
        with self.assertRaisesRegex(LibraryError,'MCP_ASSET_NOT_FOUND'):self.read(str(uuid4()))

    def test_declared_module_guid_and_private_free_text_are_not_projected_as_file_references(self):
        asset=self.register('script.py',b'import PRIVATE_module\ndef PRIVATE_function(): pass\n')
        Technical(self.db).collect(dict(asset_id=asset,confirmed=True));result=self.read(asset)
        file=result['files'][0];self.assertEqual(file['dependencies']['unresolvedDeclarationCount'],1)
        self.assertEqual(file['dependencies']['items'],[]);self.assertNotIn('PRIVATE',json.dumps(result))
        self.assertEqual(file['technical']['observation']['value']['lineCount'],2)
