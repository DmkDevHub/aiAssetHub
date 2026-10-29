import unittest
from ai_asset_hub_core.classification_axes import default_facets,VERSION
from ai_asset_hub_core.taxonomy import TaxonomyError


class FacetTests(unittest.TestCase):
    def test_independent_axes_multivalue_unknown_and_language_aliases(self):
        facets=default_facets();result=facets.assignment({'style':['픽셀아트',' PIXEL ART ','Cartoon'],'engine':['Unity']},version=VERSION)
        self.assertEqual(result['values']['style'],['style.cartoon','style.pixel']);self.assertEqual(result['values']['role'],[])
        self.assertEqual(result['values']['engine'],['engine.unity'])
        for value in ({'role':['Pixel Art']},{'dimension':['4D']},{'unknown':[]}):
            with self.assertRaises(TaxonomyError):facets.assignment(value,version=VERSION)
        with self.assertRaises(TaxonomyError):facets.assignment({},version='old')

    def test_retire_used_terms_requires_confirmation_and_preserves_old_version(self):
        old=default_facets()
        with self.assertRaisesRegex(TaxonomyError,'IN_USE'):old.retire('style.pixel',new_version='v2',used=True)
        with self.assertRaises(TaxonomyError):old.retire('style.pixel',new_version='v2',used=True,confirmed=True,replacement='engine.unity')
        new=old.retire('style.pixel',new_version='v2',used=True,confirmed=True,replacement='style.cartoon')
        self.assertEqual(old.assignment({'style':['Pixel Art']},version=VERSION)['values']['style'],['style.pixel'])
        with self.assertRaisesRegex(TaxonomyError,'UNAVAILABLE'):new.assignment({'style':['Pixel Art']},version='v2')
        self.assertEqual(new.index['style.pixel'].replacement,'style.cartoon')
