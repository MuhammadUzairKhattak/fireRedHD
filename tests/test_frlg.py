import os
import sys
import tempfile
import unittest


ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, os.path.join(ROOT, 'converter'))
sys.path.insert(0, os.path.join(ROOT, 'b2tools'))

from frlg import FrlgRepo, load_config, validate_source
from gba import Repo


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


class FrlgMetatileLayoutTest(unittest.TestCase):
    """FireRed's tileset layout differs from pokeruby's; the shared reader must honour both."""

    @classmethod
    def setUpClass(cls):
        cls.repo_root = os.path.join(ROOT, 'external', 'pokefirered')
        if not os.path.isdir(cls.repo_root):
            raise unittest.SkipTest('external/pokefirered is not installed')

    def test_frlg_splits_metatiles_at_640(self):
        # pokefirered include/fieldmap.h: NUM_METATILES_IN_PRIMARY 640 (pokeruby uses 512)
        self.assertEqual(FrlgRepo.METATILE_BOUNDARY, 640)
        self.assertEqual(FrlgRepo.METATILE_BOUNDARY, Repo.METATILE_BOUNDARY + 128)

    def test_pokeruby_defaults_unchanged(self):
        # regression for the gba.py generalisation: the shared Repo keeps Hoenn's numbers
        self.assertEqual(Repo.METATILE_BOUNDARY, 512)
        self.assertEqual(Repo.TILE_BOUNDARY, 512)
        self.assertEqual(Repo.PAL_PRIMARY, 6)
        self.assertEqual(Repo.ATTR_DTYPE, '<u2')

    def test_secondary_metatile_behaviour_uses_640_split(self):
        from gba import MetatileRenderer
        repo = FrlgRepo(self.repo_root)
        layout = repo.layouts[repo.map_json('PalletTown')['layout']]
        mr = MetatileRenderer(repo, layout['primary_tileset'], layout['secondary_tileset'])
        # 0x2a3 is PalletTown's warp door (secondary, id >= 640); behaviour MB_WARP_DOOR 0x69
        self.assertEqual(mr.behavior(0x2a3), 0x69)
        # 0x00d is General's tall grass (primary); behaviour MB_TALL_GRASS 0x02
        self.assertEqual(mr.behavior(0x00d), 0x02)


class FrlgClassificationTest(unittest.TestCase):
    """The FireRed table must cover every metatile the prototype maps place, with no Hoenn id leaking in."""

    @classmethod
    def setUpClass(cls):
        cls.repo_root = os.path.join(ROOT, 'external', 'pokefirered')
        if not os.path.isdir(cls.repo_root):
            raise unittest.SkipTest('external/pokefirered is not installed')

    def test_every_used_metatile_is_classified(self):
        import frlg_classify
        maps = load_config()['prototype_maps']
        labels, missing = frlg_classify.build_labels(os.path.abspath(self.repo_root), maps)
        self.assertEqual(missing, [], f'unclassified FRLG metatiles: {missing}')
        self.assertTrue(any(t.startswith('frlg:') for t in labels), 'labels must be keyed by namespaced tilesets')

    def test_label_files_are_current(self):
        import frlg_classify
        self.assertEqual(frlg_classify.main([self.repo_root, '--check']), 0,
                         'data/labels/frlg_*.json is stale: re-run frlg_classify.py')

    def test_clean_plans(self):
        import frlg_plan
        repo = FrlgRepo(os.path.abspath(self.repo_root))
        table = frlg_plan.load_table()
        for name in load_config()['prototype_maps']:
            plan = frlg_plan.plan_map(repo, table, name)
            flat = {t for row in plan['tiles'] for t in row}
            self.assertNotIn('unknown', flat, f'{name}: has unknown tiles')
            self.assertNotIn('blocked', flat, f'{name}: has blocked (unlabelled solid) tiles')
            self.assertEqual(plan['unclassified'], {}, f'{name}: unclassified metatiles remain')
        # Pallet Town has three doors (two houses and Oak's Lab); Route 1 is open field
        pt = frlg_plan.plan_map(repo, table, 'PalletTown')
        self.assertEqual(len(pt['buildings']), 3)
        self.assertEqual({b['kind'] for b in pt['buildings']}, {'house', 'lab'})
        r1 = frlg_plan.plan_map(repo, table, 'Route1')
        self.assertEqual(r1['buildings'], [])
        self.assertIn('tall_grass', {t for row in r1['tiles'] for t in row})


class KantoWorldTest(unittest.TestCase):
    """b2tools/kanto_world.py lays the clean Kanto plans onto one global grid (the build step parallel to
    world.compose) - without touching Hoenn's build path. Plans are generated fresh into a temp dir, so this does
    not depend on the gitignored work/kanto/plans artifacts."""

    @classmethod
    def setUpClass(cls):
        cls.repo_root = os.path.join(ROOT, 'external', 'pokefirered')
        if not os.path.isdir(cls.repo_root):
            raise unittest.SkipTest('external/pokefirered is not installed')
        import frlg_plan
        repo = FrlgRepo(cls.repo_root)
        table = frlg_plan.load_table()
        cls.tmp = tempfile.mkdtemp()
        import json
        for name in load_config()['prototype_maps']:
            plan = frlg_plan.plan_map(repo, table, name)
            json.dump(plan, open(os.path.join(cls.tmp, f'{name}.json'), 'w'))

    def test_map_const_to_plan_name(self):
        import kanto_world
        self.assertEqual(kanto_world._plan_name('MAP_PALLET_TOWN'), 'PalletTown')
        self.assertEqual(kanto_world._plan_name('MAP_ROUTE1'), 'Route1')
        self.assertEqual(kanto_world._plan_name('MAP_VIRIDIAN_CITY'), 'ViridianCity')

    def test_layout_is_connection_consistent(self):
        import kanto_world
        doc = kanto_world.load_doc()
        for name in doc['maps']:                                   # attach sizes/connections as build() does
            p = kanto_world.json.load(open(os.path.join(self.tmp, f'{name}.json')))
            doc['maps'][name]['size'] = p['size']
            doc['maps'][name]['connections'] = p.get('connections') or []
        self.assertEqual(kanto_world.check_layout(doc), [], 'Route1 north of Pallet Town should be consistent')

    def test_bad_placement_is_caught(self):
        import copy
        import kanto_world
        doc = kanto_world.load_doc()
        for name in doc['maps']:
            p = kanto_world.json.load(open(os.path.join(self.tmp, f'{name}.json')))
            doc['maps'][name]['size'] = p['size']
            doc['maps'][name]['connections'] = p.get('connections') or []
        bad = copy.deepcopy(doc)
        bad['layout']['PalletTown']['tile_z'] += 5                 # break the Route1.down <-> PalletTown.up abut
        self.assertTrue(kanto_world.check_layout(bad), 'a shifted map should fail the connection check')

    def test_compose_and_build(self):
        import json
        import kanto_world
        world, trees, maps = kanto_world.compose(kanto_world.load_doc(),
                                                 {n: os.path.join(self.tmp, f'{n}.json') for n in ('PalletTown', 'Route1')})
        self.assertEqual(set(maps), {'PalletTown', 'Route1'})
        self.assertEqual(len(world), 24 * 20 + 24 * 40)           # every map tile placed, no overlap (compose asserts)
        out = os.path.join(self.tmp, 'world')
        self.assertEqual(kanto_world.build(out_dir=out, plan_dir=self.tmp), 0)
        doc = json.load(open(os.path.join(out, 'compose_report.json')))
        self.assertTrue(doc['validation']['ok'])
        self.assertEqual(doc['maps']['PalletTown']['kind'], 'town')
        self.assertEqual(doc['maps']['Route1']['kind'], 'route')
        self.assertEqual(doc['maps']['PalletTown']['buildings'], ['house', 'house', 'lab'])
        self.assertGreaterEqual(len(doc['cells_built']), 1)


class KantoBuildCellTest(unittest.TestCase):
    """kanto_world --cells runs Black 2's real b2tools/world.build_cell over the composed Kanto cells (reused, not
    edited) to prove the plan class vocabulary feeds the Gen 5 geometry builder unchanged. Needs `import world`, which
    reads the pokebw2 extract (external/pokebw2/.../ov036.bin) - present and importable only under WSL, so this skips
    on Windows."""

    @classmethod
    def setUpClass(cls):
        sys.path.insert(0, os.path.join(ROOT, 'b2tools'))
        try:
            import world                                    # noqa: F401  (the extract resolves here)
        except Exception as e:
            raise unittest.SkipTest(f'b2tools/world not importable (run under WSL): {e}')
        cls.repo_root = os.path.join(ROOT, 'external', 'pokefirered')
        if not os.path.isdir(cls.repo_root):
            raise unittest.SkipTest('external/pokefirered is not installed')
        import frlg_plan
        repo = FrlgRepo(cls.repo_root)
        table = frlg_plan.load_table()
        cls.tmp = tempfile.mkdtemp()
        import json
        for name in load_config()['prototype_maps']:
            json.dump(frlg_plan.plan_map(repo, table, name), open(os.path.join(cls.tmp, f'{name}.json'), 'w'))

    def test_build_cell_makes_kanto_geometry(self):
        import json
        import kanto_world
        out = os.path.join(self.tmp, 'cells')
        self.assertEqual(kanto_world.build_cells(out_dir=out, plan_dir=self.tmp), 0)
        doc = json.load(open(os.path.join(out, 'cells_geom.json')))
        self.assertGreaterEqual(len(doc['cells']), 1)
        for c, v in doc['cells'].items():
            self.assertGreater(v['tris'], 0, f'cell {c}: no triangles')
            self.assertGreater(v['materials'], 0, f'cell {c}: no materials')

    def test_write_cells_emits_dae(self):
        """world.write_cell (reused unchanged) turns a composed Kanto cell into a real Black 2 chunk payload."""
        import json
        import kanto_world
        out = os.path.join(self.tmp, 'chunks')
        self.assertEqual(kanto_world.write_cells(out_dir=out, plan_dir=self.tmp), 0)
        doc = json.load(open(os.path.join(kanto_world.OUT_DIR, 'cells_dae.json')))
        self.assertGreaterEqual(len(doc['cells']), 1)
        for c in doc['cells']:
            d = os.path.join(out, c)
            for name in ('terrain.dae', 'collision.per', 'placements.bin', 'chunk.json'):
                self.assertTrue(os.path.exists(os.path.join(d, name)), f'cell {c}: missing {name}')
        self.assertGreater(min(v['dae_bytes'] for v in doc['cells'].values()), 0, 'empty .dae')

    def test_package_writes_loadable_manifest(self):
        """kanto_world.package() wires the composed maps through world.zone_rects/map_events/make_put (reused) and
        writes the ROM-shaped world.json manifest that patches/hoenn_world.apply() consumes."""
        import json
        import kanto_world
        out = os.path.join(self.tmp, 'chunks_world')
        self.assertEqual(kanto_world.package(out_dir=out, plan_dir=self.tmp), 0)
        man = json.load(open(os.path.join(kanto_world.OUT_DIR, 'world.json')))
        for key in ('matrix', 'width', 'height', 'area', 'cells', 'zones', 'standalone'):
            self.assertIn(key, man)
        cfg = kanto_world.load_doc()
        self.assertEqual(len(man['cells']), 12)                        # 2 built + 10 forest-ring cells
        for c in man['cells']:
            self.assertTrue(os.path.exists(os.path.join(out, f"{c['cx']:02d}_{c['cz']:02d}", 'terrain.dae')))
        zones = man['zones']
        self.assertEqual(set(zones), {str(cfg['maps']['PalletTown']['zone']), str(cfg['maps']['Route1']['zone'])})
        for zid, z in zones.items():
            self.assertEqual(len(z['fly']), 2)                         # a fly point (world x, z) chosen from walkable tiles
            self.assertTrue(z['place'] and z['kind'] in ('town', 'route'))
        self.assertTrue(any(len(z['maps']) == 1 for z in zones.values()))


if __name__ == '__main__':
    unittest.main()
