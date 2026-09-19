import sys
from pathlib import Path
import unittest
import json
import base64
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'outputs'/'KeyScore'))
from score import read_score, validate_score, score_result, MARKER, PREFIX
from exporter import generate
from arrangement import arrange

class Tests(unittest.TestCase):
    def test_four_instrument_round_trip(self):
        for mode in ('piano', 'cello', 'violin', 'harp'):
            with self.subTest(mode=mode):
                data=self.sample()
                data['settings']['mode']=mode
                source=generate('test',score_result(data))
                restored=read_score(source)
                self.assertEqual(restored['settings']['mode'],mode)
                self.assertEqual(restored['notes'][0]['s'],1)
                self.assertEqual(restored['notes'][0]['p'],60)

    def sample(self):
        return dict(version=1,title='測試',settings={},notes=[dict(s=1,e=2,k='A',v=.8),dict(s=1,e=3,k='D',v=.7)])
    def test_round_trip_preserves_events_and_leading_silence(self):
        result=score_result(self.sample())
        source=generate('測試',result)
        self.assertEqual(source.splitlines()[1],MARKER)
        self.assertEqual(score_result(read_score(source))['events'],result['events'])
        self.assertEqual(read_score(source)['notes'][0]['s'],1)
        compile(source,'export','exec')
    def test_existing_analysis_round_trip(self):
        r=arrange([[0,2,60,.8],[0,1,64,.9],[2,3,67,.8]],{})
        self.assertEqual(score_result(read_score(generate('曲',r)))['events'],r['events'])
    def test_import_never_executes_code(self):
        source=generate('曲',score_result(self.sample()))
        data=read_score('\n'.join(source.splitlines()[:3])+"\nraise RuntimeError('must not execute')")
        self.assertEqual(len(data['notes']),2)
    def test_reject_invalid(self):
        for mutate in [lambda d:d.update(version=2),lambda d:d.update(notes=[]),lambda d:d['notes'][0].update(s=float('nan')),lambda d:d['notes'][0].update(k='X'),lambda d:d['notes'][0].update(e=1.01),lambda d:d['notes'].append(dict(s=1.5,e=3,k='A',v=.8))]:
            d=self.sample();mutate(d)
            with self.assertRaises(ValueError):validate_score(d)
        for text in ['print(1)','\n'+MARKER+'\n'+PREFIX+'broken']:
            with self.assertRaises(ValueError):read_score(text)
    def test_polyphony(self):
        d=self.sample();d['notes']=[dict(s=0,e=1,k=k,v=.8) for k in 'ASDFGHJQW']
        with self.assertRaises(ValueError):validate_score(d)
    def test_edits_roundtrip(self):
        d=self.sample();d['notes'][0].update(s=0,e=4);d['notes'].pop();d['notes'].append(dict(s=5,e=6,k='I',v=.9))
        s=read_score(generate('編輯',score_result(d)))
        self.assertEqual([(n['s'],n['e'],n['k']) for n in s['notes']],[(0,4,'A'),(5,6,'I')])

if __name__=='__main__':unittest.main(verbosity=2)
