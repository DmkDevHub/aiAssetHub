import unittest
from ai_asset_hub_core.analysis_features import suggestions
from ai_asset_hub_core.libraries import LibraryError


class FeatureTests(unittest.TestCase):
    def test_suggestions_are_bounded_valid_codes_and_never_accept_measurements(self):
        result=suggestions({'primary':'A04','roles':['role.item'],'styles':['style.pixel'],'colors':[' red ','red']})
        self.assertEqual(result['primary'],'A04')
        self.assertEqual(result['colors'],['red'])
        for value in ({'width':100},{'primary':'A99'},{'roles':['engine.unity']},
                      {'styles':['invented']},{'roles':['role.item']*9},{'material':['x'*65]},{'colors':['red']*9},[],{'colors':['\x00']}):
            with self.subTest(value=value),self.assertRaises(LibraryError):suggestions(value)
