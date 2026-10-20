"""Synthetic records only: verify automatic joins and absence of private output."""
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
import precinct_scores as scores
from voter_matching import match_precincts
import local_update as local
import test_local_update


def voter(uid='1000000001', precinct='101', first='Synthetic', last='Person', **extra):
    return dict(vuid=uid,precinct=precinct,first_name=first,last_name=last,
                district=10,mode='in_person',vote_date='2026-10-19',**extra)


def score(uid='', precinct='101', first='Synthetic', last='Person', value=25):
    return dict(vuid=uid,precinct=precinct,first_name=first,last_name=last,score=value)


class MatchingTests(unittest.TestCase):
    def test_name_case_accents_punctuation_and_full_name_orders(self):
        row=score(first='José',last='O’Neil')
        for v in (voter(first='JOSE',last="O'NEIL"),voter(first='',last='',full_name='ONEIL, JOSE')):
            data=match_precincts([v],[row])['101']
            self.assertEqual(data['name_match_count'],1)
            self.assertEqual(data['values'],[25])

    def test_duplicate_names_and_contradictory_state_ids(self):
        data=match_precincts([voter(),voter('1000000002')],[score()])['101']
        self.assertEqual(data['ambiguous_count'],2);self.assertEqual(data['values'],[])
        data=match_precincts([voter()],[score(),score()])['101']
        self.assertEqual(data['ambiguous_count'],1)
        data=match_precincts([voter()],[score(uid='1000000009')])['101']
        self.assertEqual(data['identifier_conflict_count'],1)

    def test_ids_win_names_require_precinct_and_no_guessed_middle_names(self):
        data=match_precincts([voter()],[score(uid='1000000001',precinct='102',first='Different')])['101']
        self.assertEqual(data['id_match_count'],1)
        self.assertEqual(data['values'],[25])
        self.assertEqual(match_precincts([voter()],[score(precinct='102')])['101']['unmatched_count'],1)
        self.assertEqual(match_precincts([voter()],[score(first='Synthetic Middle')])['101']['unmatched_count'],1)
        self.assertEqual(match_precincts([voter(first='John',last='James')],[score(first='James',last='John')])['101']['unmatched_count'],1)
        self.assertEqual(match_precincts([voter(first='Ann',last='Abe')],[score(first='Anna',last='Be')])['101']['unmatched_count'],1)

    def test_nonvoters_never_enter_average_and_unmatched_is_not_zero(self):
        data=match_precincts([voter(),voter('1000000002',first='Other')],
                            [score(uid='1000000001',value=-100),score(uid='1000000003',first='Nonvoter',value=100)])['101']
        self.assertEqual(data['values'],[-100]);self.assertEqual(data['unmatched_count'],1)
        self.assertEqual(data['early_voter_count'],2)

    def test_only_in_period_cd10_eligible_records_are_sent_to_join(self):
        settings=json.loads((ROOT/'config/settings.json').read_text())
        rows=[voter(),dict(voter('1000000002'),district=37),dict(voter('1000000003'),vote_date='2026-03-03'),
              dict(voter('1000000004'),mode='election_day',vote_date='2026-11-03')]
        eligible=[];u.aggregate(rows,{'county':'Travis'},settings,{},'2026-10-20',eligible)
        self.assertEqual([r['vuid'] for r in eligible],['1000000001'])

    def setup_root(self,root):
        (root/'config').mkdir()
        for name in ('settings.json','county_sources.csv','precinct_crosswalk.csv'):
            (root/'config'/name).write_bytes((ROOT/'config'/name).read_bytes())
        (root/'inbox/scores').mkdir(parents=True)

    def put_scores(self,root,values):
        with (root/'inbox/scores/brazos__2026-10-20__scores.csv').open('w',newline='') as f:
            w=csv.writer(f);w.writerow(['Prec','STID','Score','First','Last'])
            w.writerows([['101','',values[0],'Synthetic','One'],['101','',values[1],'Synthetic','Two']])

    def test_new_rosters_and_score_uploads_automatically_rebuild_join_offline(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);self.setup_root(root);self.put_scores(root,[-100,100])
            roster=root/'inbox/brazos__2026-11-03__2026-10-19__in-person__daily.csv'
            roster.write_text('VUID,Precinct,First Name,Last Name\n1000000001,101,Synthetic,One\n')
            with patch.object(u,'fetch',side_effect=AssertionError('Network prohibited')):
                def read():return json.loads((root/'docs/data/precinct_scores.json').read_text())['rows'][0]
                self.assertEqual(u.run(root,inbox=root/'inbox'),0)
                self.assertEqual(read()['mean_score'],-100)
                roster.write_text(roster.read_text()+'1000000002,101,Synthetic,Two\n')
                self.assertEqual(u.run(root,inbox=root/'inbox'),0)
                self.assertEqual(read()['mean_score'],0)
                self.put_scores(root,[40,80])
                self.assertEqual(u.run(root,inbox=root/'inbox'),0)
                self.assertEqual(read()['mean_score'],60)
                public=''.join(p.read_text() for p in (root/'docs').rglob('*') if p.is_file())
                for private in ('Synthetic','1000000001','1000000002'):
                    self.assertNotIn(private,public)

    def test_missing_and_failed_rosters_and_old_population_migration(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);self.setup_root(root);self.put_scores(root,[20,40])
            settings=json.loads((root/'config/settings.json').read_text())
            output=root/'docs/data/precinct_scores.json'
            def publish(voters=None,failed=None):
                errors=scores.publish(root,root/'inbox',settings,'2026-10-20',voters,failed)
                return errors,json.loads(output.read_text())
            errors,data=publish()
            self.assertFalse(errors);self.assertEqual(data['rows'],[])
            self.assertTrue(any(r.get('status')=='waiting_for_roster' for r in data['diagnostics']))
            errors,data=publish({'Brazos':[voter(first='Synthetic',last='One')]})
            self.assertEqual(data['rows'][0]['mean_score'],20)
            errors,data=publish(failed={'Brazos'})
            self.assertTrue(errors);self.assertEqual(data['rows'][0]['status'],'stale')
            self.assertEqual(data['rows'][0]['mean_score'],20)
            output.write_text(json.dumps({'rows':[{'county':'Brazos','mean_score':99}]}))
            errors,data=publish(failed={'Brazos'})
            self.assertEqual(data['rows'],[])

    def test_vanid_is_not_state_id_and_name_column_is_not_person_name(self):
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'scores.csv'
            path.write_text('Prec,VanId,Score,First,Last,Name\n101,999,25,Synthetic,Person,STREET\n')
            groups,_=scores.read_file(path,{'precinct':None})
            self.assertEqual(groups['101'][0]['vuid'],'')
            self.assertEqual(groups['101'][0]['full_name'],'')
            self.assertEqual(match_precincts([voter()],groups['101'])['101']['name_match_count'],1)

    def test_publisher_blocks_tracked_private_inbox_before_processing(self):
        import subprocess
        with tempfile.TemporaryDirectory() as temp:
            root,_=test_local_update.LocalPublisherTests().prepare(temp)
            (root/'inbox').mkdir();(root/'inbox/private.csv').write_text('synthetic private data')
            subprocess.run(['git','-C',str(root),'add','-f','inbox/private.csv'],check=True,capture_output=True)
            with patch.object(local,'ROOT',root),patch.object(local,'run') as updater:
                with self.assertRaisesRegex(RuntimeError,'Private inbox files are tracked'):
                    local.publish_once(push=True,inbox=root/'inbox')
                updater.assert_not_called()


if __name__=='__main__':unittest.main()
