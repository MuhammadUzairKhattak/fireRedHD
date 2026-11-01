"""Populate work/tex with the Black 2 exterior building textures used by the model builders."""
import os

import b2files
import nsbtx


HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, '..'))
FILES = os.path.join(ROOT, 'external', 'pokebw2', 'build', 'b2_us', 'files')
OUT = os.path.join(ROOT, 'work', 'tex')


def main():
    os.makedirs(OUT, exist_ok=True)
    area = b2files.area(FILES, 2)
    area_data = b2files.map_textures(FILES, area['texset'])
    area_dir = os.path.join(OUT, 'area2')
    os.makedirs(area_dir, exist_ok=True)
    for name, image, _ in nsbtx.decode(area_data):
        image_file = os.path.join(area_dir, name.replace('.', '_') + '.png')
        if not os.path.exists(image_file):
            image.save(image_file)

    textures = b2files.narc_entries(b2files.arc_path(FILES, 174))
    packs = b2files.narc_entries(b2files.arc_path(FILES, 225))
    if len(textures) != len(packs):
        raise SystemExit(f'exterior texture/pack count differs: {len(textures)} != {len(packs)}')

    for pack_id, data in enumerate(textures):
        stem = f'ext{pack_id:02d}'
        texture_file = os.path.join(OUT, stem + '.nsbtx')
        if not os.path.exists(texture_file):
            open(texture_file, 'wb').write(data)

        image_dir = os.path.join(OUT, stem)
        os.makedirs(image_dir, exist_ok=True)
        for name, image, _ in nsbtx.decode(data):
            image_file = os.path.join(image_dir, name + '.png')
            if not os.path.exists(image_file):
                image.save(image_file)

        palette_file = os.path.join(OUT, f'pal{pack_id:02d}.txt')
        if not os.path.exists(palette_file):
            pairs = set().union(*(nsbtx.material_pairs(model['bmd'])
                                  for model in b2files.building_pack(FILES, pack_id)))
            with open(palette_file, 'w') as out:
                out.writelines(f'{texture} {palette}\n'
                               for texture, palette in sorted(pairs, key=str) if texture and palette)

    print(f'bootstrap_textures: Area 2 and {len(textures)} exterior sets in {OUT}')


if __name__ == '__main__':
    main()
