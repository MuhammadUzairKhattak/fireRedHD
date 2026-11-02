"""FireRed/LeafGreen metatile classification for the Kanto prototype maps.

    python3 frlg_classify.py ../external/pokefirered            -> data/labels/frlg_gTileset_*.json
    python3 frlg_classify.py ../external/pokefirered --check     exit 1 when a label file is stale (nothing written)

Hoenn's converter classifies by a hand-checked id table (converter/metatiles.json + data/labels/gTileset_*.json)
keyed by pokeruby's metatile ids. FRLG reuses many of the same tileset *symbols* for different metatiles (its
General has 640 primary metatiles, not 512, and reorders ids), so those ids cannot carry over: a FireRed map read
with Hoenn's table scrambles grass into roofs and trees into buildings. This module classifies FRLG's own metatiles.

Two signals, in order of trust:
  1. the metatile behaviour byte (pokefirered include/constants/metatile_behaviors.h shares pokeruby's MB_* values),
     which is authoritative for terrain that has a behaviour: tall grass, water, ledges, sand, doors, signposts;
  2. OVERRIDES below - a hand-checked class for every behaviour-0x00 (MB_NORMAL) metatile the prototype maps use,
     read from rendered contact sheets (converter/frlg_classify.py --sheet writes them). A normal metatile's art is
     the only evidence, so it is labelled by eye rather than guessed from pixels.

Any metatile a prototype map uses that gets neither is an error: the plan would silently drop it as 'unknown'.
"""
import argparse
import json
import os
import sys

from frlg import FrlgRepo, load_config

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
OUT = os.path.join(ROOT, 'data', 'labels')

# MB_* -> class (pokefirered metatile_behaviors.h; same numeric values pokeruby's classify.py keys on).
def class_by_behavior(beh):
    if beh == 0x02: return 'tall_grass'                       # MB_TALL_GRASS (wild-encounter grass)
    if beh == 0x03: return 'long_grass'                        # MB_VERY_TALL_GRASS
    if 0x10 <= beh <= 0x17: return 'water'                     # pond/fast/deep/ocean/puddle/shallow water
    if beh == 0x21: return 'sand'                              # MB_SAND
    if beh == 0x23: return 'ice'
    if 0x38 <= beh <= 0x3B: return {0x38: 'ledge_e', 0x39: 'ledge_w', 0x3A: 'ledge_n', 0x3B: 'ledge_s'}[beh]
    if 0x62 <= beh <= 0x69: return 'door'                      # arrow warps, regular warp, warp door
    if beh == 0x84: return 'sign'                             # MB_SIGNPOST
    return None

# Hand-checked classes for MB_NORMAL metatiles used by the prototype maps (Pallet Town, Route 1), keyed by the
# namespaced tileset symbol and the metatile id. Trees: GBA trees are 2x2 (a canopy row over a trunk row); the left
# and right halves of each art variant are consecutive ids (top_l, top_r, bot, bot).
OVERRIDES = {
    'frlg:gTileset_General': {
        '001': 'grass', '008': 'grass', '009': 'grass', '010': 'grass', '011': 'grass',
        '004': 'flowers',
        '00e': 'tree_tip', '00f': 'tree_tip',
        '014': 'tree_top_l', '015': 'tree_top_r', '016': 'tree_bot', '017': 'tree_bot',
        '01c': 'tree_top_l', '01d': 'tree_top_r', '01e': 'tree_bot', '01f': 'tree_bot',
        '024': 'tree_top_l', '025': 'tree_top_r', '026': 'tree_bot', '027': 'tree_bot',
        # Route 1's sandy dirt path and its raised-dirt (jump-south) edges are labelled by behaviour; the flat path:
        '0d3': 'path', '0d4': 'path', '0d5': 'path', '0db': 'path', '0dc': 'path', '0dd': 'path',
        '0e3': 'path', '0e4': 'path', '0e5': 'path', '102': 'path', '103': 'path', '104': 'path', '105': 'path',
        # the metal gate where Route 1 meets Pallet Town (solid, grey, paired posts):
        '0e7': 'fence', '0ec': 'fence', '0ed': 'fence',
        # --- Viridian City additions (contact sheets work/kanto/sheets/b_gTileset_General_*.png) ---
        # a trimmed round hedge ball:
        '005': 'bush',
        # the decorative town pond: rounded shore corners vs the flat surface, and the fountain spray pieces:
        '028': 'water_edge', '029': 'water', '02a': 'water', '02b': 'water_edge',
        '030': 'water', '031': 'water', '032': 'water', '033': 'water',
        '038': 'water_edge', '039': 'prop', '03a': 'prop', '03b': 'water_edge',
        # wall-mounted shop signage (the letters 'HA'/'RT'/'P'/'C' and a round emblem):
        '040': 'sign', '041': 'sign', '05a': 'sign', '060': 'sign', '061': 'sign',
        # the red-tiled market roofs and a grey sloped roof edge:
        '048': 'building_roof', '049': 'building_roof', '04a': 'building_roof', '04b': 'building_roof',
        '050': 'building_roof', '051': 'building_roof', '052': 'building_roof', '053': 'building_roof',
        '063': 'building_roof',
        # a rock at the pond edge:
        '058': 'prop',
        # town buildings (grey walls with blue windows):
        '059': 'building', '05b': 'building',
        # the brown mountain/cliff wall that borders Viridian's north and west:
        '069': 'cliff', '06a': 'cliff', '06b': 'cliff', '06c': 'cliff', '06d': 'cliff',
        '071': 'cliff', '072': 'cliff', '073': 'cliff', '075': 'cliff', '079': 'cliff',
        '07a': 'cliff', '07b': 'cliff', '07c': 'cliff', '07d': 'cliff', '0b2': 'cliff',
        '0ba': 'cliff', '0bb': 'cliff',
        # the pale mint town ground:
        '0bd': 'grass', '0be': 'grass', '0bf': 'grass', '0c4': 'grass', '0c5': 'grass',
        '0c6': 'grass', '0c7': 'grass', '0cb': 'grass', '0cd': 'grass', '0ce': 'grass', '0cf': 'grass',
        # grey railing/fence posts (paired) along the walkways:
        '0f4': 'fence', '0f5': 'fence', '0fc': 'fence', '0fd': 'fence',
        # grass with a dirt lip at one corner:
        '133': 'grass',
        # the tan-sided market/warehouse walls (with window rows):
        '141': 'building', '142': 'building', '143': 'building', '149': 'building', '14a': 'building',
        '14b': 'building', '150': 'building', '151': 'building', '152': 'building', '154': 'building',
        '156': 'building', '159': 'building', '15a': 'building', '15c': 'building', '15e': 'building',
        '15f': 'building',
        # a Poké Ball emblem painted on the ground:
        '153': 'prop',
        # grass with a building edge drawn over the top:
        '158': 'grass',
        # a red-domed roof top:
        '160': 'building_roof',
        # the pale grey paved town squares:
        '165': 'path', '166': 'path', '167': 'path', '16d': 'path', '16e': 'path', '16f': 'path',
        '175': 'path', '176': 'path', '177': 'path', '195': 'path', '196': 'path', '19d': 'path', '19e': 'path',
        # a glass-fronted wall and its red/grey roof edges:
        '186': 'building', '187': 'building_roof', '18f': 'building_roof', '19f': 'building_roof',
        '197': 'building',
        # a brown rock at the south-west cliff base:
        '1f2': 'cliff',
        # --- Route 2 / Route 22 additions (contact sheet work/kanto/sheets/unclassified.png) ---
        # pale grey/blue paneled walls and the tan market walls (solid building faces):
        '044': 'building', '045': 'building', '046': 'building', '04c': 'building', '04d': 'building', '04e': 'building',
        '05c': 'building', '05d': 'building', '05e': 'building', '064': 'building', '065': 'building', '066': 'building',
        '170': 'building', '171': 'building', '183': 'building', '184': 'building', '185': 'building', '188': 'building',
        '189': 'building', '18a': 'building', '190': 'building', '191': 'building', '192': 'building',
        # the brown rock/cliff that borders the route, and the dark Viridian Forest mouth:
        '068': 'cliff', '070': 'cliff', '078': 'cliff', '0b3': 'cliff', '198': 'cliff',
        '0a9': 'cave_entrance',
        # the pale mint route ground and the sandy/dirt patches:
        '0c3': 'grass', '0cc': 'grass',
        '178': 'sand', '17a': 'sand', '199': 'sand', '19a': 'sand',
        # the solid white/grey railings that wall off the route (0e6/0f2: a post with a railing arm):
        '0e6': 'fence', '0f2': 'fence',
        # the tan boardwalk planks are walkable (solid=0), not railings: draw them as path, never a fence (a fence here
        # rendered a railing you could walk straight through - Route 22's "railings in incorrect places"):
        '162': 'path', '163': 'path', '164': 'path', '16a': 'path', '16b': 'path',
        '16c': 'path', '172': 'path', '173': 'path', '174': 'path',
        # small route shrubs (a trunk with a leafy top):
        '0e8': 'bush', '0e9': 'bush', '0f0': 'bush', '0f3': 'bush',
        # the route pond water:
        '1b5': 'water', '1b6': 'water', '1b7': 'water',
        # Route 2's blue-roofed shop: windowed walls, the blue roof rows, and the wall row under them:
        '006': 'building', '007': 'building',
        '02c': 'building_roof', '02d': 'building_roof', '02f': 'building_roof',
        '034': 'building_roof', '035': 'building_roof', '036': 'building_roof', '037': 'building_roof',
        '03c': 'building', '03f': 'building',
    },
    'frlg:gTileset_PalletTown': {
        # houses: slanted roof rows, walls/windows (solid), and the pale mint town ground under/around them.
        '281': 'building_roof', '282': 'building_roof', '283': 'building_roof',
        '284': 'building', '287': 'prop',
        '285': 'grass', '286': 'grass', '288': 'grass', '28c': 'grass',
        '289': 'building', '28a': 'building', '28b': 'building',
        '28e': 'grass', '28f': 'grass', '290': 'grass',
        '291': 'building', '292': 'building', '293': 'building', '294': 'building',
        '295': 'grass', '296': 'grass', '297': 'grass',
        '298': 'building', '299': 'building', '29a': 'building', '29b': 'building', '29c': 'building',
        '29e': 'grass', '29f': 'grass',
        '2a0': 'building', '2a1': 'building', '2a2': 'building', '2a4': 'building',
        '2a5': 'grass', '2a6': 'grass', '2a7': 'grass',
        '2a8': 'building', '2a9': 'building',
        '2aa': 'tree_bot', '2ab': 'tree_bot', '2b2': 'tree_bot', '2ba': 'tree_bot',   # Route 1's south-border trees
        '2ae': 'grass', '2af': 'grass',
        '2b0': 'building', '2b1': 'building', '2b3': 'building', '2b4': 'building', '2b5': 'building',
        '2b6': 'grass',
        '2b8': 'building', '2b9': 'building', '2bb': 'building', '2bc': 'building', '2bd': 'building',
        '2be': 'grass', '2bf': 'grass',
        '2c0': 'building', '2c1': 'building', '2c2': 'building', '2c3': 'building', '2c4': 'building', '2c5': 'building',
        '2c6': 'grass', '2c7': 'grass',
        '2c8': 'building', '2c9': 'building', '2cb': 'building', '2cc': 'building', '2cd': 'building',
        '2ce': 'grass', '2d0': 'building', '2d8': 'building',
    },
    'frlg:gTileset_ViridianCity': {
        # Viridian's own secondary tileset (contact sheets b_gTileset_ViridianCity_*.png).
        # trimmed hedges around the town (the walk-behind top row and the solid balls):
        '280': 'bush', '281': 'bush', '282': 'bush', '284': 'bush', '285': 'bush', '286': 'bush',
        '287': 'bush', '288': 'bush', '289': 'bush', '28a': 'bush', '28c': 'bush', '28d': 'bush',
        '290': 'bush', '291': 'bush', '292': 'bush', '293': 'bush', '294': 'bush',
        # the market/shop buildings (tan walls, dark window grids, glass fronts):
        '283': 'building', '28b': 'building', '29d': 'building', '2a5': 'building', '2a6': 'building',
        '2a7': 'building', '2ab': 'building', '2ad': 'building', '2ae': 'building', '2af': 'building',
        # the garden archway / planter feature with its fountain emblem:
        '298': 'prop', '29a': 'prop', '29b': 'prop', '29c': 'prop',
        # grass at the base of the garden structure:
        '2a0': 'grass', '2a2': 'grass', '2a3': 'grass', '2a4': 'grass',
        # the pale grey paving (with hedge/roof edges drawn over it):
        '2a8': 'path', '2a9': 'path', '2aa': 'path', '2ac': 'path', '2b0': 'path', '2b1': 'path',
        '2b2': 'path', '2b3': 'path', '2b4': 'path',
        # a brown rock at the cliff base:
        '2bc': 'cliff',
        # --- Route 2 / Route 22 additions (the maps reuse Viridian's secondary tileset) ---
        # the tan market wall and the pale grey town walls:
        '296': 'building', '2b5': 'building', '2b6': 'building', '2b7': 'building', '2cd': 'building', '2ce': 'building',
        # the brown cliff/rock:
        '297': 'cliff', '29e': 'cliff', '2db': 'cliff',
        # trimmed round hedges and leafy bushes:
        '2b8': 'bush', '2b9': 'bush', '2ba': 'bush', '2bb': 'bush', '2c4': 'bush', '2cf': 'bush',
        # Route 22's warehouse/rival's-house walls (brick, pale siding, glass fronts) and the hedges beside them:
        '2bd': 'building', '2be': 'building', '2bf': 'building', '2c0': 'building', '2c1': 'building',
        '2c2': 'building', '2c3': 'building', '2c5': 'building', '2c7': 'building', '2c8': 'building',
        '2ca': 'building', '2d0': 'building', '2d2': 'building', '2d4': 'building', '2d5': 'building',
        '2d6': 'building', '2d8': 'building', '2da': 'building',
        '2cb': 'bush', '2d3': 'bush',
    },
}


def classify(repo, renderer, tsym, m, beh):
    """One FRLG metatile's class, or None when neither behaviour nor a hand-checked label covers it."""
    c = class_by_behavior(beh)
    if c:
        return c
    return OVERRIDES.get(tsym, {}).get(f'{m:03x}')


def used_metatiles(repo, maps):
    """{namespaced_tileset: {metatile_id: (map, x, y)}} for every metatile the given maps place."""
    used = {}
    split = repo.METATILE_BOUNDARY
    for name in maps:
        mj = repo.map_json(name)
        grid, layout = repo.layout_grid(mj['layout'])
        prim, sec = layout['primary_tileset'], layout['secondary_tileset']
        for y in range(grid.shape[0]):
            for x in range(grid.shape[1]):
                m = int(grid[y, x]) & 0x3FF
                tsym = prim if m < split else sec
                used.setdefault(tsym, {}).setdefault(m, (name, x, y))
    return used


def build_labels(repo_root, maps):
    """{namespaced_tileset: {hex_id: class}} plus the ids that got no class (must be empty for a clean plan)."""
    repo = FrlgRepo(repo_root)
    used = used_metatiles(repo, maps)
    labels, missing = {}, []
    for tsym, ids in used.items():
        renderer = repo_tileset_renderer(repo, tsym, maps)
        for m, at in sorted(ids.items()):
            c = classify(repo, renderer, tsym, m, renderer.behavior(m))
            if c is None:
                missing.append((tsym, f'{m:03x}', at))
            else:
                labels.setdefault(tsym, {})[f'{m:03x}'] = c
    return labels, missing


def repo_tileset_renderer(repo, tsym, maps):
    """A MetatileRenderer for a tileset pair any of the maps uses (FRLG prototype maps share one pair)."""
    from gba import MetatileRenderer
    for name in maps:
        _, layout = repo.layout_grid(repo.map_json(name)['layout'])
        if tsym in (layout['primary_tileset'], layout['secondary_tileset']):
            return MetatileRenderer(repo, layout['primary_tileset'], layout['secondary_tileset'])
    raise KeyError(tsym)


def label_path(tsym):
    """data/labels/frlg_gTileset_X.json for 'frlg:gTileset_X' (frlg_ prefix keeps these apart from Hoenn's)."""
    return os.path.join(OUT, tsym.replace(':', '_') if not tsym.startswith('frlg:')
                        else 'frlg_' + tsym.split(':', 1)[1] + '.json')


def render_doc(tsym):
    return (f"FRLG {tsym} metatile classes for the Kanto prototype maps (converter/frlg_classify.py, generated: "
            f"do not edit by hand - add a behaviour rule or an OVERRIDES entry there). Behaviour-anchored classes "
            f"(tall_grass/water/ledge/sand/door/sign) come from pokefirered's MB_* codes; MB_NORMAL art is hand-"
            f"checked from the contact sheets. Keyed by the namespaced tileset so Hoenn's ids never apply.")


def write_sheets(repo_root, maps, out_dir):
    """Render a contact sheet of every metatile the maps use (id, behaviour, primary/secondary) for by-eye labelling.
    This is the evidence the OVERRIDES table is read from; see notes/LABELS.md for the class vocabulary."""
    from PIL import Image, ImageDraw
    from gba import MetatileRenderer
    repo = FrlgRepo(os.path.abspath(repo_root))
    used = used_metatiles(repo, maps)
    os.makedirs(out_dir, exist_ok=True)
    paths = []
    for tsym in sorted(used):
        renderer = repo_tileset_renderer(repo, tsym, maps)
        ids = sorted(used[tsym])
        cols = 8
        rows = (len(ids) + cols - 1) // cols
        img = Image.new('RGB', (cols * 100, max(rows, 1) * 100), (40, 40, 40))
        d = ImageDraw.Draw(img)
        for i, m in enumerate(ids):
            x0, y0 = (i % cols) * 100, (i // cols) * 100
            img.paste(Image.fromarray(renderer.render(m)[..., :3]).resize((64, 64), Image.NEAREST), (x0 + 4, y0 + 4))
            d.text((x0 + 72, y0 + 6), f'{m:03x}', fill=(255, 255, 0))
            d.text((x0 + 72, y0 + 22), f'beh {renderer.behavior(m):02x}', fill=(255, 255, 255))
            d.text((x0 + 72, y0 + 38), 'prim' if m < repo.METATILE_BOUNDARY else 'sec', fill=(180, 180, 255))
        p = os.path.join(out_dir, tsym.split(':', 1)[1] + '.png')
        img.save(p)
        paths.append(p)
    return paths


def main(argv=None):
    ap = argparse.ArgumentParser(description='Classify FRLG metatiles and write data/labels/frlg_*.json')
    ap.add_argument('repo', nargs='?', default=os.path.join(ROOT, 'external', 'pokefirered'))
    ap.add_argument('--check', action='store_true', help='fail if a label file is not current (writes nothing)')
    ap.add_argument('--todo', metavar='OUT.json', help='write the unclassified ids to OUT.json')
    ap.add_argument('--sheet', metavar='OUT_DIR', help='write by-eye contact sheets of the used metatiles and exit')
    args = ap.parse_args(argv)
    if args.sheet:
        maps = load_config()['prototype_maps']
        for p in write_sheets(args.repo, maps, args.sheet):
            print('sheet:', p)
        return 0
    repo_root = os.path.abspath(args.repo)
    maps = load_config()['prototype_maps']
    labels, missing = build_labels(repo_root, maps)
    if args.todo:
        os.makedirs(os.path.dirname(os.path.abspath(args.todo)), exist_ok=True)
        json.dump([{'tileset': t, 'id': i, 'at': list(a)} for t, i, a in missing], open(args.todo, 'w'), indent=1)
    stale = []
    for tsym in sorted(labels):
        out = {'_doc': render_doc(tsym), tsym: dict(sorted(labels[tsym].items()))}
        p = label_path(tsym)
        text = json.dumps(out, indent=1, ensure_ascii=False) + '\n'
        if args.check:
            if not os.path.exists(p) or open(p).read() != text:
                stale.append(p)
        else:
            os.makedirs(os.path.dirname(p), exist_ok=True)
            open(p, 'w').write(text)
    if args.check:
        print('stale:' if stale else 'frlg label files current', *stale)
        return 1 if stale else 0
    n = sum(len(v) for v in labels.values())
    print(f'classified {n} metatiles across {len(labels)} tilesets '
          f'({", ".join(f"{t.split(chr(58),1)[-1]}: {len(v)}" for t, v in sorted(labels.items()))})')
    if missing:
        print(f'UNCLASSIFIED ({len(missing)}):', *(f'{t}:{i}@{a}' for t, i, a in missing), file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
