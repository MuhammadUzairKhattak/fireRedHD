"""Kanto-only building geometry: extrude FireRed/LeafGreen building footprints into placeholder box volumes.

world.build_cell gives geometry to path/grass/ledge/water, and terrain/ground.py draws fence/prop/wall/bush/rock -
but NO module owns the plan's 'building' and 'building_roof' classes. In Hoenn a building is a placed 3D model
(models_<town>.py -> a `res` id via map_events.put()), and the Kanto prototypes have no models and an empty buildings
config yet (the a4.4 "no bespoke models" decision), so Pallet Town's 3 detected buildings rendered as flat grass.

This module draws those tiles as solid extruded boxes instead - a placeholder that makes the town read as built, from
the footprint the plan already carries. It is enabled ONLY for the Kanto build: b2tools/kanto_world.py appends it to
world.FEATURES at runtime, so neither Hoenn's world.py nor its data/terrain_modules.json is edited (AGENTS.md: adapters
for Kanto content). Real per-building art (houses, Oak's Lab) replaces this in a later slice."""

CLASSES = {'building', 'building_roof'}
TEXTURES = {}                     # t02_kabe01 is Black 2's own town-wall texture (area 2 set 3): native, nothing to copy
WALL = 40                         # units: a one-storey massing (~2.5 tiles tall), like a Gen 3 house seen top-down
ROOF_EXTRA = 8                    # the roof rows stand a little higher, so a house reads as walls under a raised top
MAT = 't02_kabe01'                # Black 2 town wall (in terrain/ground.py's area-2 set: world.write_palettes covers it)


def _faces(bc, tx, tz, h1):
    """The faces of a solid box over one tile, corners from y 0 up to y h1, each as (verts, [reversed verts]) so it
    renders whichever way the camera sees it (the DAE writes single-sided geometry; a coincident back face costs 2
    triangles on a handful of tiles and keeps a box closed against back-face culling)."""
    x0, x1, z0, z1 = bc.ux(tx), bc.ux(tx + 1), bc.uz(tz), bc.uz(tz + 1)
    y0, y1 = 0, h1
    uv = lambda x, y, z, u, v: (x, y, z, u, v)
    top = [uv(x0, y1, z1, 0, 0), uv(x1, y1, z1, 1, 0), uv(x1, y1, z0, 1, 1), uv(x0, y1, z0, 0, 1)]
    north = [uv(x0, y0, z0, 0, 0), uv(x1, y0, z0, 1, 0), uv(x1, y1, z0, 1, 1), uv(x0, y1, z0, 0, 1)]
    south = [uv(x1, y0, z1, 0, 0), uv(x0, y0, z1, 1, 0), uv(x0, y1, z1, 1, 1), uv(x1, y1, z1, 0, 1)]
    west = [uv(x0, y0, z1, 0, 0), uv(x0, y0, z0, 1, 0), uv(x0, y1, z0, 1, 1), uv(x0, y1, z1, 0, 1)]
    east = [uv(x1, y0, z0, 0, 0), uv(x1, y0, z1, 1, 0), uv(x1, y1, z1, 1, 1), uv(x1, y1, z0, 0, 1)]
    return [top, north, south, west, east]


def draw(m, cell):
    """A box on every building/roof tile of this cell (chunk model units; cell.get -> (map, class, walkable))."""
    bc = cell.bc
    for tz in range(32):
        for tx in range(32):
            e = cell.get(tx, tz)
            if not e or e[1] not in CLASSES:
                continue
            h1 = WALL + (ROOF_EXTRA if e[1] == 'building_roof' else 0)
            for quad in _faces(bc, tx, tz, h1):
                m.quad(MAT, quad)
                m.quad(MAT, list(reversed(quad)))


def collision(cls, tile, cell):
    """None: keep build_cell's default. A building tile is already solid in the plan (not walkable), so it collides as
    a wall; this module only makes it visible."""
    return None
