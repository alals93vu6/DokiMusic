"""Signal regressions; no live keyboard input."""
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import numpy as np

APP = Path(__file__).resolve().parents[2]/'outputs'/'KeyScore'
sys.path.insert(0,str(APP))
from isolation import SignalEvidence, AudioSepIsolationService
from isolation_profiles import get_profile
from arrangement import settings


class Tests(unittest.TestCase):
    def evidence(self, amplitude=1.):
        t = np.arange(44100)/22050
        audio = (amplitude*.2*np.sin(2*np.pi*220*t)).astype('float32')
        return SignalEvidence(audio,audio,np.zeros_like(audio),get_profile('cello'))

    def test_continuous_cello_and_new_attack(self):
        e = self.evidence()
        notes = [[.1,.6,57,.8,None],[.6,1.2,57,.8,None]]
        self.assertEqual(len(e.consolidate(notes)),1)
        idx=round(220*e.nfft/e.sr);frame=round(.6*e.sr/e.hop)
        e.target[idx-1:idx+2,frame:frame+4] *= 3
        self.assertEqual(len(e.consolidate(notes)),2)

    def test_evidence_and_out_of_bounds(self):
        e=self.evidence()
        self.assertTrue(e.assess(.1,1.2,57,.8)[0])
        self.assertFalse(e.assess(50,51,57,.8)[0])
        self.assertFalse(e.assess(.1,.12,57,.8)[0])
        e.competitor=e.target*10
        self.assertFalse(e.assess(.1,1.2,57,.8)[0])

    def test_missing_model_is_explicit_error(self):
        with tempfile.TemporaryDirectory() as temp, patch('isolation.MODEL_DIR',Path(temp)):
            with self.assertRaisesRegex(RuntimeError,'未安裝完整'):
                AudioSepIsolationService()

    def test_settings(self):
        self.assertEqual(settings({})['isolation'],'mixed')
        for name in ('isolation','strictness','device'):
            with self.assertRaises(ValueError):settings({name:'invalid'})


if __name__=='__main__':unittest.main(verbosity=2)
