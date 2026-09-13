import json
from pathlib import Path
import subprocess
import sys
import time

import imageio_ffmpeg
import numpy as np
import soundfile as sf

WORK = Path(__file__).resolve().parent
APP = WORK.parents[1] / 'outputs' / 'KeyScore'
sys.path.insert(0, str(APP))
from app import Api


def make_demo():
    sr = 22050
    audio = np.zeros(sr * 10, dtype=np.float32)
    def note(start, duration, pitch, amp=.18):
        t = np.arange(round(duration * sr)) / sr
        freq = 440 * 2 ** ((pitch - 69) / 12)
        envelope = np.minimum(t / .008, 1) * np.minimum((duration-t)/.04,1) * np.exp(-t*1.2)
        tone = sum(np.sin(2*np.pi*freq*i*t) / i**2 for i in range(1,5))
        pos=round(start*sr)
        audio[pos:pos+len(t)] += (amp * envelope * tone).astype(np.float32)
    for i,pitch in enumerate([72,76,79,76,74,77,81,77,72,76,79,84]):
        note(.5+i*.6,.5,pitch)
    for onset,chord in [(0.5,[60,64,67]),(2.9,[62,65,69]),(5.3,[60,64,67])]:
        for pitch in chord: note(onset,2.2,pitch,.12)
    wav=WORK/'demo_source.wav'; sf.write(wav,audio,sr)
    (APP/'assets').mkdir(exist_ok=True)
    dest=APP/'assets'/'demo.mp3'
    subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(),'-nostdin','-v','error','-y','-i',str(wav),'-codec:a','libmp3lame','-q:a','3',str(dest)],check=True)
    return dest


def await_done(api, limit=240):
    start=time.monotonic(); last=''
    while time.monotonic()-start<limit:
        state=api.get_status()
        if state['message']!=last:
            print(state['status'],state['progress'],state['message'],flush=True);last=state['message']
        if state['status']!='running':return state
        time.sleep(.5)
    api.cancel()
    raise AssertionError('Analysis timeout')


def main():
    make_demo()
    api=Api()
    assert api.choose_demo()['ok']
    assert api.analyze({'mode':'piano','isolation':'solo'})['ok']
    state=await_done(api)
    assert state['status']=='done',state
    r=state['result']
    assert len(r['notes'])>=6 and r['stats']['peak_voices']>=2,r['stats']
    print('PIANO',json.dumps(r['stats']),flush=True)
    (WORK/'demo_result.json').write_text(json.dumps(r),encoding='utf-8')
    class SaveWindow:
        def create_file_dialog(self,*args,**kwargs):return (str(WORK/'exported_demo.py'),)
    api._window=SaveWindow()
    saved=api.save_python()
    assert saved['ok'],saved
    subprocess.run([sys.executable,saved['path'],'--check'],check=True)
    assert api.analyze({'mode':'piano','isolation':'solo','speed':.5,'max_voices':3})['ok']
    slow=await_done(api)
    assert slow['status']=='done'
    assert slow['result']['stats']['duration']>r['stats']['duration']*1.8
    assert slow['result']['stats']['peak_voices']<=3
    assert api.analyze({'mode':'cello','isolation':'solo'})['ok']
    cello=await_done(api)
    assert cello['status']=='done',cello
    assert cello['result']['stats']['peak_voices']==1
    print('CELLO',json.dumps(cello['result']['stats']),flush=True)
    # Cancel a real worker and ensure the UI can accept another selection.
    api.choose_demo();api.analyze({'mode':'piano'});api.cancel()
    cancelled=await_done(api)
    assert cancelled['status']=='cancelled',cancelled
    assert api.choose_demo()['ok']
    print('PASS: real MP3 decode/transcription, both modes, cached rearrangement, Python export and cancellation. No keys sent.',flush=True)


if __name__=='__main__':main()
