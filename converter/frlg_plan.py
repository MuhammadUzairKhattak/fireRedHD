"""Turn one FireRed/LeafGreen map into a Black 2 build plan (work/kanto/plans/<Map>.json).

    python3 frlg_plan.py ../external/pokefirered PalletTown
    python3 frlg_plan.py ../external/pokefirered PalletTown Route1        (every prototype map, from data/frlg_source.json)

FireRed's mirror of converter/plan_map.py. It reads the map through converter/frlg.py's FrlgRepo (namespaced tilesets,
the 640-metatile primary split) and classifies each metatile with the FireRed table converter/frlg_classify.py writes
(data/labels/frlg_gTileset_*.json) - Hoenn's ids do not apply. The building (a warp inside a solid component becomes a
footprint, the rows above it a roof) and tree (a tree_top_l/tree_top_r pair) detection and the per-tile elevation from
blockdata bits 12-15 match plan_map.py, so b2tools/world.py consumes a Kanto plan exactly as it does a Hoenn one.
A metatile with no label is a hard error (it would load as 'unknown'): run frlg_classify.py first.
"""
import json
import os
import sys
from collections import deque

from frlg import FrlgRepo, load_config
from frlg_classify import class_by_behavior

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
OUT_DIR = os.path.join(ROOT, 'work', 'kanto', 'plans')


def load_table():
    """The FireRed label table: {namespaced_tileset: {hex_id: class}} from data/labels/frlg_*.json,
    with converter/frlg_classify.py's behaviour rules applied on top (a behaviour tile needs no stored label)."""
    table = {}
    for f in sorted(os.listdir(os.path.join(ROOT, 'data', 'labels'))):
        if not (f.startswith('frlg_') and f.endswith('.json')):
            continue
        doc = json.load(open(os.path.join(ROOT, 'data', 'labels', f)))
        for tsym, ids in doc.items():
            if tsym.startswith('_'):
                continue
            table.setdefault(tsym, {}).update(ids)
    return table


def classify(table, renderer, tsym, m):
    c = class_by_behavior(renderer.behavior(m))
    return c or table.get(tsym, {}).get(f'{m:03x}')


def plan_map(repo, table, name):
    mj = repo.map_json(name)
    grid, layout = repo.layout_grid(mj['layout'])
    H, W = grid.shape
    prim, sec = layout['primary_tileset'], layout['secondary_tileset']
    split = repo.METATILE_BOUNDARY
    from gba import MetatileRenderer
    renderer = MetatileRenderer(repo, prim, sec)

    cls = [[None] * W for _ in range(H)]
    solid = [[bool((int(grid[y, x]) >> 10) & 3) for x in range(W)] for y in range(H)]
    unclassified = {}
    for y in range(H):
        for x in range(W):
            m = int(grid[y, x]) & 0x3FF
            tsym = prim if m < split else sec
            c = classify(table, renderer, tsym, m)
            if c is None:
                c = 'blocked' if solid[y][x] else 'unknown'
                unclassified.setdefault(f'{tsym}:{m:03x}', []).append([x, y])
            cls[y][x] = c

    # buildings: a solid component (labelled building/door/building_roof/blocked) that holds a warp becomes a
    # footprint, and the unlabelled non-solid rows above it a roof (plan_map.py's rule, unchanged)
    BUILDING = ('blocked', 'building', 'door', 'building_roof')
    is_bld = lambda x, y: solid[y][x] and cls[y][x] in BUILDING
    warps = mj.get('warp_events', [])
    seen, buildings = set(), []
    for y in range(H):
        for x in range(W):
            if not is_bld(x, y) or (x, y) in seen:
                continue
            comp, q = [], deque([(x, y)])
            seen.add((x, y))
            while q:
                cx, cy = q.popleft()
                comp.append((cx, cy))
                for nx, ny in ((cx + 1, cy), (cx - 1, cy), (cx, cy + 1), (cx, cy - 1)):
                    if 0 <= nx < W and 0 <= ny < H and (nx, ny) not in seen and is_bld(nx, ny):
                        seen.add((nx, ny))
                        q.append((nx, ny))
            xs = [c[0] for c in comp]
            ys = [c[1] for c in comp]
            door = next((w for w in warps if (w['x'], w['y']) in set(comp)), None)
            if door is None or len(comp) < 6:
                continue
            x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
            roof = 0
            while y0 - roof - 1 >= 0 and all(cls[y0 - roof - 1][cx] in ('unknown', 'building_roof', 'building')
                                             and not solid[y0 - roof - 1][cx] for cx in range(x0, x1 + 1)):
                roof += 1
            for cx, cy in comp:
                cls[cy][cx] = 'building'
            for ry in range(y0 - roof, y0):
                for cx in range(x0, x1 + 1):
                    cls[ry][cx] = 'building_roof'
            dest = door['dest_map']
            kind = ('center' if 'POKEMON_CENTER' in dest else 'mart' if 'MART' in dest else
                    'lab' if 'LAB' in dest else 'house')
            buildings.append(dict(kind=kind, footprint=[x0, y0, x1, y1], roof_rows=roof, door=[door['x'], door['y']],
                                  dest=dest, metatiles=[[f'{int(grid[cy, cx]) & 0x3FF:03x}' for cx in range(x0, x1 + 1)]
                                                        for cy in range(y0 - roof, y1 + 1)]))

    trees = []
    for y in range(H):
        for x in range(W - 1):
            if cls[y][x] == 'tree_top_l' and cls[y][x + 1] == 'tree_top_r':
                trees.append([x, y])
    for x in range(W - 1):
        if cls[0][x] == 'tree_bot' and cls[0][x + 1] == 'tree_bot' and [x, -1] not in trees \
                and (x == 0 or [x - 1, -1] not in trees):
            trees.append([x, -1])
    tips_below = [[x, H] for x in range(W - 1) if cls[H - 1][x] == 'tree_tip' and cls[H - 1][x + 1] == 'tree_tip' and x % 2 == 0]

    elev_grid = [[(int(grid[y, x]) >> 12) & 0xF for x in range(W)] for y in range(H)]
    left = {k: v for k, v in unclassified.items() if any(cls[y][x] in ('unknown', 'blocked') for x, y in v)}
    plan = dict(map=name, size=[W, H], tilesets=[prim, sec],
                tiles=[[cls[y][x] for x in range(W)] for y in range(H)],
                walkable=[[not solid[y][x] for x in range(W)] for y in range(H)],
                elevation=elev_grid,
                trees=trees, trees_below_edge=tips_below, buildings=buildings,
                signs=[dict(x=b['x'], y=b['y'], script=b.get('script')) for b in mj.get('bg_events', []) if b.get('type') == 'sign'],
                warps=[dict(id=i, x=w['x'], y=w['y'], dest=w['dest_map'], dest_warp=w['dest_warp_id']) for i, w in enumerate(warps)],
                connections=mj.get('connections'), unclassified=left)
    return plan


def main(argv=None):
    argv = argv if argv is not None else sys.argv[1:]
    if not argv:
        print('usage: frlg_plan.py <pokefirered> [MAP ...]', file=sys.stderr)
        return 2
    repo = FrlgRepo(os.path.abspath(argv[0]))
    names = argv[1:] or load_config()['prototype_maps']
    table = load_table()
    rc = 0
    for name in names:
        plan = plan_map(repo, table, name)
        os.makedirs(OUT_DIR, exist_ok=True)
        out = os.path.join(OUT_DIR, f'{name}.json')
        json.dump(plan, open(out, 'w'), indent=1)
        left = plan['unclassified']
        if left:
            rc = 1
        print(f"{name}: {plan['size'][0]}x{plan['size'][1]}, {len(plan['trees'])} trees "
              f"(+{len(plan['trees_below_edge'])} below the edge), {len(plan['buildings'])} buildings "
              f"{[(b['kind'], b['footprint'], b['door']) for b in plan['buildings']]}, "
              f"unclassified {list(left)} -> {out}")
    return rc


if __name__ == '__main__':
    sys.exit(main())
