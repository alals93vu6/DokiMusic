import ctypes
import importlib.util
import json
from pathlib import Path
import random
import runpy
import sys
import tempfile
import unittest
from unittest.mock import patch

APP = Path(__file__).resolve().parents[2] / 'outputs' / 'KeyScore'
sys.path.insert(0, str(APP))
from arrangement import arrange
from exporter import generate


def validate_events(result, limit):
    held = set()
    last = -1
    for t, release, press in result['events']:
        assert t >= last
        assert set(release) <= held
        held.difference_update(release)
        assert not (held & set(press))
        held.update(press)
        assert len(held) <= limit
        last = t
    assert not held


class Tests(unittest.TestCase):
    def test_chord_and_independent_durations(self):
        r = arrange([[0, 3, 60, .9], [0, 2, 64, .8], [0, 1, 67, .7]], {})
        self.assertEqual(r['events'][0], [0, [], ['A', 'D', 'G']])
        self.assertEqual(r['events'][1], [1, ['G'], []])
        validate_events(r, 8)

    def test_same_key_restrike(self):
        r = arrange([[0, 3, 60, .9], [1, 2, 60, .8]], {})
        self.assertIn([.975, ['A'], []], r['events'])
        self.assertIn([1, [], ['A']], r['events'])
        validate_events(r, 8)

    def test_mapping_and_skip(self):
        r = arrange([[0, 1, 48, .8], [1, 2, 61, .8]], {'accidental':'nearest'})
        self.assertEqual(r['stats']['octave_shifted'], 1)
        self.assertEqual(r['stats']['approximated'], 1)
        r = arrange([[0, 1, 48, .8], [1, 2, 61, .8]], {'accidental':'skip'})
        self.assertEqual(r['stats']['skipped'], 1)

    def test_random_polyphony_and_collisions(self):
        rng = random.Random(13)
        notes = []
        for _ in range(250):
            s = rng.randrange(100)/10
            notes.append([s, s+rng.uniform(.1, 3), rng.randrange(36,100), rng.random()])
        for mode in ('piano', 'cello'):
            for limit in (1, 3, 8):
                r = arrange(notes, {'mode':mode, 'max_voices':limit})
                validate_events(r, limit)

    def test_bad_settings_and_empty(self):
        for options in ({'speed':0}, {'root':float('nan')}, {'max_voices':9}, {'countdown':2}, {'mode':'x'}):
            with self.assertRaises(ValueError): arrange([[0, 1, 60, .8]], options)
        with self.assertRaises(ValueError): arrange([], {})

    def test_export_escaping_and_playback_cleanup(self):
        title = "Music'); raise Exception('injected') #\n曲目.mp3"
        result = arrange([[0, 1, 60, .8], [0, .3, 64, .9], [.4, .8, 67, .7]], {})
        source = generate(title, result)
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp)/'song.py'
            path.write_text(source, encoding='utf-8')
            m = runpy.run_path(str(path), run_name='validation')
        self.assertEqual(m['SONG']['title'], title)
        m['SONG']['countdown'] = 0
        class Fn:
            def __init__(self, fn): self.fn=fn
            def __call__(self, *args): return self.fn(*args)
        class Clock:
            value=0
            def sleep(self, x): self.value += x
            def perf_counter(self): return self.value
        for stop in (False, True):
            active=set()
            clock=Clock()
            def send(count, items, size):
                for item in items:
                    if item.ki.dwFlags & 2: active.discard(item.ki.wScan)
                    else: active.add(item.ki.wScan)
                return count
            class Win:
                SendInput=Fn(send)
                GetAsyncKeyState=Fn(lambda key: 0)
                GetForegroundWindow=Fn(lambda: 2 if stop and clock.value>.2 else 1)
            with patch('ctypes.WinDLL', return_value=Win()), patch.dict(m['play'].__globals__, {'time':clock}):
                if stop:
                    with self.assertRaisesRegex(RuntimeError, 'focus'): m['play']()
                else: m['play']()
            self.assertFalse(active)


if __name__ == '__main__':
    unittest.main(verbosity=2)
