"""Kanto-only building geometry: extrude FireRed/LeafGreen building footprints into placeholder box volumes.

world.build_cell gives geometry to path/grass/ledge/water, and terrain/ground.py draws fence/prop/wall/bush/rock -
but NO module owns the plan's 'building' and 'building_roof' classes. In Hoenn a building is a placed 3D model
(models_<town>.py -> a `res` id via map_events.put()), and the Kanto prototypes have no models and an empty buildings
config yet (the a4.4 "no bespoke models" decision), so Pallet Town's 3 detected buildings rendered as flat grass.

This module draws those tiles as a merged building massing instead - one solid volume per contiguous footprint (walls
on the outer edge only, so no per-tile seams), a raised roof slab in a distinct stone material. A 'door' tile is NOT
box-filled: it gets a recessed framed opening (side posts + lintel, centre open) facing the walkable approach, so the
warp you step into is visible as an entrance rather than a featureless wall tile - the old folded-in box made the
Viridian Forest entrance rooms' far-side exit indistinguishable from the perimeter ("no exit on the opposite end"). The
door tile stays solid in collision (build_cell never walks 'door'), so walking into the opening still fires the warp.
Massing walls still treat a neighbouring door as part of the footprint (FP_EDGE), so a house draws no wall over its own
 doorway. It also owns 'sign': a sign is solid in the plan but
had no model, so it rendered as an invisible wall (world.py's rule is that no solid tile is ever invisible) - here each
gets a small visible signpost. It is enabled ONLY for the Kanto build: b2tools/kanto_world.py appends it to world.FEATURES
at runtime, so neither Hoenn's world.py nor its data/terrain_modules.json is edited (AGENTS.md: adapters for Kanto
content). Real per-building art (houses, Oak's Lab) replaces this massing in a later slice."""

CLASSES = {'building', 'building_roof', 'door', 'sign'}
FP_BOX = {'building', 'building_roof'}             # classes extruded into a solid massing box (a 'door' is an opening, not a box)
FP_EDGE = {'building', 'building_roof', 'door'}    # footprint classes: a massing draws no wall face toward a neighbour in this set,
                                                   #   so a building/door boundary stays an open doorway rather than being walled shut
MODELED = set()                                    # world tiles (wx, wz) a real Black 2 building model stands on (map_events
                                                   # placed them from data/kanto_world.json 'buildings'); their placeholder
                                                   # box is suppressed so only the model shows. kanto_world.package() fills it.
TEXTURES = {'iwa01': 3, 'ki02c': 3}               # roof stone + sign wood: both Black 2 area-2 set 3 (write_palettes covers them)
WALL = 40                                         # model units (a tile is 16): a one-storey massing (~2.5 tiles tall), like a Gen 3 house
ROOF_EXTRA = 8                                    # the roof slab sits this much above the wall tops, so a house reads as walls under a raised top
MAT = 't02_kabe01'                                # Black 2 town wall (the body)
ROOF_MAT = 'iwa01'                                # Black 2 stone (roof top + parapet), distinct from the wall so the massing reads
SIGN_MAT = 'ki02c'                                # Black 2 wood (a signpost's post and board)


def _faces(x0, x1, z0, z1, y0, y1):
    """The five outward faces of a box as (x, y, z, u, v) corners, keyed by side."""
    uv = lambda x, y, z, u, v: (x, y, z, u, v)
    return {
        'top':   [uv(x0, y1, z1, 0, 0), uv(x1, y1, z1, 1, 0), uv(x1, y1, z0, 1, 1), uv(x0, y1, z0, 0, 1)],
        'north': [uv(x0, y0, z0, 0, 0), uv(x1, y0, z0, 1, 0), uv(x1, y1, z0, 1, 1), uv(x0, y1, z0, 0, 1)],
        'south': [uv(x1, y0, z1, 0, 0), uv(x0, y0, z1, 1, 0), uv(x0, y1, z1, 1, 1), uv(x1, y1, z1, 0, 1)],
        'west':  [uv(x0, y0, z1, 0, 0), uv(x0, y0, z0, 1, 0), uv(x0, y1, z0, 1, 1), uv(x0, y1, z1, 0, 1)],
        'east':  [uv(x1, y0, z0, 0, 0), uv(x1, y0, z1, 1, 0), uv(x1, y1, z1, 1, 1), uv(x1, y1, z0, 0, 1)],
    }


def _quad(m, mat, q):
    """One face, written double-sided: the DAE is single-sided, so a coincident back face (2 extra triangles on a
    handful of tiles) keeps the massing closed against back-face culling from any camera angle."""
    m.quad(mat, q); m.quad(mat, list(reversed(q)))


def _box(m, mat, x0, x1, z0, z1, y0, y1):
    for q in _faces(x0, x1, z0, z1, y0, y1).values():
        _quad(m, mat, q)


def _signpost(m, bc, tx, tz):
    """A slim post with a board on top, centred in the tile: small enough to read as a sign, solid so it stays blocked."""
    x0, x1, z0, z1 = bc.ux(tx), bc.ux(tx + 1), bc.uz(tz), bc.uz(tz + 1)
    _box(m, SIGN_MAT, x0 + 6, x1 - 6, z0 + 6, z1 - 6, 0, 16)          # post
    _box(m, SIGN_MAT, x0 + 2, x1 - 2, z0 + 5, z1 - 5, 16, 26)         # board


POST = 4                                            # doorway side-post thickness (model units; a tile is 16)
HEADER = 8                                          # the lintel sits this far below the wall top, leaving an open gap under it


def _doorway(m, bc, tx, tz, front):
    """A recessed framed opening on a warp 'door' tile: two side posts and a top lintel in the wall material, centre
    open toward `front` (the walkable side the player approaches from). No box fills the tile, so the doorway reads as
    an entrance; the tile is still solid in collision, so walking into the opening fires the warp. `front` is 'n'/
    's' (passage runs along z, posts on the east/west edges) or 'e'/'w' (passage along x, posts on the north/south
    edges); None draws a symmetric frame (posts on all four edges) for an ambiguous/isolated door."""
    x0, x1, z0, z1 = bc.ux(tx), bc.ux(tx + 1), bc.uz(tz), bc.uz(tz + 1)
    y1 = WALL
    if front in ('n', 's', None):                   # posts flank the east/west edges (passage north-south)
        _box(m, MAT, x0, x0 + POST, z0, z1, 0, y1)
        _box(m, MAT, x1 - POST, x1, z0, z1, 0, y1)
    if front in ('e', 'w', None):                   # posts flank the north/south edges (passage east-west)
        _box(m, MAT, x0, x1, z0, z0 + POST, 0, y1)
        _box(m, MAT, x0, x1, z1 - POST, z1, 0, y1)
    _box(m, MAT, x0, x1, z0, z1, y1 - HEADER, y1)   # lintel/header beam across the top, leaving the open gap below


def draw(m, cell):
    """One merged massing per contiguous building footprint, a recessed doorway on every warp 'door' tile, plus a
    signpost on every sign tile (chunk model units; cell.get -> (map, class, walkable), and it reads the neighbouring
    cell's tiles too, so a shared edge draws no wall)."""
    bc = cell.bc
    klass = lambda tx, tz: (lambda e: e[1] if e else None)(cell.get(tx, tz))
    walk = lambda tx, tz: bool((lambda e: e[2] if e else None)(cell.get(tx, tz)))
    fp = lambda tx, tz: klass(tx, tz) in FP_EDGE
    for tz in range(32):
        for tx in range(32):
            c = klass(tx, tz)
            if (cell.X + tx, cell.Z + tz) in MODELED:
                continue                                            # a real Black 2 building model stands here: no box under it
            if c in FP_BOX:
                x0, x1, z0, z1 = bc.ux(tx), bc.ux(tx + 1), bc.uz(tz), bc.uz(tz + 1)
                sides = [s for s, nb in (('north', (tx, tz - 1)), ('south', (tx, tz + 1)),
                                         ('west', (tx - 1, tz)), ('east', (tx + 1, tz))) if not fp(*nb)]
                body = _faces(x0, x1, z0, z1, 0, WALL)
                roof = _faces(x0, x1, z0, z1, WALL, WALL + ROOF_EXTRA)
                _quad(m, ROOF_MAT, roof['top'])                       # roof slab surface: one coplanar top per tile -> seamless
                for s in sides:
                    _quad(m, MAT, body[s])                            # body wall on the outer edge only (no interior seams)
                    _quad(m, ROOF_MAT, roof[s])                       # parapet rim raising the roof edge
            elif c == 'door':
                # the walkable side the player comes from is the doorway front (the door tile itself is solid).
                front = ('s' if walk(tx, tz + 1) else 'n' if walk(tx, tz - 1) else
                         'w' if walk(tx + 1, tz) else 'e' if walk(tx - 1, tz) else None)
                _doorway(m, bc, tx, tz, front)
            elif c == 'sign':
                _signpost(m, bc, tx, tz)


def collision(cls, tile, cell):
    """None: keep build_cell's default. A building/door/sign tile is already solid in the plan (not walkable), so it
    collides as a wall; this module only makes it visible."""
    return None
