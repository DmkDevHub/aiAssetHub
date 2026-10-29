import unittest
from uuid import uuid4
from ai_asset_hub_core.metadata_values import Claim,FieldState,MetadataError


def claim(source,value):return Claim(str(uuid4()),source,value,'test-owned evidence','fixture.v1')


class MetadataValueTests(unittest.TestCase):
    def test_reanalysis_does_not_replace_user_confirmation_or_clear(self):
        state=FieldState();old=claim('ai','old');state.propose(old)
        self.assertEqual(state.selected()['status'],'proposed')
        state.decide('set',value='user',confirmed=True,expected_revision=0)
        new=claim('ai','new');state.propose(new);self.assertEqual(state.selected()['value'],'user')
        state.decide('clear',confirmed=True,expected_revision=1);state.propose(claim('ai','third'))
        self.assertEqual(state.selected()['status'],'cleared');self.assertIsNone(state.selected()['value'])
        state.decide('adopt',claim_id=new.id,confirmed=True,expected_revision=2)
        self.assertEqual(state.selected()['value'],'new');self.assertEqual(len(state.history()),3)

    def test_observations_conflicts_invalid_values_and_history_are_isolated(self):
        state=FieldState();state.propose(claim('parser',{'width':32}));state.propose(claim('ai',{'width':100}))
        self.assertEqual(state.selected()['value'],{'width':32})
        with self.assertRaises(MetadataError):state.decide('set',value='x',confirmed=False,expected_revision=0)
        with self.assertRaisesRegex(MetadataError,'CONFLICT'):state.decide('clear',confirmed=True,expected_revision=1)
        with self.assertRaises(MetadataError):state.propose(claim('ai',float('nan')))
        with self.assertRaises(MetadataError):state.decide('adopt',claim_id=str(uuid4()),confirmed=True,expected_revision=0)
        self.assertEqual(state.revision,0);self.assertEqual(state.history(),[])
        state.decide('set',value={'tags':['user']},confirmed=True,expected_revision=0)
        history=state.history();history[0]['after']['value']['tags'].append('changed')
        self.assertEqual(state.selected()['value'],{'tags':['user']})
