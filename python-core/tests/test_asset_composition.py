import unittest
from uuid import uuid4
from ai_asset_hub_core.asset_composition import component,membership
from ai_asset_hub_core.metadata_values import MetadataError


class CompositionTests(unittest.TestCase):
    def test_component_identity_pins_file_content_and_actual_parser_locator(self):
        file=str(uuid4());a=component(file,'a'*64,'animation',['animations','0'])
        self.assertEqual(a,component(file,'a'*64,'animation',['animations','0']))
        self.assertNotEqual(a['id'],component(file,'b'*64,'animation',['animations','0'])['id'])
        self.assertNotEqual(a['id'],component(file,'a'*64,'animation',['animations','1'])['id'])
        for locator in (['..'],['C:'],['/path'],[],['a\\b']):
            with self.assertRaises(MetadataError):component(file,'a'*64,'animation',locator)

    def test_memberships_use_registered_ids_without_renaming_or_merging(self):
        file,asset=str(uuid4()),str(uuid4())
        self.assertEqual(membership(asset,file,'source',known_files={file})['assetId'],asset)
        with self.assertRaises(MetadataError):membership(asset,str(uuid4()),'source',known_files={file})
        with self.assertRaises(MetadataError):membership(asset,file,'move',known_files={file})
