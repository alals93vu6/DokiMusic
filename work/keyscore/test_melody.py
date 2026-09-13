import sys
from pathlib import Path
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'outputs'/'KeyScore'))
from melody import extract_melody
from arrangement import arrange
from score import read_score, score_result
from exporter import generate

class Tests(unittest.TestCase):
    def test_solo_repeated_notes_and_rests(self):
        notes=[[0,.5,72,.9],[.5,1,72,.9],[2,3,74,.8]]
        self.assertEqual(extract_melody(notes),notes)
    def test_chords_and_no_tail_resurrection(self):
        notes=[[0,3,48,.6],[0,2,60,.6],[0,.5,72,.9],[.6,1.2,74,.9]]
        out=extract_melody(notes)
        self.assertEqual([n[2] for n in out],[72,74])
        self.assertEqual(out[-1][1],1.2)
    def test_continuity_not_always_highest(self):
        notes=[[0,1,72,.9],[1,2,74,.9],[1,2,88,.7],[2,3,76,.9]]
        self.assertEqual([n[2] for n in extract_melody(notes)],[72,74,76])
    def test_selection_before_octave_folding(self):
        notes=[[0,1,60,.7],[0,1,84,.95],[1,2,62,.7],[1,2,86,.95]]
        r=arrange(notes,{'texture':'melody'})
        self.assertEqual(r['stats']['peak_voices'],1)
        self.assertEqual(r['stats']['melody_removed'],2)
        self.assertEqual(r['settings']['max_voices'],1)
        self.assertEqual(score_result(read_score(generate('主旋律',r)))['events'],r['events'])
        self.assertGreater(arrange(notes,{})['stats']['peak_voices'],1)
    def test_weak_accompaniment_during_sustain(self):
        self.assertEqual(len(extract_melody([[0,2,72,.9],[.5,1,48,.4]])),1)

if __name__=='__main__':unittest.main(verbosity=2)
