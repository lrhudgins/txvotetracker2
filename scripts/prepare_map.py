"""Convert the supplied plan to WGS84 and optionally add reference precinct outlines."""
import io
import json
import tempfile
import zipfile
from pathlib import Path

from pyproj import CRS, Transformer
import shapefile
from shapely.geometry import shape, mapping
from shapely.ops import transform

from update import ROOT, fetch, write_json


def features(body):
    with zipfile.ZipFile(io.BytesIO(body)) as archive, tempfile.TemporaryDirectory() as temp:
        shp_names = [n for n in archive.namelist() if n.lower().endswith('.shp')]
        if len(shp_names) != 1:
            raise ValueError('Expected exactly one shapefile per boundary archive.')
        stem = shp_names[0][:-4]
        members = {n.lower(): n for n in archive.namelist()}
        for suffix in ('.shp', '.shx', '.dbf', '.prj', '.cpg'):
            key = (stem + suffix).lower()
            if key in members:
                Path(temp, 'boundary' + suffix).write_bytes(archive.read(members[key]))
        projection = Path(temp, 'boundary.prj').read_text()
        transformer = Transformer.from_crs(CRS.from_wkt(projection), 'EPSG:4326', always_xy=True)
        with shapefile.Reader(str(Path(temp, 'boundary.shp'))) as reader:
            fields = [f[0] for f in reader.fields[1:]]
            for record in reader.iterShapeRecords():
                props = dict(zip(fields, record.record))
                yield props, transform(transformer.transform, shape(record.shape.__geo_interface__))


def main():
    settings = json.loads((ROOT / 'config/settings.json').read_text())
    district = [(p, g) for p, g in features((ROOT / 'data/planc2333.zip').read_bytes()) if int(p['District']) == 10]
    if len(district) != 1:
        raise ValueError('The supplied plan must contain exactly one District 10 feature.')
    geometry = district[0][1]
    if not geometry.is_valid:
        raise ValueError('District geometry is invalid; review the source plan.')
    write_json(ROOT / 'docs/data/district.geojson', {'type': 'FeatureCollection', 'features': [
        {'type': 'Feature', 'properties': {'district': 10, 'plan': settings['plan']}, 'geometry': mapping(geometry)}]})
    target = ROOT / 'docs/data/precincts.geojson'
    if target.exists():
        return
    try:
        # This older map is used only to display outlines. It never assigns voters.
        relevant = set(settings['full_counties'] + settings['split_counties'])
        output = []
        for props, geom in features(fetch(settings['reference_precincts_url'])):
            lookup = {k.upper(): v for k, v in props.items()}
            county = str(lookup.get('COUNTY', '')).strip()
            if county not in relevant or not geom.intersects(geometry):
                continue
            clipped = geom.intersection(geometry).simplify(0.00008, preserve_topology=True)
            if clipped.is_empty or clipped.area == 0:
                continue
            pct = str(lookup.get('PREC', lookup.get('PRECINCT', ''))).strip()
            output.append({'type': 'Feature', 'properties': {'county': county, 'precinct': pct,
                           'vintage': settings['reference_precincts_vintage']}, 'geometry': mapping(clipped)})
        if not output:
            raise ValueError('No county/precinct features recognized in the reference map.')
        write_json(target, {'type': 'FeatureCollection', 'features': output})
    except Exception as exc:
        print(f'Reference precinct map unavailable: {type(exc).__name__}: {exc}. District outline still available.')


if __name__ == '__main__':
    main()
