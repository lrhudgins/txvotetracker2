"""VAN adapter fixtures are synthetic; no uploaded identities are included."""
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
import folder_inputs


class VanScoreTests(unittest.TestCase):
    def write(self,root,rows,encoding='utf-16',extension='txt',headers=None):
        path=Path(root)/('travis__2026-10-20__dnc-scores.'+extension)
        stream=io.StringIO(newline='');writer=csv.writer(stream,delimiter='\t')
        writer.writerow(headers or ['Voter File VANID','LastName','FirstName','PrecinctName','26:_Dem_Support','26:clarity_turnout','DNC_Education'])
        writer.writerows(rows);path.write_bytes(stream.getvalue().encode(encoding));return path

    def test_utf16_tsv_democratic_support_only_and_all_conversion_endpoints(self):
        with tempfile.TemporaryDirectory() as temp:
            p=self.write(temp,[['900001','Synthetic','One','0140','0','88','77'],
                               ['900002','Synthetic','Two','140','50','88','77'],
                               ['900003','Synthetic','Three','140','100','88','77'],
                               ['900004','Synthetic','Four','140','','88','77']])
            info=scores.NAME.fullmatch(p.name).groupdict()
            groups,report=scores.read_file(p,info)
            self.assertEqual([r['score'] for r in groups['140']],[-100,0,100,None])
            self.assertTrue(all(r['vuid']=='' for r in groups['140']))
            self.assertEqual(report['score_conversion'],'2 * score - 100')

    def test_utf8_utf16le_without_bom_and_cp1252(self):
        for enc in ['utf-8-sig','utf-16-le','cp1252']:
            with self.subTest(enc=enc),tempfile.TemporaryDirectory() as temp:
                p=self.write(temp,[['900001','Synthetíc','One','140','25','88','77']],encoding=enc,extension='tsv')
                groups,_=scores.read_file(p,{'scale':'dnc'})
                self.assertEqual(groups['140'][0]['score'],-50)

    def test_bad_support_does_not_use_other_numeric_fields(self):
        with tempfile.TemporaryDirectory() as temp:
            for value in ['-1','101','NaN','not available']:
                p=self.write(temp,[['900001','Synthetic','One','140',value,'88','77']])
                with self.assertRaises(ValueError):scores.read_file(p,{'scale':'dnc'})
            p=self.write(temp,[['900001','Synthetic','One','140','88']],headers=['Voter File VANID','LastName','FirstName','PrecinctName','DNC_Education'])
            with self.assertRaisesRegex(ValueError,'DNC input needs'):scores.read_file(p,{'scale':'dnc'})

    def test_native_score_is_unchanged_and_filename_marker_is_required(self):
        with tempfile.TemporaryDirectory() as temp:
            p=Path(temp)/'travis__2026-10-20__scores.csv'
            p.write_text('Prec,First,Last,Score\n140,Synthetic,One,50\n')
            groups,_=scores.read_file(p,{'scale':None});self.assertEqual(groups['140'][0]['score'],50)
            p=self.write(temp,[['900001','Synthetic','One','140','50','88','77']])
            with self.assertRaisesRegex(ValueError,'dnc-scores'):scores.read_file(p,{'scale':None})

    def test_one_unidentifiable_scored_row_does_not_reject_valid_van_rows(self):
        with tempfile.TemporaryDirectory() as temp:
            p=self.write(temp,[['900001','Synthetic','One','0069','91.61','88','77'],
                               ['900002','','','0069','50','88','77'],
                               ['900002','Synthetic','Two','0069','50','88','77']])
            groups,report=scores.read_file(p,{'scale':'dnc'})
            self.assertEqual(len(groups['69']),2)
            self.assertAlmostEqual(groups['69'][0]['score'],83.22)
            self.assertEqual(report['unidentifiable_rows_ignored'],1)
            # VAN ID must not be mistaken for a state ID when names are absent.
            self.assertEqual(groups['69'][0]['vuid'],'')

    def test_truncated_rows_are_skipped_reported_and_never_scored(self):
        with tempfile.TemporaryDirectory() as temp:
            p=self.write(temp,[['900001','Synthetic','One','140','75','88','77'],['900002','Synthetic','Two','140']])
            groups,report=scores.read_file(p,{'scale':'dnc'})
            self.assertEqual(len(groups['140']),1);self.assertEqual(groups['140'][0]['score'],50)
            self.assertEqual(report['incomplete_rows_ignored'],1)

    def test_private_inbox_discovers_txt_watches_and_publishes_only_matched_normalized_mean(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);folder=root/'inbox/scores';folder.mkdir(parents=True)
            self.write(folder,[['900001','Synthetic','One','140','75','88','77'],['900002','Synthetic','Nonvoter','140','0','88','77']])
            settings=json.loads((ROOT/'config/settings.json').read_text())
            files=scores.collect(folder,settings)
            self.assertEqual(files['Travis'][0]['scale'],'dnc')
            self.assertTrue(folder_inputs.stamp(root/'inbox'))
            self.assertEqual(folder_inputs.scan(root/'inbox',settings),{})
            voters={'Travis':[{'vuid':'1000000001','precinct':'140','first_name':'One','last_name':'Synthetic'}]}
            self.assertFalse(scores.publish(root,root/'inbox',settings,'2026-10-20',voters))
            payload=json.loads((root/'docs/data/precinct_scores.json').read_text())
            self.assertEqual(payload['rows'][0]['mean_score'],50)
            self.assertEqual(payload['rows'][0]['name_match_count'],1)
            public=''.join(p.read_text() for p in (root/'docs').rglob('*') if p.is_file())
            for private in ['Synthetic','900001','900002','1000000001','Nonvoter']:self.assertNotIn(private,public)


if __name__=='__main__':unittest.main()
