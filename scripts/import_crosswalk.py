"""Import Council's PlanC2333 precinct workbook without claiming November verification."""
import argparse
import csv
from pathlib import Path
import pandas as pd
from update import ROOT, precinct, read_json

SOURCE = 'https://data.capitol.texas.gov/dataset/precincts/resource/58899c7b-a3ba-4cea-b70c-524fbd3920af'


def convert(path, output=ROOT / 'config/precinct_crosswalk.csv'):
    frame = pd.read_excel(path, dtype=str).fillna('')
    county_col = 'FENAME' if 'FENAME' in frame.columns else 'COUNTY'
    if not {county_col, 'PREC', 'PlanC2333'}.issubset(frame.columns):
        raise ValueError('Expected county name, PREC and PlanC2333 columns.')
    settings = read_json(ROOT / 'config/settings.json', {})
    allowed = set(settings['full_counties'] + settings['split_counties'])
    rows, seen = [], {}
    for _, row in frame.iterrows():
        county = row[county_col].strip().title()
        if county not in allowed:
            continue
        pct, district = precinct(row['PREC']), int(row['PlanC2333'])
        key = county, pct
        if key in seen and seen[key] != district:
            raise ValueError('Conflicting district assignments for one precinct; cannot import as a whole precinct.')
        if key in seen:
            continue
        if not 1 <= district <= 38 or not pct:
            raise ValueError('Invalid precinct or congressional district.')
        if county in settings['full_counties'] and district != settings['district']:
            raise ValueError('Workbook disagrees with expected whole-county district coverage.')
        seen[key] = district
        rows.append({'county': county, 'precinct': pct, 'congressional_district': district,
                     'verified_for_election': '', 'source_url': SOURCE, 'assignment_basis': '2026-primary-reference'})
    if not rows:
        raise ValueError('No target-county rows found.')
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open('w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(sorted(rows, key=lambda r: (r['county'], r['precinct'])))
    print(f'Imported {len(rows)} precinct assignments as a provisional 2026-primary reference.')
    return rows


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('workbook', type=Path)
    parser.add_argument('--output', type=Path, default=ROOT / 'config/precinct_crosswalk.csv')
    args = parser.parse_args()
    convert(args.workbook, args.output)
