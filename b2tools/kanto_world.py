"""Compose the Kanto prototype maps (FireRed) onto one global tile grid - the Black 2 world-build step.

    python3 kanto_world.py                 -> work/kanto/world/ (world.json, grid.txt)
    python3 kanto_world.py --check         exit 1 on a placement/connection problem (writes nothing)

The parallel of b2tools/world.py for Kanto content, kept separate so Hoenn's build path is never edited in place
(AGENTS.md: "build new adapters for Kanto's content rather than modifying working Hoenn conversion logic"). It reads
the clean plans converter/frlg_plan.py writes (work/kanto/plans/<Map>.json) and places each map at its (tile_x, tile_z)
from data/kanto_world.json, exactly as world.compose does for Hoenn.

world.compose() and world.cells_needed() are reused here in spirit: those two functions hold no Hoenn-specific logic
(they only touch a plan's size/tiles/walkable/trees and a margin), but importing them would run world.py's module-level
terrain/heights.py, which reads the Black 2 ROM extract (external/pokebw2/.../ov036.bin). That extract, and the
build_cell()/patch stages that consume it (Gen 5 terrain writing from each tile class), are the next slices; this tool
does the placement, the connection-consistency check and the cell enumeration that gate them. If world.compose() ever
changes its plan-geometry contract, mirror it here (kept small and dependency-free on purpose).
"""
import json
import os
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, '..'))
CFG_PATH = os.path.join(ROOT, 'data', 'kanto_world.json')
PLAN_DIR = os.path.join(ROOT, 'work', 'kanto', 'plans')
OUT_DIR = os.path.join(ROOT, 'work', 'kanto', 'world')

# plan class -> one preview letter (grid.txt only; world.json keeps the real class strings). ASCII so the grid
# writes cleanly on a cp1252 console; ledge direction and tree halves live in the plan, not in this eyeball preview.
LETTER = {'grass': '.', 'path': '#', 'tall_grass': ',', 'long_grass': '"', 'flowers': 'f', 'sand': 's', 'ice': 'i',
          'water': 'W', 'tree_top_l': 'T', 'tree_top_r': 'T', 'tree_bot': 't', 'tree_tip': 'v', 'fence': '|',
          'building': 'B', 'building_roof': 'R', 'door': 'D', 'sign': 'S', 'prop': 'p', 'unknown': '?', 'blocked': 'X',
          'ledge_n': 'l', 'ledge_s': 'l', 'ledge_e': 'l', 'ledge_w': 'l'}

# tree classes a 2x2 tree model stands on. compose() opens any solid tile of these that no tree anchor covers, so a
# FireRed tree tile is never an invisible wall (the collision-matches-the-look rule Hoenn's forest fill enforces).
TREE_CLASSES = {'tree_top_l', 'tree_top_r', 'tree_bot', 'tree_tip'}


def load_doc(path=CFG_PATH):
    return json.load(open(path))


def _plans(doc, plan_dir=PLAN_DIR):
    return {name: os.path.join(plan_dir, f'{name}.json') for name in doc['maps']}


def compose(doc, plans=None):
    """Global tile grid: world[(wx, wz)] = (map, class, walkable). Mirrors world.compose's geometry (no shift/pad
    in the Kanto prototype; those keys are honoured if a future map sets them)."""
    cfg, lay = doc, doc['layout']
    M = cfg['margin_cells'] * 32
    plans = plans or _plans(doc)
    world, trees, maps, tree_tiles = {}, set(), {}, set()
    for name in cfg['maps']:
        mc = cfg['maps'][name]
        plan = json.load(open(plans[name]))
        L = lay[name]
        pad = cfg.get('pad_north', {}).get(name, 0)
        sx, sz = cfg.get('shift', {}).get(name, [0, 0])
        ox, oz = L['tile_x'] + M + sx, L['tile_z'] + M + sz + pad      # world position of the map's (0, 0)
        W, H = plan['size']
        rows = [(y, plan['tiles'][y], plan['walkable'][y]) for y in range(H)]
        rows += [(-pad + k, plan['tiles'][k % 2], plan['walkable'][k % 2]) for k in range(pad)]
        for y, tr, wr in rows:
            for x in range(W):
                key = (ox + x, oz + y)
                assert key not in world, f'{name} overlaps {world[key][0]} at {key}'
                world[key] = (name, tr[x], wr[x])
        for x, y in plan['trees']:
            if any((ox + x + dx, oz + y + dz) in tree_tiles for dx in (0, 1) for dz in (0, 1)):
                continue
            trees.add((ox + x, oz + y))
            tree_tiles.update((ox + x + dx, oz + y + dz) for dx in (0, 1) for dz in (0, 1))
        mc = dict(mc)
        maps[name] = dict(ox=ox, oz=oz, plan=plan, cfg=mc, w=W, h=H)
    # collision must match the look: a solid tree tile no 2x2 tree model covers would be an invisible wall, so open it
    # (frlg_plan covers every full 2x2 tree block; only isolated/edge tiles fall through to here).
    for k, (name, c, walk) in list(world.items()):
        if not walk and c in TREE_CLASSES and k not in tree_tiles:
            world[k] = (name, c, True)
    return world, trees, maps


def cells_needed(world):
    """built cells (holding map tiles) and the one-cell forest ring around them. Mirrors world.cells_needed."""
    built = {}
    for (wx, wz), (name, _, _) in world.items():
        c = (wx // 32, wz // 32)
        built.setdefault(c, {})
        built[c][name] = built[c].get(name, 0) + 1
    ring = {}
    for (cx, cz) in built:
        for dx in (-1, 0, 1):
            for dz in (-1, 0, 1):
                c = (cx + dx, cz + dz)
                if c not in built and c[0] >= 0 and c[1] >= 0:
                    ring.setdefault(c, []).append((cx, cz))
    return built, ring


def check_layout(doc):
    """Placement/connection consistency: every prototype-to-prototype connection must agree with layout's tile coords.
    Returns a list of problem strings (empty = clean). A connection to a map outside the prototype is an open edge and
    is not checked (it is expected to be listed in doc['open_edges'] for reporting)."""
    problems = []
    lay = doc['layout']
    have = set(lay)
    # sizes/connections are attached to doc['maps'][name] by build() before calling this; validate against those
    for name, mc in doc['maps'].items():
        if 'connections' not in mc:
            continue
        ax, az = lay[name]['tile_x'], lay[name]['tile_z']
        aw, ah = mc['size']
        for c in mc['connections']:
            dest = c['map']
            key = _plan_name(dest)
            if key not in have:
                continue                                            # open edge to a not-yet-built map
            bx, bz = lay[key]['tile_x'], lay[key]['tile_z']
            bw, bh = doc['maps'][key]['size']
            off = c.get('offset', 0)
            d = c['direction']
            exp = {'up': (ax + off, az - bh), 'down': (ax + off, az + ah),
                   'left': (ax - bw, az + off), 'right': (ax + aw, az + off)}[d]
            if (bx, bz) != exp:
                problems.append(f'{name}.{d} -> {dest}: layout has ({bx}, {bz}), connection implies {exp}')
    return problems


def _plan_name(map_const):
    """MAP_PALLET_TOWN -> PalletTown, MAP_ROUTE1 -> Route1 (FireRed map constants to plan file names)."""
    if not map_const.startswith('MAP_'):
        return map_const
    parts = map_const[4:].split('_')
    return ''.join(p.capitalize() for p in parts)


def preview(doc, maps):
    """An ASCII grid of the whole composed world for eyeballing, like plan_map.py prints per map."""
    if not maps:
        return ''
    minx = min(mp['ox'] for mp in maps.values())
    minz = min(mp['oz'] for mp in maps.values())
    maxx = max(mp['ox'] + mp['w'] for mp in maps.values())
    maxz = max(mp['oz'] + mp['h'] for mp in maps.values())
    # rebuild the world grid from plans (cheap, only for the printable region)
    world, _, _ = compose(doc)
    lines = []
    for z in range(minz, maxz):
        row = ''.join(LETTER.get(world[(x, z)][1], '?') if (x, z) in world else ' ' for x in range(minx, maxx))
        lines.append(row)
    return '\n'.join(lines)


def build(check=False, out_dir=OUT_DIR, plan_dir=PLAN_DIR):
    doc = load_doc()
    plans = _plans(doc, plan_dir)
    for name in doc['maps']:
        p = json.load(open(plans[name]))
        doc['maps'][name]['size'] = p['size']                       # W, H
        doc['maps'][name]['connections'] = p.get('connections') or []
    problems = check_layout(doc)
    if check:
        if problems:
            print('kanto layout problems:', *problems, sep='\n  ')
            return 1
        print('kanto layout consistent:', ', '.join(doc['maps']))
        return 0
    if problems:
        print('WARNING: kanto layout problems:', *problems, file=sys.stderr)
    world, trees, maps = compose(doc)
    built, ring = cells_needed(world)
    cells = sorted(built)
    bounds = ([min(c[0] for c in cells), min(c[1] for c in cells),
               max(c[0] for c in cells), max(c[1] for c in cells)] if cells else None)
    os.makedirs(out_dir, exist_ok=True)
    out = {
        'source': 'data/kanto_world.json + work/kanto/plans/*.json (b2tools/kanto_world.py)',
        'next_stage': 'build_cell (Gen 5 terrain from tile class) + ROM patch - gated on the pokebw2 extract (external/pokebw2)',
        'margin_cells': doc['margin_cells'],
        'cell_bounds': bounds,
        'cells_built': [list(c) for c in cells],
        'cells_ring': [list(c) for c in sorted(ring)],
        'maps': {n: dict(ox=mp['ox'], oz=mp['oz'], w=mp['w'], h=mp['h'],
                         kind=mp['cfg'].get('kind'), place=mp['cfg'].get('place'),
                         trees=sum(1 for t in trees if _in_map(t, mp)),
                         warps=mp['plan'].get('warps'), buildings=[b['kind'] for b in mp['plan'].get('buildings', [])])
                 for n, mp in maps.items()},
        'validation': {'ok': not problems, 'problems': problems},
    }
    json.dump(out, open(os.path.join(out_dir, 'compose_report.json'), 'w', encoding='utf-8'), indent=1)
    open(os.path.join(out_dir, 'grid.txt'), 'w', encoding='utf-8').write(preview(doc, maps) + '\n')
    total = len(world)
    walk = sum(1 for v in world.values() if v[2])
    print(f"kanto world: {len(maps)} maps, {total} tiles ({walk} walkable), {len(trees)} tree anchors, "
          f"{len(cells)} built cells + {len(ring)} forest ring (bounds {bounds}), "
          f"validation {'OK' if not problems else f'{len(problems)} PROBLEMS'} -> {out_dir}")
    return 0 if not problems else 1


def _in_map(t, mp):
    x, z = t
    return mp['ox'] <= x < mp['ox'] + mp['w'] and mp['oz'] <= z < mp['oz'] + mp['h']


def build_cells(out_dir=OUT_DIR, plan_dir=PLAN_DIR):
    """Run Black 2's real cell geometry builder over each composed Kanto cell: import b2tools/world unchanged and call
    world.build_cell per cell (flat heights: HF=None, world.py's 'before heights' path). This is the composition ->
    cell-geometry step toward a loadable map, reusing Hoenn's build machinery for Kanto content WITHOUT editing it.

    Needs `import world` to succeed, i.e. run under WSL (Ubuntu-24.04) where external/pokebw2's extract/build resolve
    (terrain.heights reads ov036.bin at module load); on Windows the symlink dangles and this returns 2. Full
    packaging (write_cell: placements/zones/chunk ids -> .dae -> narc -> ROM patch) is the next slice."""
    world = _import_world()
    if world is None:
        return 2
    doc = load_doc()
    plans = _plans(doc, plan_dir)
    for name in doc['maps']:
        doc['maps'][name]['size'] = json.load(open(plans[name]))['size']
    world_grid, trees, maps = compose(doc, plans)
    built, ring = cells_needed(world_grid)
    os.makedirs(out_dir, exist_ok=True)
    report = {}
    for c in sorted(built):
        owner = max(built[c], key=built[c].get)                     # the map with most tiles in the cell (zone/banner)
        m, per, grid = world.build_cell(f'kanto_{c[0]}_{c[1]}', c[0], c[1], world_grid, trees, doc['maps'])
        report[f'{c[0]}_{c[1]}'] = dict(owner=owner, tris=sum(len(v) for v in m.tris.values()),
                                        materials=len(m.tris), walkable=''.join(''.join(r) for r in grid).count('.'))
    json.dump({'source': 'world.build_cell over work/kanto compose (HF=None, flat)', 'cells': report},
              open(os.path.join(out_dir, 'cells_geom.json'), 'w', encoding='utf-8'), indent=1)
    print(f'built {len(report)} Kanto cells with world.build_cell: '
          + ', '.join(f'{k}:{v["tris"]} tris/{v["materials"]} mats' for k, v in report.items())
          + f' -> {out_dir}/cells_geom.json')
    return 0


def _import_world():
    try:
        if HERE not in sys.path:
            sys.path.insert(0, HERE)
        import world
        # Kanto-only building geometry: extrude the 'building'/'building_roof' classes no Hoenn module draws into
        # placeholder boxes (terrain/ground.py already renders fence/prop/water/wall). Appended to world.FEATURES at
        # runtime so neither b2tools/world.py nor Hoenn's data/terrain_modules.json is edited in place (AGENTS.md:
        # adapters for Kanto content). build_cell reads the FEATURES global when it runs.
        from terrain import kanto_features
        if not any(f is kanto_features for f in world.FEATURES):
            world.FEATURES = list(world.FEATURES) + [kanto_features]
        return world
    except Exception as e:
        print(f'needs b2tools/world importable (run under WSL, where external/pokebw2 resolves): '
              f'{type(e).__name__}: {e}', file=sys.stderr)
        return None


def write_cells(out_dir=None, plan_dir=PLAN_DIR, first_chunk=0, zone_base=450):
    """Emit a real Black 2 chunk per built Kanto cell: reuse world.write_cell UNCHANGED (build_cell's model + collision
    -> terrain.dae, collision.per, placements.bin, chunk.json, with Black 2 textures via feature_texture). This is the
    geometry->chunk step toward a loadable map; it runs flat (world.HF is left None - prepare()/Kanto heights is a4.3)
    and with no placements (warps/signs/building models are a4.4), so buildings render but doors are not yet wired.
    WSL-only (needs `import world`). Cells go to work/kanto/world/cells/<cx>_<cz>/."""
    world = _import_world()
    if world is None:
        return 2
    out_dir = out_dir or os.path.join(OUT_DIR, 'cells')
    doc = load_doc()
    plans = _plans(doc, plan_dir)
    for name in doc['maps']:
        doc['maps'][name]['size'] = json.load(open(plans[name]))['size']
    wgrid, trees, maps = compose(doc, plans)
    built, _ring = cells_needed(wgrid)
    shutil.rmtree(out_dir, ignore_errors=True)
    os.makedirs(out_dir, exist_ok=True)
    placements = {c: [] for c in built}                       # no props/warps yet (a4.4)
    order = sorted(built)
    report = {}
    for i, c in enumerate(order):
        owner = max(built[c], key=built[c].get)               # the map with most tiles in the cell
        key = f'{c[0]:02d}_{c[1]:02d}'
        d = os.path.join(out_dir, key)
        ntri = world.write_cell(d, f'kanto_{c[0]}_{c[1]}', c, wgrid, trees, doc['maps'], placements,
                                dict(chunk=first_chunk + i, zone=zone_base + i, map=owner))
        dae = os.path.join(d, 'terrain.dae')
        report[key] = dict(owner=owner, chunk=first_chunk + i, zone=zone_base + i, tris=ntri,
                           dae_bytes=os.path.getsize(dae) if os.path.exists(dae) else 0)
    json.dump({'source': 'world.write_cell over work/kanto compose (HF=None flat, no placements yet)', 'cells': report},
              open(os.path.join(OUT_DIR, 'cells_dae.json'), 'w', encoding='utf-8'), indent=1)
    print(f'wrote {len(report)} Kanto chunk(s) via world.write_cell -> {out_dir}: '
          + ', '.join(f'{k} {v["tris"]} tris/{v["dae_bytes"]}B dae' for k, v in report.items()))
    return 0


def package(out_dir=None, plan_dir=PLAN_DIR):
    """The functional-wiring pass that turns the composed Kanto maps into the package a ROM patch consumes, reusing
    b2tools/world.py's event/zone machinery UNCHANGED (no Hoenn edit): world.zone_rects (sub-cell zones), world.zone_of,
    world.make_put (placement blobs) and world.map_events (per-map zone: place/kind/fly point + door/sign/npc events) over
    the Kanto cfg, then world.write_cell for every cell (built map cells + the forest ring) with the real placements. It
    writes the ROM-shaped manifest work/kanto/world/world.json (matrix/width/height/area/cells[{cx,cz,chunk,zone}]/
    zones/zone_rects/standalone) - the exact input patches/hoenn_world.apply() reads (via HOENN_WORLD_DIR). The overworld
    builds complete (terrain, collision, walkability, fly, banner zone); doors/NPCs are wired only for destinations in
    that map cfg (empty for the Kanto prototypes now, so map_events safely emits none until Kanto interiors/scripts land).
    WSL-only (needs `import world`)."""
    world = _import_world()
    if world is None:
        return 2
    out_dir = out_dir or os.path.join(OUT_DIR, 'cells')
    doc = load_doc()
    plans = _plans(doc, plan_dir)
    for name in doc['maps']:
        doc['maps'][name]['size'] = json.load(open(plans[name]))['size']
    wgrid, trees, maps = compose(doc, plans)
    built, ring = cells_needed(wgrid)
    zone_of_map = {n: doc['maps'][n]['zone'] for n in doc['maps']}
    kind = {n: doc['maps'][n].get('kind', 'route') for n in doc['maps']}
    cells = {}
    for c, counts in built.items():                     # a town wins its cell (banner/music/respawn), else most tiles
        towns = {n: k for n, k in counts.items() if kind.get(n) == 'town'}
        pick = towns or counts
        cells[c] = zone_of_map[max(pick, key=pick.get)]
    for c, nbrs in ring.items():                        # the forest ring borrows a neighbour's zone
        best = max(nbrs, key=lambda n: sum(built[n].values()))
        cells[c] = cells[best]
    order = sorted(cells, key=lambda c: (c[1], c[0]))
    first_chunk = doc.get('first_chunk', 0)
    chunk_id = {c: first_chunk + i for i, c in enumerate(order)}
    W = max(c[0] for c in cells) + 1 + doc['margin_cells']
    H = max(c[1] for c in cells) + 1 + doc['margin_cells']
    rects = world.zone_rects(maps, cells, doc.get('pad_north'))
    zone_at = lambda wx, wz: world.zone_of(cells, wx, wz, rects)
    hgt = lambda wx, wz: 0                              # flat (single-elevation prototypes; see the a4.3 decision)
    placements = {c: [] for c in order}
    put = world.make_put(placements)
    zones = {}
    for name, mp in maps.items():
        world.map_events(name, mp, zones, put, hgt, zone_at, wgrid)
    # a building whose map cfg names a Black 2 model (data/kanto_world.json 'buildings') is drawn by that placed model,
    # not by kanto_features' placeholder massing: mark its footprint + roof tiles so the box is suppressed under it
    # (the tiles stay solid walls; the model is the building, exactly as in Hoenn).
    from terrain import kanto_features
    modeled = set()
    for mp in maps.values():
        ox, oz = mp['ox'], mp['oz']
        for b in mp['plan'].get('buildings', []):
            if not mp['cfg'].get('buildings', {}).get(b['dest']):
                continue
            x0, y0, x1, y1 = b['footprint']
            modeled.update((ox + x, oz + y) for y in range(y0 - b.get('roof_rows', 0), y1 + 1) for x in range(x0, x1 + 1))
    kanto_features.MODELED = modeled
    shutil.rmtree(out_dir, ignore_errors=True)
    os.makedirs(out_dir, exist_ok=True)
    for c in order:
        d = os.path.join(out_dir, f'{c[0]:02d}_{c[1]:02d}')
        world.write_cell(d, f'kanto_{c[0]}_{c[1]}', c, wgrid, trees, doc['maps'], placements,
                         dict(chunk=chunk_id[c], zone=cells[c]))
    manifest = dict(matrix=doc.get('matrix', 0), width=W, height=H, area=doc.get('area', 2),
                    cells=[dict(cx=c[0], cz=c[1], chunk=chunk_id[c], zone=cells[c]) for c in order],
                    zones={str(k): v for k, v in zones.items()}, standalone=[],
                    **({'zone_rects': rects} if rects else {}))
    json.dump(manifest, open(os.path.join(OUT_DIR, 'world.json'), 'w', encoding='utf-8'), indent=1)
    n_placed = sum(len(v) for v in placements.values())
    print(f'packaged Kanto world: {len(order)} cells (matrix {W}x{H}, area {manifest["area"]}), '
          f'zones {sorted(int(k) for k in manifest["zones"])} '
          f'(fly {[manifest["zones"][k].get("fly") for k in manifest["zones"]]}), '
          f'{n_placed} placements -> {os.path.join(OUT_DIR, "world.json")}')
    return 0


def convert_nsbmd(out_dir=None, plan_dir=None):
    """Turn every packaged Kanto cell's terrain.dae into the terrain.nsbmd the ROM chunk-packer (patches/kanto_world.py's
    _chunk/_terrain, shared with Hoenn's patches/hoenn_world.py) reads: one CTRMapV ToNsbmd batch over the cells, with
    Black 2's own palettes (world.write_palettes). This is the same step b2tools/rebuild_slice.sh / agent_build.sh run for
    Hoenn (java -cp work/java:tools/CTRMap.jar:...ToNsbmd --batch), reused unchanged for Kanto content. WSL-only (needs
    `import world` for the palettes, and the compiled ToNsbmd + CTRMap jars under work/java, tools/)."""
    import subprocess
    world = _import_world()
    if world is None:
        return 2
    cells = out_dir or os.path.join(OUT_DIR, 'cells')
    dirs = sorted(os.path.join(cells, d) for d in os.listdir(cells)
                  if os.path.exists(os.path.join(cells, d, 'terrain.dae')))
    if not dirs:
        print(f'convert_nsbmd: no terrain.dae under {cells} (run --world first)', file=sys.stderr)
        return 1
    pal = os.path.join(OUT_DIR, 'palettes.txt')
    os.makedirs(OUT_DIR, exist_ok=True)
    world.write_palettes(pal)
    batch = os.path.join(OUT_DIR, 'batch.txt')
    with open(batch, 'w', encoding='utf-8') as fh:
        for d in dirs:
            dae = os.path.join(d, 'terrain.dae')
            fh.write(f'{dae} {dae[:-4]}.nsbmd\n')
    cp = ':'.join(os.path.join(ROOT, p) for p in
                  ('work/java', 'tools/CTRMap.jar', 'tools/ctrmap-plugins/CTRMapV-1.4.1.jar'))
    r = subprocess.run(['java', '-Djava.awt.headless=true', '-cp', cp, 'ToNsbmd', '--batch', batch, pal],
                       capture_output=True, text=True)
    if r.returncode:
        print(f'ToNsbmd failed (rc {r.returncode}):\n{r.stdout[-1000:]}\n{r.stderr[-1000:]}', file=sys.stderr)
        return 1
    made = sum(os.path.exists(os.path.join(d, 'terrain.nsbmd')) for d in dirs)
    print(f'convert_nsbmd: {made}/{len(dirs)} Kanto cell(s) terrain.dae -> terrain.nsbmd -> {cells}')
    return 0 if made == len(dirs) else 1


def main(argv=None):
    argv = argv if argv is not None else sys.argv[1:]
    if '--cells' in argv:
        return build_cells()
    if '--dae' in argv:
        return write_cells()
    if '--nsbmd' in argv:
        return convert_nsbmd()
    if '--world' in argv:
        return package()
    return build(check='--check' in argv)


if __name__ == '__main__':
    sys.exit(main())
