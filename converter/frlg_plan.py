"""Turn one FireRed/LeafGreen map into a Black 2 build plan (work/kanto/plans/<Map>.json).

    python3 frlg_plan.py ../external/pokefirered PalletTown
    python3 frlg_plan.py ../external/pokefirered PalletTown Route1        (every prototype map, from data/frlg_source.json)

FireRed's mirror of converter/plan_map.py. It reads the map through converter/frlg.py's FrlgRepo (namespaced tilesets,
the 640-metatile primary split) and classifies each metatile with the FireRed table converter/frlg_classify.py writes
(data/labels/frlg_gTileset_*.json) - Hoenn's ids do not apply. The building (a warp inside a solid component becomes a
footprint, the rows above it a roof) and tree (a tree_top_l/tree_top_r pair) detection and the per-tile elevation from
blockdata bits 12-15 match plan_map.py, so b2tools/world.py consumes a Kanto plan exactly as it does a Hoenn one.
An MB_NORMAL metatile with no by-eye label is not an error here: it falls back to a navigable placeholder (a solid
'building' box or open 'grass', see PLACEHOLDER_*) and is tallied in the plan's 'placeholders' for frlg_classify.py to
label by eye later - so an un-reviewed city is walkable ground, never a field of invisible walls.
"""
import json
import os
import sys
from collections import deque

from frlg import FrlgRepo, load_config
from frlg_classify import class_by_behavior

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
OUT_DIR = os.path.join(ROOT, 'work', 'kanto', 'plans')

# classes the FLAT Kanto build cannot draw. Mirrors b2tools/terrain/heights.py's CLASSES (a module-level read of the
# Black 2 ov036.bin extract, so this converter must not import it) plus the south/north ledges, which heights.py does
# not list at all (no module owns them). Keep in step with heights.CLASSES when a new height class is added there.
HEIGHTS_OWNED = {'cliff', 'cliff_top', 'stairs', 'ledge_e', 'ledge_w', 'ledge_cap', 'mountain', 'cave_entrance',
                 'cracked_floor', 'mud', 'ledge_s', 'ledge_n'}

# Navigable placeholder classes for an MB_NORMAL metatile that has no by-eye label yet (converter/frlg_classify.py
# OVERRIDES). The whole-Kanto expansion has ~1.5k unlabelled city tiles; leaving them 'unknown'/'blocked' would paint
# invisible walls across every un-reviewed city, so an unlabelled tile falls back to a class the FLAT build draws:
# a solid metatile becomes a 'building' box, a walkable one open 'grass'. Each is counted in the plan's 'placeholders'
# so frlg_classify's by-eye pass can later replace them; a labelled tile never hits this path.
PLACEHOLDER_SOLID, PLACEHOLDER_OPEN = 'building', 'grass'


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


def flatify(cls, solid):
    """Make a classified grid renderable by the FLAT Kanto build (kanto_world.write_cells runs world.py with HF=None,
    so terrain/heights.py.draw returns early - `if FIELD is None: return` - and draws nothing). A solid tile whose class
    only heights owns (a cliff, cave mouth, ...), or that no module owns at all (a south/north ledge: heights.py has no
    ledge_s/ledge_n), is otherwise a barrier the player bumps into with nothing on screen - Route 22's invisible walls.
    Fold each into the closest class a flat module does draw: a solid rock mass becomes a 'wall' (terrain/ground.py
    draw_walls: a one-tile stone block, so collision still matches the look); a walkable heights tile and a ledge become
    open 'grass' (a ledge is a one-tile step-down with no height to drop through when flat, so it is walked, not walled -
    an honest simplification until Kanto heights, a4.3). Tree tiles are left to kanto_world.compose's tree cover."""
    H, W = len(cls), len(cls[0])
    for y in range(H):
        for x in range(W):
            c = cls[y][x]
            if c in HEIGHTS_OWNED:
                if c in ('ledge_s', 'ledge_n'):
                    cls[y][x] = 'grass'
                    solid[y][x] = False                     # a ledge is walked over, not a wall, when flat
                else:
                    cls[y][x] = 'wall' if solid[y][x] else 'grass'
    return cls


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
    placeholders = {}
    for y in range(H):
        for x in range(W):
            m = int(grid[y, x]) & 0x3FF
            tsym = prim if m < split else sec
            c = classify(table, renderer, tsym, m)
            if c is None:
                # an unlabelled metatile stays navigable (a solid box or open grass), never an invisible wall
                c = PLACEHOLDER_SOLID if solid[y][x] else PLACEHOLDER_OPEN
                key = f'{tsym}:{m:03x}'
                placeholders[key] = placeholders.get(key, 0) + 1
            cls[y][x] = c

    # the flat Kanto build draws no heights-owned class, so fold those tiles into a drawn class before anything reads
    # the grid (buildings below never see a 'cliff'/'ledge', and world.write_cell never leaves a solid tile undrawn).
    flatify(cls, solid)

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

    # trees: cover every tree metatile with a 2x2 tree model, greedily from each block's top-left, so the solid tree
    # tiles always have a visible tree over them. FireRed's tree art is not the clean tree_top_l/tree_top_r pairs the
    # old pair rule expected, so that rule left many solid tree tiles (the route borders and cluster edges) undrawn -
    # invisible walls. A tree tile no full 2x2 block covers is opened by kanto_world.compose so it is never a wall.
    TREE = {'tree_top_l', 'tree_top_r', 'tree_bot', 'tree_tip'}
    is_tree = lambda x, y: 0 <= x < W and 0 <= y < H and cls[y][x] in TREE
    trees, covered = [], set()
    for y in range(H):
        for x in range(W - 1):
            if (x, y) in covered or not is_tree(x, y):
                continue
            blk = [(x + dx, y + dz) for dz in (0, 1) for dx in (0, 1)]
            if all(is_tree(bx, by) for bx, by in blk):
                trees.append([x, y])
                covered.update(blk)
    tips_below = [[x, H] for x in range(W - 1) if cls[H - 1][x] == 'tree_tip' and cls[H - 1][x + 1] == 'tree_tip' and x % 2 == 0]

    elev_grid = [[(int(grid[y, x]) >> 12) & 0xF for x in range(W)] for y in range(H)]
    left = {k: v for k, v in unclassified.items() if any(cls[y][x] in ('unknown', 'blocked') for x, y in v)}
    plan = dict(map=name, id=mj['id'], size=[W, H], tilesets=[prim, sec],
                tiles=[[cls[y][x] for x in range(W)] for y in range(H)],
                walkable=[[not solid[y][x] for x in range(W)] for y in range(H)],
                elevation=elev_grid,
                trees=trees, trees_below_edge=tips_below, buildings=buildings,
                signs=[dict(x=b['x'], y=b['y'], script=b.get('script')) for b in mj.get('bg_events', []) if b.get('type') == 'sign'],
                warps=[dict(id=i, x=w['x'], y=w['y'], dest=w['dest_map'], dest_warp=w['dest_warp_id']) for i, w in enumerate(warps)],
                connections=mj.get('connections'), unclassified=left,
                placeholders={k: n for k, n in sorted(placeholders.items(), key=lambda kv: -kv[1])})
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
