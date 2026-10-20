"""Synthetic county chunks: preserve all voters, replacements, and privacy."""
import csv
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import precinct_scores as scores


class ScorePartTests(unittest.TestCase):
    def setUp(self):
        self.settings=json.loads((ROOT/'config/settings.json').read_text())
        self.voters={'Travis':[{'vuid':f'100000000{i}','precinct':'140','first_name':f'Voter{i}','last_name':'Synthetic'} for i in range(1,4)]}

    def write(self,root,name,rows,van=False):
        folder=Path(root)/'inbox/scores';folder.mkdir(parents=True,exist_ok=True)
        s=io.StringIO(newline='');w=csv.writer(s,delimiter='\t' if van else ',')
        w.writerow(['PrecinctName','Voter File VANID','FirstName','LastName','26:_Dem_Support'] if van else ['Prec','STID','First','Last','Score'])
        w.writerows(rows);p=folder/name;p.write_bytes(s.getvalue().encode('utf-16' if van else 'utf-8'));return p

    def publish(self,root):
        errors=scores.publish(Path(root),Path(root)/'inbox',self.settings,'2026-10-20',self.voters)
        return errors,json.loads((Path(root)/'docs/data/precinct_scores.json').read_text())

    def test_parts_merge_shared_precinct_and_r2_changes_only_one_part(self):
        with tempfile.TemporaryDirectory() as temp:
            self.write(temp,'travis__2026-10-20__part-01__scores.csv',[['140','1000000001','Voter1','Synthetic','20']])
            self.write(temp,'travis__2026-10-20__part-02__scores.csv',[['140','1000000002','Voter2','Synthetic','80']])
            errors,data=self.publish(temp);self.assertFalse(errors)
            self.assertEqual(data['rows'][0]['mean_score'],50);self.assertEqual(data['rows'][0]['scored_count'],2)
            self.write(temp,'travis__2026-10-20__part-01__scores__r2.csv',[['140','1000000001','Voter1','Synthetic','-20']])
            errors,data=self.publish(temp);self.assertFalse(errors)
            self.assertEqual(data['rows'][0]['mean_score'],30)
            self.assertEqual(data['rows'][0]['scored_count'],2)

    def test_latest_batch_replaces_all_old_parts(self):
        with tempfile.TemporaryDirectory() as temp:
            self.write(temp,'travis__2026-10-19__part-01__scores.csv',[['140','1000000001','Voter1','Synthetic','20']])
            self.write(temp,'travis__2026-10-19__part-02__scores.csv',[['140','1000000002','Voter2','Synthetic','80']])
            self.write(temp,'travis__2026-10-20__part-01__scores.csv',[['140','1000000003','Voter3','Synthetic','-50']])
            errors,data=self.publish(temp);self.assertFalse(errors)
            self.assertEqual(data['rows'][0]['mean_score'],-50);self.assertEqual(data['rows'][0]['scored_count'],1)

    def test_van_ids_deduplicate_across_parts_and_conversion_matches(self):
        with tempfile.TemporaryDirectory() as temp:
            row=['140','900001','Voter1','Synthetic','75']
            self.write(temp,'travis__2026-10-20__part-north__dnc-scores.txt',[row],van=True)
            self.write(temp,'travis__2026-10-20__part-south__dnc-scores.txt',[row,['140','900002','Voter2','Synthetic','25']],van=True)
            errors,data=self.publish(temp);self.assertFalse(errors)
            self.assertEqual(data['rows'][0]['mean_score'],0);self.assertEqual(data['rows'][0]['scored_count'],2)
            public=json.dumps(data)
            for private in ('900001','Voter1','Synthetic'):self.assertNotIn(private,public)

    def test_conflicting_overlap_preserves_prior_as_stale(self):
        with tempfile.TemporaryDirectory() as temp:
            self.write(temp,'travis__2026-10-20__part-01__scores.csv',[['140','1000000001','Voter1','Synthetic','20']])
            self.publish(temp)
            self.write(temp,'travis__2026-10-20__part-02__scores.csv',[['140','1000000001','Voter1','Synthetic','80']])
            errors,data=self.publish(temp);self.assertTrue(errors)
            self.assertEqual(data['rows'][0]['mean_score'],20);self.assertEqual(data['rows'][0]['status'],'stale')

    def test_mixing_complete_and_parts_same_date_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            row=['140','1000000001','Voter1','Synthetic','20']
            self.write(temp,'travis__2026-10-20__scores.csv',[row])
            self.write(temp,'travis__2026-10-20__part-01__scores.csv',[row])
            errors,data=self.publish(temp);self.assertTrue(errors);self.assertEqual(data['rows'],[])


if __name__=='__main__':unittest.main()
