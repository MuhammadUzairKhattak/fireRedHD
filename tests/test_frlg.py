import os
import sys
import unittest


ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, os.path.join(ROOT, 'converter'))

from frlg import FrlgRepo, load_config, validate_source


class FrlgSourceTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.repo_root = os.path.join(ROOT, 'external', 'pokefirered')
        if not os.path.isdir(cls.repo_root):
            raise unittest.SkipTest('external/pokefirered is not installed')

    def test_prototype_inventory(self):
        result = validate_source(self.repo_root)

        self.assertEqual(result['profile'], 'firered_rev1_us_english')
        self.assertEqual(result['maps']['PalletTown']['size'], [24, 20])
        self.assertEqual(result['maps']['Route1']['size'], [24, 40])

    def test_tilesets_are_namespaced(self):
        repo = FrlgRepo(self.repo_root)
        for name in load_config()['prototype_maps']:
            source = repo.map_json(name)
            layout = repo.layouts[source['layout']]
            self.assertTrue(layout['primary_tileset'].startswith('frlg:'))
            self.assertTrue(layout['secondary_tileset'].startswith('frlg:'))
            repo.load_tileset(layout['primary_tileset'])
            repo.load_tileset(layout['secondary_tileset'])


if __name__ == '__main__':
    unittest.main()
