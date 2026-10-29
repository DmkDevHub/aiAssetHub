import unittest
from ai_asset_hub_core.taxonomy import Category,Taxonomy,TaxonomyError,VERSION,default_taxonomy


class TaxonomyTests(unittest.TestCase):
    def test_versioned_roots_and_parent_paths_are_real_contract_data(self):
        taxonomy=default_taxonomy();contract=taxonomy.contract()
        self.assertEqual(contract['version'],VERSION)
        self.assertEqual([n['code'] for n in contract['categories'] if n['parent'] is None],[f'A{i:02}' for i in range(1,15)])
        self.assertTrue(all(1<=n['depth']<=3 for n in contract['categories']))
        self.assertEqual(taxonomy.path('걷기 모션'),['A03','A03.02','A03.02.01'])
        contract['categories'][0]['labels']['ko']='changed'
        self.assertEqual(taxonomy.resolve('2D 그래픽'),'A01')

    def test_aliases_normalization_and_unknown_values_never_guess(self):
        taxonomy=default_taxonomy()
        for value in ('walking animation',' WALKING   ANIMATION ','보행 모션','Ａ０３.０２.０１'):
            self.assertEqual(taxonomy.resolve(value),'A03.02.01')
        for value in ('knight.fbx','unknown','A15','A03.99','',None,'bad\nvalue'):
            with self.assertRaises(TaxonomyError):taxonomy.resolve(value)

    def test_primary_and_navigation_are_independent_without_duplicate_branches(self):
        taxonomy=default_taxonomy()
        result=taxonomy.assignment('Human Character Model',['A02','A02.01','A09','A09.01','A09.01','Walking Animation'],version=VERSION)
        self.assertEqual(result['primary'],'A02.01.01')
        self.assertEqual(result['navigation'],['A03.02.01','A09.01'])
        self.assertIsNone(taxonomy.assignment(version=VERSION)['primary'])
        with self.assertRaisesRegex(TaxonomyError,'VERSION_MISMATCH'):taxonomy.assignment('A02',version='old')
        with self.assertRaises(TaxonomyError):taxonomy.assignment(['A01','A02'],version=VERSION)

    def test_malformed_hierarchy_alias_collisions_and_inactive_nodes_are_rejected(self):
        root=Category('A01',None,'대분류','Root')
        invalid=[(root,root),(root,Category('A02.01','A02','자식','Child')),
                 (root,Category('A01.01','A01.01','자식','Child')),
                 (root,Category('A01.01','A01','다른 이름','Root')),
                 (root,Category('A01.01.01.01','A01','자식','Child'))]
        for nodes in invalid:
            with self.assertRaises(TaxonomyError):Taxonomy(nodes)
        inactive=Taxonomy((Category('A01',None,'대분류','Root',active=False),Category('A01.01','A01','자식','Child')))
        with self.assertRaises(TaxonomyError):inactive.path('Child')
