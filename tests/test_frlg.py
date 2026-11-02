import json
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

    def test_no_solid_tile_is_invisible(self):
        """world.py's rule: a solid (non-walkable) tile must be drawn by some module, or it is an invisible wall the
        player bumps into (this is what made the Kanto signs and door gaps invisible). Every class a prototype plan
        marks solid must have a geometry owner. DRAWN mirrors the terrain modules' CLASSES plus world.build_cell's core
        classes and terrain/kanto_features.py; when a new solid class appears with no owner here, either draw it (a
        module) or reclassify it - never leave it invisible. Pure-python (frlg_plan only), so it runs on Windows."""
        import frlg_plan
        GROUND = {'sand', 'ash_grass', 'long_grass', 'bike_path', 'bridge', 'fence', 'wall', 'bush', 'rock', 'prop'}
        HEIGHTS = {'cliff', 'cliff_top', 'stairs', 'ledge_e', 'ledge_w', 'ledge_n', 'ledge_s', 'ledge_cap',
                   'mountain', 'cave_entrance', 'cracked_floor', 'mud'}
        WATER = {'water', 'deep_water', 'current_n', 'current_s', 'current_e', 'current_w', 'waterfall', 'puddle', 'water_edge'}
        CORE = {'grass', 'path', 'tall_grass', 'flowers', 'lava', 'sand_patch', 'tree',
                'tree_top_l', 'tree_top_r', 'tree_bot', 'tree_tip'}
        KANTO = {'building', 'building_roof', 'door', 'sign'}
        drawn = GROUND | HEIGHTS | WATER | CORE | KANTO
        repo = FrlgRepo(os.path.abspath(self.repo_root))
        table = frlg_plan.load_table()
        for name in load_config()['prototype_maps']:
            plan = frlg_plan.plan_map(repo, table, name)
            for y in range(plan['size'][1]):
                for cls, walk in zip(plan['tiles'][y], plan['walkable'][y]):
                    if not walk:
                        self.assertTrue(cls in drawn or cls.startswith('other:'),
                                        f'{name}: solid tile class {cls!r} has no geometry owner (invisible wall)')


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
        cfg = kanto_world.load_doc()
        names = list(cfg['maps'])
        plans = {n: os.path.join(self.tmp, f'{n}.json') for n in names}
        sizes = {n: json.load(open(plans[n]))['size'] for n in names}
        world, trees, maps = kanto_world.compose(cfg, plans)
        self.assertEqual(set(maps), set(names))
        self.assertEqual(len(world), sum(w * h for w, h in sizes.values()))   # every map tile placed, no overlap (compose asserts)
        out = os.path.join(self.tmp, 'world')
        self.assertEqual(kanto_world.build(out_dir=out, plan_dir=self.tmp), 0)
        doc = json.load(open(os.path.join(out, 'compose_report.json')))
        self.assertTrue(doc['validation']['ok'])
        self.assertEqual(doc['maps']['PalletTown']['kind'], 'town')
        self.assertEqual(doc['maps']['Route1']['kind'], 'route')
        self.assertEqual(doc['maps']['PalletTown']['buildings'], ['house', 'house', 'lab'])
        self.assertGreaterEqual(len(doc['cells_built']), 1)

    def test_no_invisible_tree_wall(self):
        """compose() must never leave a solid tree tile without a tree model over it. FireRed's tree art does not form
        the clean tree_top_l/tree_top_r pairs the old detector required, so uncovered solid tree tiles (the route
        borders, cluster edges) were invisible walls; frlg_plan now covers every 2x2 block and compose opens the rest."""
        import kanto_world
        cfg = kanto_world.load_doc()
        plans = {n: os.path.join(self.tmp, f'{n}.json') for n in cfg['maps']}
        world, trees, maps = kanto_world.compose(cfg, plans)
        covered = {(x + dx, z + dz) for (x, z) in trees for dx in (0, 1) for dz in (0, 1)}
        for k, (name, c, walk) in world.items():
            self.assertFalse(not walk and c in kanto_world.TREE_CLASSES and k not in covered,
                             f'{name}: solid tree tile {k} has no tree model (invisible wall)')


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
        self.assertGreaterEqual(len(man['cells']), 1)                    # built map cells + the forest ring
        for c in man['cells']:
            self.assertTrue(os.path.exists(os.path.join(out, f"{c['cx']:02d}_{c['cz']:02d}", 'terrain.dae')))
        zones = man['zones']
        self.assertEqual(set(zones), {str(m['zone']) for m in cfg['maps'].values()})
        for zid, z in zones.items():
            self.assertEqual(len(z['fly']), 2)                         # a fly point (world x, z) chosen from walkable tiles
            self.assertTrue(z['place'] and z['kind'] in ('town', 'route'))
        self.assertTrue(any(len(z['maps']) == 1 for z in zones.values()))

    def test_package_places_black2_building_models(self):
        """data/kanto_world.json 'buildings' names a Black 2 native model per footprint; package() must place it (a cell
        gains placement bytes) and mark those tiles in kanto_features.MODELED so the placeholder box is suppressed."""
        import kanto_world
        from terrain import kanto_features
        out = os.path.join(self.tmp, 'bld_world')
        self.assertEqual(kanto_world.package(out_dir=out, plan_dir=self.tmp), 0)
        self.assertTrue(kanto_features.MODELED,
                        'package() marked no building footprint to suppress the box for (buildings config not read?)')
        sizes = [os.path.getsize(os.path.join(out, d, 'placements.bin'))
                 for d in os.listdir(out) if os.path.exists(os.path.join(out, d, 'placements.bin'))]
        self.assertTrue(sizes and max(sizes) > min(sizes),
                        'no Black 2 building model placement was written to any cell')

    def test_package_manifest_is_injector_ready(self):
        """The manifest patches/kanto_world.apply() consumes is a valid injection: the cell chunks are contiguous from
        first_chunk (the patch appends them on Black 2's own a/0/0/8 count), every cell sits on the WxH matrix grid and
        names a zone the manifest defines, and the matrix/area match the config's region base."""
        import json
        import kanto_world
        out = os.path.join(self.tmp, 'ready_world')
        self.assertEqual(kanto_world.package(out_dir=out, plan_dir=self.tmp), 0)
        man = json.load(open(os.path.join(kanto_world.OUT_DIR, 'world.json')))
        cfg = kanto_world.load_doc()
        chunks = sorted(c['chunk'] for c in man['cells'])
        self.assertEqual(chunks, list(range(cfg['first_chunk'], cfg['first_chunk'] + len(chunks))),
                         'cell chunks must be contiguous from first_chunk (patch appends on Unova\'s count)')
        self.assertEqual(man['matrix'], cfg['matrix'])
        self.assertEqual(man['area'], cfg['area'])
        W, H = man['width'], man['height']
        for c in man['cells']:
            self.assertTrue(0 <= c['cx'] < W and 0 <= c['cz'] < H, f"cell {c['cx']},{c['cz']} off the {W}x{H} matrix")
            self.assertIn(str(c['zone']), man['zones'])

    def test_region_base_ids_match_black2(self):
        """data/kanto_world.json's injection ids are FireRedHD's region base, measured off Black 2's build files (read
        only): the first Kanto chunk and the Kanto matrix equal a/0/0/8's and a/0/0/9's own counts - the exact invariant
        patches/kanto_world.apply() asserts - and the zone slots Pallet Town / Route 1 take are real, distinct header
        slots. Needs the pokebw2 build files, so it skips on Windows and when they are absent."""
        import narcio
        import zoneheaders
        import kanto_world
        files = os.path.join(ROOT, 'external', 'pokebw2', 'build', 'b2_us', 'files')
        if not os.path.isdir(files):
            raise unittest.SkipTest(f'Black 2 build files not present: {files}')
        cfg = kanto_world.load_doc()
        self.assertEqual(len(narcio.load(files, 8)), cfg['first_chunk'],
                         'first_chunk must be Black 2\'s a/0/0/8 chunk count (where Kanto appends)')
        self.assertEqual(len(narcio.load(files, 9)), cfg['matrix'],
                         'matrix must be Black 2\'s a/0/0/9 matrix count (the Kanto matrix id)')
        headers, _ = zoneheaders.load(files)
        slots = [m['zone'] for m in cfg['maps'].values()]
        self.assertEqual(len(set(slots)), len(slots), 'zone slots must be distinct')
        for z in slots:
            self.assertTrue(0 <= z < len(headers), f'zone {z} is not a real header slot (Black 2 has {len(headers)})')

    @staticmethod
    def _load_patch(name):
        import importlib.util
        p = os.path.join(ROOT, 'b2tools', 'patches', f'{name}.py')
        spec = importlib.util.spec_from_file_location(name, p)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod

    def test_kanto_door_bridge_preconditions(self):
        """patches/kanto_door.py (the a4.6 reachability bridge) rewires an entry door into Pallet Town's zone slot.
        Its preconditions, read off Black 2's build files (no write): the Kanto zone is one data/kanto_world.json
        installs, it differs from the entry zone, and the entry zone has a warp to repurpose. Skips with the class."""
        import narcio
        import zoneheaders
        from zones import parse_entities
        import kanto_world
        files = os.path.join(ROOT, 'external', 'pokebw2', 'build', 'b2_us', 'files')
        if not os.path.isdir(files):
            raise unittest.SkipTest(f'Black 2 build files not present: {files}')
        kd = self._load_patch('kanto_door')
        cfg = kanto_world.load_doc()
        self.assertNotEqual(kd.KANTO_ZONE, kd.ENTRY_ZONE, 'entry and destination zones must differ')
        self.assertIn(kd.KANTO_ZONE, {m['zone'] for m in cfg['maps'].values()},
                      'the bridge leads to a zone the Kanto world does not install')
        headers, _ = zoneheaders.load(files)
        ents = narcio.load(files, 126)
        self.assertTrue(0 <= kd.ENTRY_ZONE < len(headers), 'entry zone is not a real header slot')
        e, _ = parse_entities(ents[headers[kd.ENTRY_ZONE]['entities']])
        self.assertTrue(e['warps'], f'entry zone {kd.ENTRY_ZONE} has no warp {kd.ENTRY_WARP} to repurpose')


class KantoBuildingGeometryTest(unittest.TestCase):
    """b2tools/terrain/kanto_features.py is the Kanto-only feature module (appended to world.FEATURES at runtime, never
    added to Hoenn's data/terrain_modules.json) that draws the plan's 'building'/'building_roof'/'door' tiles as one
    merged massing per footprint and gives solid 'sign' tiles a visible signpost - none of which a Hoenn module draws.
    It uses only build_chunk primitives, so it runs on Windows."""

    def setUp(self):
        from terrain import kanto_features
        kanto_features.MODELED = set()          # order-independent: package() tests may have left real footprints here

    @staticmethod
    def _cell(grid):
        import build_chunk as bc
        class Cell:
            cx = cz = 0
            X = Z = 0
        c = Cell()
        c.bc = bc
        c.get = lambda tx, tz: grid.get((tx, tz))
        return c

    def test_footprint_merges_interior_seams(self):
        from dae import Model
        from terrain import kanto_features
        grid = {(1, 1): ('PalletTown', 'building', False),
                (1, 2): ('PalletTown', 'building_roof', False),
                (5, 5): ('PalletTown', 'grass', True)}
        m = Model('test')
        kanto_features.draw(m, self._cell(grid))
        # a two-tile footprint shares one edge: walls go on the 6 outer faces only (not 8), each double-sided (2 quads
        # x 2 tris = 4 tris/face); the roof slab (top + 6 parapet faces) is a distinct stone material.
        self.assertEqual(len(m.tris['t02_kabe01']), 6 * 4,
                         'interior seam: adjacent building tiles must not both wall the shared edge')
        self.assertIn('iwa01', m.tris, 'the massing drew no roof slab')
        # collision defers to build_cell's default, so a (solid) building tile stays a wall
        self.assertIsNone(kanto_features.collision('building', grid[(1, 1)], self._cell(grid)))

    def test_door_tile_fills_the_footprint(self):
        from dae import Model
        from terrain import kanto_features
        m = Model('test')
        kanto_features.draw(m, self._cell({(3, 3): ('ViridianCity', 'door', False)}))
        self.assertIn('t02_kabe01', m.tris, 'a door tile left a hole in the building instead of closing it')

    def test_sign_draws_a_visible_signpost(self):
        from dae import Model
        from terrain import kanto_features
        grid = {(4, 4): ('ViridianCity', 'sign', False)}
        m = Model('test')
        kanto_features.draw(m, self._cell(grid))
        self.assertIn('ki02c', m.tris, 'a solid sign tile rendered as nothing (invisible wall)')
        self.assertIsNone(kanto_features.collision('sign', grid[(4, 4)], self._cell(grid)))

    def test_plain_tiles_draw_nothing(self):
        from dae import Model
        from terrain import kanto_features
        m = Model('test')
        kanto_features.draw(m, self._cell({(0, 0): ('PalletTown', 'grass', True)}))
        self.assertFalse(m.tris, 'a grass tile must not gain building or sign geometry')

    def test_modeled_footprint_suppresses_the_box(self):
        """When map_events places a real Black 2 building model on a footprint (data/kanto_world.json 'buildings'),
        kanto_features.MODELED holds those world tiles and the placeholder box is suppressed - the model is the building."""
        from dae import Model
        from terrain import kanto_features
        grid = {(1, 1): ('PalletTown', 'building', False),
                (1, 2): ('PalletTown', 'building_roof', False)}
        saved = kanto_features.MODELED
        try:
            kanto_features.MODELED = {(1, 1), (1, 2)}          # _cell maps world tile == (tx, tz)
            m = Model('test')
            kanto_features.draw(m, self._cell(grid))
            self.assertFalse(m.tris, 'a footprint covered by a real building model must not also draw a placeholder box')
        finally:
            kanto_features.MODELED = saved


class KantoEscapeRopeTest(unittest.TestCase):
    """b2tools/patches/kanto_escape_rope.py is a thin adapter that enables the generic engine patch
    escape_rope.py on the Kanto build without editing it: escape_rope reads the region's overworld matrix from
    HOENN_WORLD_DIR, so the adapter points it at the packaged Kanto world (KANTO_WORLD_DIR) and delegates. It
    compiles no C and touches no shared ITCM arena, so it imports and checks on Windows."""

    PATCHES = os.path.join(ROOT, 'b2tools', 'patches')

    def _import(self):
        if self.PATCHES not in sys.path:
            sys.path.insert(0, self.PATCHES)
        import kanto_escape_rope
        import escape_rope
        return kanto_escape_rope, escape_rope

    def test_adapter_points_escape_rope_at_kanto_world(self):
        kanto_escape_rope, escape_rope = self._import()
        seen = {}
        real, real_env = escape_rope.apply_code, os.environ.get('HOENN_WORLD_DIR')

        def fake_apply_code(code):
            seen['code'] = code
            seen['world'] = os.environ.get('HOENN_WORLD_DIR')
            return 'escape_rope: GetIsZoneMatrix0 = Hoenn outdoor matrices 416..416'

        escape_rope.apply_code = fake_apply_code
        os.environ['KANTO_WORLD_DIR'] = '/tmp/kanworld'
        try:
            msg = kanto_escape_rope.apply_code('/tmp/code')
        finally:
            escape_rope.apply_code = real
            if real_env is None:
                os.environ.pop('HOENN_WORLD_DIR', None)
            else:
                os.environ['HOENN_WORLD_DIR'] = real_env
        self.assertEqual(seen['code'], '/tmp/code', 'adapter did not pass the code dir through')
        self.assertEqual(seen['world'], '/tmp/kanworld', 'adapter did not aim escape_rope at KANTO_WORLD_DIR')
        self.assertIn('Kanto', msg, 'adapter left the Hoenn wording in its report')

    def test_kanto_matrix_encoding_matches_escape_rope(self):
        # Kanto's world.json matrix 416, no standalone maps yet: the same 12 bytes escape_rope writes into
        # GetIsZoneMatrix0 (0x02018d04), so the escape-rope exit fix is valid on the prototype.
        import struct
        m, n = 416, 0
        self.assertTrue(255 < m <= 510 and n + 1 <= 255, 'Kanto matrix outside escape_rope\'s accepted range')
        new = struct.pack('<6H', 0x3800 | 255, 0x3800 | (m - 255), 0x2800 | (n + 1), 0x4180, 0x4240, 0xBD08)
        self.assertEqual(new.hex(), 'ff38a13801288041404208bd')


class KantoTradeEvosTest(unittest.TestCase):
    """b2tools/patches/kanto_trade_evos.py (slice a5.3) installs the Kanto trade-evolution *mechanic* by running
    trade_evos' data-only steps 1-2 and deferring the shop-append (step 3) to the Kanto-marts content phase. The steps
    touch no code, clang, shops or the intro chain and keep every archive's size, so the data-shape invariants that
    make the change boot-safe are checkable statically, on Windows."""

    PATCHES = os.path.join(ROOT, 'b2tools', 'patches')

    def setUp(self):
        if self.PATCHES not in sys.path:
            sys.path.insert(0, self.PATCHES)
        import json
        self.kanto = json.load(open(os.path.join(ROOT, 'data', 'kanto_trade_evos.json')))
        self.hoenn = json.load(open(os.path.join(ROOT, 'data', 'trade_evos.json')))

    def test_kanto_json_shape(self):
        # every evolution entry is [method, param, target]; symbols are the decomp's names (resolved by the patch)
        self.assertTrue(self.kanto['evolutions'], 'no evolutions in kanto_trade_evos.json')
        self.assertIn('keep_trade_methods', self.kanto)
        for sp, lst in self.kanto['evolutions'].items():
            self.assertTrue(sp.startswith('SPECIES_'), sp)
            self.assertTrue(lst, f'{sp}: empty evolution list')
            for e in lst:
                self.assertEqual(len(e), 3, f'{sp}: entry {e} is not [method, param, target]')
                self.assertTrue(e[0].startswith('EVO_METHOD_'), f'{sp}: method {e[0]}')

    def test_covers_the_engine_fixed_trade_species(self):
        # Black 2's a/0/1/9 fixes which species have a trade method, so the patch asserts
        # traders == keys(evolutions). The Kanto set must equal the Hoenn set (both cover exactly Black 2's traders).
        self.assertEqual(set(self.kanto['evolutions']), set(self.hoenn['evolutions']))

    def test_shop_append_is_deferred(self):
        # a5.3 ships the mechanic only: no shop block in the Kanto data (it needs Kanto marts / shops, Phase 2/3)
        self.assertNotIn('shop', self.kanto, 'kanto_trade_evos must defer the shop-append (see the adapter docstring)')
        self.assertIn('shop', self.hoenn)

    def test_record_packing_keeps_archive_size(self):
        # a/0/1/9 records are 7 x {u16 method, param, species} = 42 bytes; pack/entries_of keep that fixed size
        # (the invariant that leaves the ROM file table and savestates unchanged), and round-trip.
        import trade_evos
        entries = [(8, 221, 65), (5, 0, 66)]               # ITEM, TRADE (kept via keep_trade_methods)
        rec = trade_evos.pack(entries)
        self.assertEqual(len(rec), 42, 'evolution record must stay 42 bytes')
        self.assertEqual(trade_evos.entries_of(rec), entries)


class KantoBuildListTest(unittest.TestCase):
    """Phase 1 (a5.x) lands the QoL engine slices by appending patch names to the Kanto build list in
    b2tools/kanto_build.sh, never editing the Hoenn path. This guards that the shipped slices stay wired into the
    Kanto build (a pure text read, so it runs on Windows)."""

    # the QoL engine slices implemented so far (a5.2 escape_rope/exp_share, a5.3 kanto_trade_evos, a5.4 kanto_music)
    ENABLED = ('kanto_world', 'kanto_door', 'kanto_escape_rope', 'exp_share', 'kanto_trade_evos', 'kanto_music')

    def test_qol_patches_are_in_the_kanto_build_list(self):
        script = open(os.path.join(ROOT, 'b2tools', 'kanto_build.sh')).read()
        line = next((l for l in script.splitlines() if 'build_rom.py' in l), None)
        self.assertIsNotNone(line, 'kanto_build.sh has no build_rom.py invocation')
        for patch in self.ENABLED:
            self.assertIn(patch, line, f'{patch} is not enabled in the Kanto build list')


class KantoMusicDataTest(unittest.TestCase):
    """data/kanto_music.json must be sound before it is installed: every song slot is a Black 2 sequence the
    music pool proved free (data/hoenn_music.json 'pool.bgm_slots'), every zone points at a song that has a slot, and
    every FireRed-only instrument name maps to a program the Hoenn calibration actually measured. Pure JSON reads, so
    it runs on Windows (the install itself is covered by KantoMusicConvertTest under WSL)."""

    @classmethod
    def setUpClass(cls):
        cls.k = json.load(open(os.path.join(ROOT, 'data', 'kanto_music.json')))
        cls.h = json.load(open(os.path.join(ROOT, 'data', 'hoenn_music.json')))
        cls.lv = json.load(open(os.path.join(ROOT, 'data', 'hoenn_music_levels.json')))

    def test_slots_come_from_the_free_pool(self):
        pool = set(self.h['pool']['bgm_slots'])
        for song, slot in self.k['slots'].items():
            self.assertIn(slot, pool, f'{song} -> {slot} is not a proven-free Black 2 BGM slot')
        self.assertEqual(len(set(self.k['slots'].values())), len(self.k['slots']), 'two songs share a slot')

    def test_zones_reference_mapped_songs(self):
        for zid, song in self.k['zones'].items():
            self.assertIn(song, self.k['slots'], f'zone {zid} plays {song}, which has no slot')

    def test_defaults_use_measured_programs(self):
        measured = {int(x) for x in self.lv['programs']}
        for name, d in self.k['defaults'].items():
            self.assertIn(d['program'], measured, f'{name} -> program {d["program"]} is not in the measured library')


class KantoMusicFrlgReaderTest(unittest.TestCase):
    """b2tools/m4a_frlg.py is the FireRed side of the a5.4 soundtrack port: it reuses m4a.py's M4A engine parsing but
    finds the song table and reads songs straight from the user's FireRed dump (roms/firered_rev1_original.gba, which
    is gitignored). It touches no Black 2 ROM build, so it runs wherever the dump is present and skips otherwise."""

    DUMP = os.path.join(ROOT, 'roms', 'firered_rev1_original.gba')
    PFIR = os.path.join(ROOT, 'external', 'pokefirered')

    @classmethod
    def setUpClass(cls):
        if os.path.join(ROOT, 'b2tools') not in sys.path:
            sys.path.insert(0, os.path.join(ROOT, 'b2tools'))
        if not os.path.exists(cls.DUMP):
            raise unittest.SkipTest(f'FireRed dump not present: {cls.DUMP}')
        if not os.path.isdir(cls.PFIR):
            raise unittest.SkipTest('external/pokefirered is not installed')
        import m4a_frlg
        cls.m = m4a_frlg
        cls.rom = m4a_frlg.FrlgRom()

    def test_song_table_resolves(self):
        self.assertEqual(len(self.rom.song_names), 347, 'pokefirered song_table.inc should list 347 songs')
        self.assertTrue(0x08000000 <= self.rom.song_table < 0x0A000000, 'song table pointer out of ROM range')

    def test_kanto_songs_parse(self):
        # the songs the Kanto prototype's two maps and the title play parse into looping tracks with notes
        for song in ('mus_pallet', 'mus_route1', 'mus_title'):
            self.assertIn(song, self.rom.song_names, f'{song} is not in the FireRed song table')
            h, tracks = self.m.dump(song, self.rom)
            self.assertGreater(h['tracks'], 0, f'{song}: no tracks')
            self.assertTrue(any(t.loop_tick is not None for t in tracks), f'{song}: nothing loops (a field song must)')

    def test_sample_map_resolves(self):
        # pokefirered drops pokeruby's `@ address` labels, so the reader recovers addresses by locating each sample's
        # .incbin blob in the dump; it must cover most samples and name the FRLG-only ones the conversion needs.
        names = self.rom._build_sample_names()
        self.assertGreater(len(names), 80, 'FRLG sample map should resolve most pokefirered samples')
        self.assertIn('steinway_b_piano', set(names.values()), 'FRLG-only sample names must resolve')
        self.assertIn('sc88pro_nylon_str_guitar', set(names.values()), 'shared RSE/FRLG names must resolve')


class KantoMusicConvertTest(unittest.TestCase):
    """a5.4 step2: the FireRed songs the Kanto prototype plays convert to Black 2 SSEQ/SBNK/SWAR. The converter reads
    Black 2's instrument library from external/pokebw2/.../swan_sound_data.sdat (a WSL-only symlink), so it skips on
    Windows."""

    @classmethod
    def setUpClass(cls):
        for p in (os.path.join(ROOT, 'b2tools'), os.path.join(ROOT, 'b2tools', 'patches')):
            if p not in sys.path:
                sys.path.insert(0, p)
        try:
            from sdat import SDAT, DEFAULT
            open(DEFAULT, 'rb').read()
        except Exception as e:
            raise unittest.SkipTest(f'Black 2 SDAT not readable (run under WSL): {e}')
        import kanto_music
        cls.m = kanto_music

    def test_frlg_defaults_are_merged(self):
        mp = self.m.mapping()
        for name in ('steinway_b_piano', 'sd90_classical_whistle'):
            self.assertIn(name, mp['defaults'], f'{name} missing from the merged instrument table')

    def test_kanto_songs_convert(self):
        songs, total = self.m.convert_all(self.m.KANTO_SONGS)
        self.assertEqual(set(songs), set(self.m.KANTO_SONGS))
        for s, (q, b, w, vol) in songs.items():
            self.assertGreater(len(q), 0, f'{s}: empty sseq')
            self.assertGreater(len(w), 0, f'{s}: empty swar')
            self.assertTrue(0 <= vol <= 127, f'{s}: INFO volume {vol} out of range')
        self.assertGreater(total, 0)


if __name__ == '__main__':
    unittest.main()
