"""Synthetic statewide rosters only. Never package actual voter records."""
import csv
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import update as u
import folder_inputs as folders
import sos_rosters as sos
from voter_matching import match_precincts


class SosRosterTests(unittest.TestCase):
    def setUp(self):
        self.settings=json.loads((ROOT/'config/settings.json').read_text())

    def setup_root(self,root):
        (root/'config').mkdir()
        for name in ('settings.json','county_sources.csv','precinct_crosswalk.csv'):
            (root/'config'/name).write_bytes((ROOT/'config'/name).read_bytes())
        (root/'inbox').mkdir()

    def write(self,folder,rows,day=20,name=None):
        p=folder/(name or f'STATEWIDE.2026 NOVEMBER GENERAL ELECTION.EarlyVoting.10_{day}_2026.csv')
        with p.open('w',newline='') as f:
            w=csv.writer(f);w.writerow(['COUNTY','VOTER_NAME','ID_VOTER','VOTING_METHOD','PRECINCT']);w.writerows(rows)
        return p

    def test_original_and_explicit_filenames_validate_election_and_dates(self):
        meta=sos.identify('STATEWIDE.2026 NOVEMBER GENERAL ELECTION.EarlyVoting.10_20_2026.csv',self.settings)
        self.assertEqual(meta['asof'],'2026-10-20');self.assertEqual(meta['coverage'],'daily')
        meta=sos.identify('statewide__2026-11-03__2026-10-20__mixed__cumulative__r2.csv',self.settings)
        self.assertEqual(meta['coverage'],'cumulative');self.assertEqual(meta['revision'],2)
        with self.assertRaises(ValueError):sos.identify('STATEWIDE.2025 NOVEMBER GENERAL ELECTION.EarlyVoting.10_20_2025.csv',self.settings)

    def test_county_split_filters_outside_counties_and_normalizes_fields(self):
        with tempfile.TemporaryDirectory() as temp:
            p=self.write(Path(temp),[['BRAZOS','SYNTHETIC, ONE','1000000001','IN-PERSON','0069'],
                                     ['SAN JACINTO','SYNTHETIC, TWO','1000000002','MAIL-IN','001'],
                                     ['HARRIS','OUTSIDE SYNTHETIC','invalid','unknown','1']])
            records,_=sos.load(p,self.settings,'2026-10-20')
            self.assertEqual(set(records),{'Brazos','San Jacinto'})
            row=records['Brazos']['records'][0]
            self.assertEqual(row['precinct'],'69');self.assertEqual(row['mode'],'in_person')
            self.assertEqual(row['vote_date'],'2026-10-20');self.assertEqual(row['date_basis'],'report_date')
            self.assertEqual(records['San Jacinto']['records'][0]['mode'],'mail')

    def test_new_exports_union_and_deduplicate_prior_observations_with_no_network(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);self.setup_root(root)
            self.write(root/'inbox',[['BRAZOS','SYNTHETIC, ONE','1000000001','IN-PERSON','69']],day=19)
            self.write(root/'inbox',[['BRAZOS','SYNTHETIC, ONE','1000000001','IN-PERSON','69'],
                                     ['BRAZOS','SYNTHETIC, TWO','1000000002','MAIL-IN','69']])
            with patch.object(u,'fetch',side_effect=AssertionError('Network prohibited')):
                self.assertEqual(u.run(root,inbox=root/'inbox'),0)
            data=json.loads((root/'docs/data/latest.json').read_text())
            county=next(r for r in data['counties'] if r['county']=='Brazos')
            self.assertEqual(county['total'],2);self.assertEqual(county['in_person'],1);self.assertEqual(county['mail'],1)
            public=''.join(p.read_text() for p in (root/'docs').rglob('*') if p.is_file())
            for private in ('1000000001','1000000002','SYNTHETIC'):self.assertNotIn(private,public)

    def test_statewide_default_ignores_conflicting_county_rosters(self):
        with tempfile.TemporaryDirectory() as temp:
            folder=Path(temp)
            self.write(folder,[['BRAZOS','SYNTHETIC, ONE','1000000001','IN-PERSON','69'],
                               ['BRAZOS','SYNTHETIC, TWO','1000000002','IN-PERSON','69']])
            (folder/'brazos__2026-11-03__2026-10-20__in-person__daily.csv').write_text('VUID,Precinct\n1000000001,70\n1000000003,69\n')
            files=folders.scan(folder,self.settings)
            source={'county':'Brazos','adapter':'brazos_index','columns_json':'{}'}
            rows,_,notes=folders.read_county(files['Brazos'],source,u.parse_document,u.parse_travis_archive)
            self.assertEqual(len(rows),2)
            self.assertEqual({r['precinct'] for r in rows},{'69'})
            self.assertTrue(any('statewide-first' in n for n in notes))

    def test_statewide_travis_does_not_parse_legacy_travis_archive(self):
        with tempfile.TemporaryDirectory() as temp:
            folder=Path(temp)
            self.write(folder,[['TRAVIS','SYNTHETIC, ONE','1000000001','IN-PERSON','101']])
            (folder/'travis__2026-11-03__2026-10-19__mixed__archive.zip').write_bytes(b'invalid archive must never be read')
            files=folders.scan(folder,self.settings)
            source={'county':'Travis','adapter':'roster','columns_json':'{}'}
            with patch.object(u,'parse_travis_archive',side_effect=AssertionError('County archive must be ignored')):
                rows,_,_=folders.read_county(files['Travis'],source,u.parse_document,u.parse_travis_archive)
            self.assertEqual(len(rows),1)

    def test_revision_and_explicit_cumulative_replace_superseded_rows(self):
        with tempfile.TemporaryDirectory() as temp:
            folder=Path(temp)
            self.write(folder,[['BRAZOS','SYNTHETIC, ONE','1000000001','IN-PERSON','69']],day=19)
            self.write(folder,[['BRAZOS','SYNTHETIC, TWO','1000000002','IN-PERSON','69']],name='statewide__2026-11-03__2026-10-20__mixed__cumulative__r2.csv')
            files=folders.scan(folder,self.settings)
            source={'county':'Brazos','adapter':'brazos_index','columns_json':'{}'}
            rows,_,_=folders.read_county(files['Brazos'],source,u.parse_document,u.parse_travis_archive)
            self.assertEqual([r['vuid'] for r in rows],['1000000002'])

    def test_bad_target_county_is_withheld_without_blocking_valid_counties(self):
        with tempfile.TemporaryDirectory() as temp:
            p=self.write(Path(temp),[['BRAZOS','SYNTHETIC, ONE','bad','IN-PERSON','69'],
                                     ['LEON','SYNTHETIC, TWO','1000000002','MAIL-IN','1']])
            records,_=sos.load(p,self.settings,'2026-10-20')
            self.assertTrue(records['Brazos']['error']);self.assertFalse(records['Leon']['error'])

    def test_van_supplied_middle_name_matches_sos_full_name_exactly(self):
        row={'vuid':'1000000001','precinct':'69','full_name':'SYNTHETIC, PERSON MIDDLE'}
        score={'vuid':'','precinct':'69','score':25,'first_name':'Person','middle_name':'Middle','last_name':'Synthetic'}
        self.assertEqual(match_precincts([row],[score])['69']['name_match_count'],1)
        score['middle_name']='Different'
        self.assertEqual(match_precincts([row],[score])['69']['unmatched_count'],1)


if __name__=='__main__':unittest.main()
