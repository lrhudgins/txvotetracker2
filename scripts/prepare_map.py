"""Build WGS84 reference precinct outlines from the Council's official files."""
import argparse
import io
import json
import tempfile
import zipfile
from pathlib import Path
import shapefile
from pyproj import CRS, Transformer
from update import ROOT, fetch, load_crosswalk, precinct, write_json

# Census county FIPS values, checked against the supplied Council workbook.
COUNTIES = {21: 'Bastrop', 41: 'Brazos', 51: 'Burleson', 185: 'Grimes', 225: 'Houston',
            287: 'Lee', 289: 'Leon', 313: 'Madison', 373: 'Polk', 407: 'San Jacinto',
            453: 'Travis', 455: 'Trinity', 471: 'Walker'}


def features(body, select):
    with zipfile.ZipFile(io.BytesIO(body)) as archive, tempfile.TemporaryDirectory() as temp:
        names = archive.namelist()
        shps = [n for n in names if n.lower().endswith('.shp')]
        if len(shps) != 1:
            raise ValueError('Expected one shapefile per archive.')
        stem = shps[0][:-4]
        members = {n.lower(): n for n in names}
        for suffix in ('.shp', '.shx', '.dbf', '.prj', '.cpg'):
            key = (stem + suffix).lower()
            if key in members:
                Path(temp, 'boundary' + suffix).write_bytes(archive.read(members[key]))
        converter = Transformer.from_crs(CRS.from_wkt(Path(temp, 'boundary.prj').read_text()), 'EPSG:4326', always_xy=True)
        def coordinates(value):
            if isinstance(value[0], (int, float)):
                lon, lat = converter.transform(value[0], value[1])
                return [round(lon, 7), round(lat, 7)]
            return [coordinates(v) for v in value]
        with shapefile.Reader(str(Path(temp, 'boundary.shp'))) as reader:
            fields = [f[0] for f in reader.fields[1:]]
            for record in reader.iterShapeRecords():
                selected = select(dict(zip(fields, record.record)))
                if selected is None:
                    continue
                geom = record.shape.__geo_interface__
                yield {'type': 'Feature', 'properties': selected,
                       'geometry': {'type': geom['type'], 'coordinates': coordinates(geom['coordinates'])}}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--precincts-zip', type=Path)
    parser.add_argument('--force', action='store_true')
    args = parser.parse_args()
    settings = json.loads((ROOT / 'config/settings.json').read_text())
    district_path = ROOT / 'docs/data/district.geojson'
    if args.force or not district_path.exists():
        district = list(features((ROOT / 'data/planc2333.zip').read_bytes(),
                        lambda p: {'district': 10, 'plan': settings['plan']} if int(p['District']) == 10 else None))
        if len(district) != 1:
            raise ValueError('Expected one District 10 geometry.')
        write_json(district_path, {'type': 'FeatureCollection', 'features': district})
    target = ROOT / 'docs/data/precincts.geojson'
    if target.exists() and not args.force:
        print('Using bundled reference precinct map.')
        return
    crosswalk = load_crosswalk(ROOT / 'config/precinct_crosswalk.csv', settings['election_date'])
    def select(properties):
        lookup = {k.upper(): v for k, v in properties.items()}
        name = lookup.get('COUNTY', lookup.get('FENAME'))
        county = str(name).strip().title() if name else COUNTIES.get(int(lookup.get('CNTY', 0)))
        p = precinct(lookup.get('PREC', lookup.get('PRECINCT', '')))
        if crosswalk.get((county, p)) != 10:
            return None
        return {'county': county, 'precinct': p, 'district': 10, 'vintage': '2026 primary precincts',
                'assignment_basis': '2026 primary PlanC2333 workbook'}
    path = args.precincts_zip or ROOT / 'data/precincts26p.zip'
    body = path.read_bytes() if path.exists() else fetch(settings['reference_precincts_url'])
    output = list(features(body, select))
    if not output:
        raise ValueError('No target precincts matched county FIPS and the crosswalk.')
    write_json(target, {'type': 'FeatureCollection', 'features': output})
    print(f'Prepared {len(output)} primary-reference precinct features. Full precinct outlines, not clipped pieces.')


if __name__ == '__main__':
    main()
