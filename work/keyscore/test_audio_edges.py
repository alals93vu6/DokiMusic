from pathlib import Path
import json
import os
import subprocess
import sys

import numpy as np
import soundfile as sf
import imageio_ffmpeg

WORK=Path(__file__).resolve().parent
APP=WORK.parents[1]/'outputs'/'KeyScore'
env=os.environ.copy()
env['PYTHONIOENCODING']='utf-8'
env['NUMBA_CACHE_DIR']=str(WORK/'data'/'numba')


def worker(path, name):
    dest=WORK/(name+'.json')
    p=subprocess.run([sys.executable,str(APP/'worker.py'),str(path),'piano',str(dest)],
                     capture_output=True,env=env,text=True,encoding='utf-8',timeout=180)
    return p,dest


audio,sr=sf.read(WORK/'demo_source.wav',dtype='float32')
long=np.tile(audio,4)
t=np.arange(6*sr)/sr
long[28*sr:34*sr]+=(.2*np.sin(2*np.pi*261.6256*t)*np.minimum(t/.02,1)*np.minimum((6-t)/.02,1)).astype(np.float32)
sf.write(WORK/'long.wav',long,sr)
subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(),'-nostdin','-v','error','-y','-i',str(WORK/'long.wav'),str(WORK/'long.mp3')],check=True)
p,dest=worker(WORK/'long.mp3','long_result')
assert p.returncode==0,p.stdout+p.stderr
r=json.loads(dest.read_text())
assert max(n[1] for n in r['notes'])>36
assert all(0<=n[0]<n[1]<=r['duration'] for n in r['notes'])
print('PASS: 40-second MP3 / two inference chunks / notes preserved beyond boundary',flush=True)
sf.write(WORK/'silence.wav',np.zeros(sr),sr)
p,_=worker(WORK/'silence.wav','silence_result')
assert p.returncode!=0 and 'KEYSCORE_ERROR:' in p.stdout
print('PASS: silent audio returns a user-facing error',flush=True)
(WORK/'corrupt.mp3').write_bytes(b'not an audio file')
p,_=worker(WORK/'corrupt.mp3','corrupt_result')
assert p.returncode!=0 and 'KEYSCORE_ERROR:' in p.stdout
print('PASS: invalid MP3 returns a user-facing error',flush=True)
