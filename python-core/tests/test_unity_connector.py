from datetime import datetime,timezone,timedelta
import json
from unittest.mock import patch
import unittest
from uuid import uuid4
import test_annotations
from ai_asset_hub_core.unity_connector import EditorMailbox,write_private
from ai_asset_hub_core.session_file import private
from ai_asset_hub_core.libraries import LibraryError


class UnityConnectorTests(unittest.TestCase):
    setUp=test_annotations.AnnotationTests.setUp
    tearDown=test_annotations.AnnotationTests.tearDown

    def connector(self):
        project=self.base/'project';(project/'Assets').mkdir(parents=True);(project/'ProjectSettings').mkdir()
        (project/'ProjectSettings/ProjectVersion.txt').write_text('m_EditorVersion: 6000.6.8f1\n')
        directory=project/'Library/AIAssetHub';directory.mkdir(parents=True);private(directory,True)
        state=dict(protocol=1,pid=123,session=str(uuid4()),token='a'*64,project=str(project),editorVersion='6000.6.8f1',
            updatedAt=datetime.now(timezone.utc).isoformat(),scene='',sceneHandle='1',sceneDirty=False,playing=False,compiling=False,batchMode=True)
        write_private(directory/'connector.json',state)
        return project,directory,state,EditorMailbox(self.db,[project])

    def test_allowed_live_project_and_private_ping_redaction(self):
        project,directory,state,mailbox=self.connector()
        before='\n'.join(self.db.connection.iterdump())
        identifier,session=mailbox.send(str(project),'ping')
        request=json.loads((directory/(identifier+'.request.json')).read_text())
        self.assertEqual(request['token'],state['token']);self.assertEqual(request['session'],session)
        self.assertIsNone(mailbox.result(str(project),identifier,session))
        write_private(directory/(identifier+'.result.json'),dict(id=identifier,session=session,token=state['token'],status='succeeded',target=state))
        self.assertEqual(mailbox.result(str(project),identifier,session),dict(status='succeeded',errorCode=None))
        self.assertNotIn('token',mailbox.public(state));self.assertNotIn('session',mailbox.public(state))
        self.assertEqual('\n'.join(self.db.connection.iterdump()),before)

    def test_untrusted_stale_tampered_session_and_result_fail_closed(self):
        project,directory,state,mailbox=self.connector()
        with patch('pathlib.Path.stat',side_effect=AssertionError('no arbitrary probe')):
            with self.assertRaisesRegex(LibraryError,'UNITY_PROJECT_NOT_ALLOWED'):EditorMailbox(self.db,[]).connect(str(project))
        identifier,session=mailbox.send(str(project),'ping')
        write_private(directory/(identifier+'.result.json'),dict(id=identifier,session=session,token='wrong',status='succeeded'))
        with self.assertRaisesRegex(LibraryError,'UNITY_INVALID_RESULT'):mailbox.result(str(project),identifier,session)
        (directory/'connector.json').unlink();state['updatedAt']=(datetime.now(timezone.utc)-timedelta(seconds=12)).isoformat();write_private(directory/'connector.json',state)
        with self.assertRaisesRegex(LibraryError,'UNITY_NOT_CONNECTED'):mailbox.connect(str(project))
        (directory/'connector.json').unlink();state.update(updatedAt=datetime.now(timezone.utc).isoformat(),session=str(uuid4()));write_private(directory/'connector.json',state)
        with self.assertRaisesRegex(LibraryError,'UNITY_SESSION_CHANGED'):mailbox.result(str(project),identifier,session)

    def test_linked_mailbox_and_oversized_descriptor_rejected(self):
        project,directory,state,mailbox=self.connector()
        with patch('ai_asset_hub_core.session_file.no_links',side_effect=ValueError()):
            with self.assertRaisesRegex(LibraryError,'UNITY_NOT_CONNECTED'):mailbox.connect(str(project))
        (directory/'connector.json').write_text('x'*16385)
        with self.assertRaisesRegex(LibraryError,'UNITY_NOT_CONNECTED'):mailbox.connect(str(project))

    def test_desktop_allowlist_persistence_duplicate_and_revocation(self):
        from ai_asset_hub_core.unity_targets import UnityTargets
        from ai_asset_hub_core.application import CoreApplication
        project,directory,state,_=self.connector();targets=UnityTargets(self.db)
        self.assertEqual(targets.list({})['items'],[])
        with self.assertRaisesRegex(LibraryError,'INVALID_PARAMS'):targets.save(dict(project_path=str(project),confirmed=False))
        registered=targets.save(dict(project_path=str(project),confirmed=True))
        self.assertEqual(targets.save(dict(project_path=str(project),confirmed=True)),registered)
        self.assertTrue(targets.list({})['items'][0]['connected']);self.assertNotIn('token',json.dumps(targets.list({})))
        app=CoreApplication(self.db)
        response=app.handle(dict(request_id=str(uuid4()),method='unity.targets',params={}))
        self.assertTrue(response['ok']);self.assertEqual(len(response['data']['items']),1)
        targets.remove(dict(target_id=registered['id'],confirmed=True))
        self.assertEqual(targets.list({})['items'],[])
        with self.assertRaisesRegex(LibraryError,'UNITY_PROJECT_NOT_ALLOWED'):targets.mailbox().connect(str(project))
        self.assertTrue((directory/'connector.json').is_file());self.assertEqual((self.source/'나무.png').read_bytes(),b'original')
