"""A-H before/after note metrics on sample-based rendered, known-MIDI stems.

This is a controlled regression set, not a real-recording accuracy claim.
"""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import time

WORK=Path(__file__).resolve().parent
ROOT=WORK.parents[1]
APP=ROOT/'outputs'/'KeyScore'
BENCH=WORK/'benchmark'
os.environ['NUMBA_CACHE_DIR']=str(WORK/'data'/'numba')
os.environ['NUMBA_NUM_THREADS']='4'
os.environ['OMP_NUM_THREADS']='4'
os.environ['HF_HUB_OFFLINE']='1'
sys.path.insert(0,str(APP))

import numpy as np
import soundfile as sf
from scipy.optimize import linear_sum_assignment
import imageio_ffmpeg


def render(notes,preset,drums=False,duration=14):
    import tinysoundfont
    sr=32000
    synth=tinysoundfont.Synth(samplerate=sr)
    ident=synth.sfload(str(BENCH/'GeneralUser-GS.sf2'))
    synth.program_select(0,ident,0,preset,is_drums=drums)
    events=[]
    for s,e,p,v in notes:
        events.extend([(round(s*sr),1,p,v),(round(e*sr),0,p,v)])
    events.sort()
    out=[];pos=0
    for sample,down,p,v in events:
        if sample>pos:
            out.append(np.frombuffer(synth.generate(sample-pos),dtype=np.float32).reshape(-1,2).mean(axis=1).copy())
            pos=sample
        if down:synth.noteon(0,p,v)
        else:synth.noteoff(0,p)
    out.append(np.frombuffer(synth.generate(round(duration*sr)-pos),dtype=np.float32).reshape(-1,2).mean(axis=1).copy())
    wave=np.concatenate(out)
    return wave*.075/max(float(np.sqrt(np.mean(wave**2))),1e-8)


def fixtures(holdout=False):
    piano=[];cello=[];drums=[]
    if not holdout:
        pitches=[60,64,67,72,65,69,74,67,64,71]
        for i,p in enumerate(pitches):
            s=.6+i*1.05;piano.append([s,s+.72,p,85])
            if i in (0,3,6):piano.extend([[s,s+.9,p-12,68],[s,s+.8,p-5,72]])
        for i,p in enumerate([55,62,57,65,59]):
            s=.85+i*2.2;cello.append([s,s+1.85,p,85])
    else:
        for i,p in enumerate([67,60,65,69,64,62,71,67]):
            s=.7+i*1.25;piano.extend([[s,s+.6,p,76],[s,s+.8,p-12,65]])
        for i,p in enumerate([60,65,62,57,64,59]):
            s=.5+i*1.8;cello.append([s,s+1.55,p,90])
    for i in range(28):
        s=.4+i*.4;drums.append([s,s+.09,42,68])
        if i%2==0:drums.append([s,s+.15,36 if i%4==0 else 38,92])
    stems={'piano':render(piano,0),'cello':render(cello,42),'drums':render(drums,0,True)}
    for name,audio in stems.items():sf.write(BENCH/f'{"holdout_" if holdout else ""}{name}_stem.wav',audio,32000,subtype='FLOAT')
    cases=[('A','piano',['piano']),('B','piano',['piano','drums']),('C','piano',['piano','cello']),('D','piano',['piano','cello','drums']),
           ('E','cello',['cello']),('F','cello',['cello','drums']),('G','cello',['cello','piano']),('H','cello',['cello','piano','drums'])]
    made=[]
    for letter,target,names in cases:
        name=('holdout_' if holdout else '')+letter
        audio=sum(stems[x]*(1.35 if holdout and x!=target else 1) for x in names)
        audio*=min(1,.95/max(np.max(np.abs(audio)),1e-8))
        wav=BENCH/f'{name}.wav';mp3=BENCH/f'{name}.mp3'
        sf.write(wav,audio,32000)
        subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(),'-nostdin','-v','error','-y','-i',str(wav),'-codec:a','libmp3lame','-b:a','192k',str(mp3)],check=True)
        made.append(dict(case=name,target=target,instruments=names,path=str(mp3),truth=piano if target=='piano' else cello))
    (BENCH/f'{"holdout_" if holdout else ""}fixtures.json').write_text(json.dumps(made,indent=2),encoding='utf-8')
    return made


def metrics(truth, predicted, duration=14):
    # Match exact MIDI pitch, onset within 150 ms. Offsets evaluated separately.
    costs=np.full((len(truth),len(predicted)),1e6)
    for i,a in enumerate(truth):
        for j,b in enumerate(predicted):
            if a[2]==b[2] and abs(a[0]-b[0])<=.15:costs[i,j]=abs(a[0]-b[0])
    rows,cols=linear_sum_assignment(costs)
    pairs=[(i,j) for i,j in zip(rows,cols) if costs[i,j]<1e5]
    tp=len(pairs);fp=len(predicted)-tp;fn=len(truth)-tp
    def frames(notes):
        out=np.zeros((round(duration/.02)+1,128),dtype=bool)
        for s,e,p,*_ in notes:
            out[max(0,round(s/.02)):min(len(out),round(e/.02)),int(p)]=True
        return out
    ref,est=frames(truth),frames(predicted)
    frame_tp=np.sum(ref&est)
    frame_precision=float(frame_tp/max(1,np.sum(est)))
    frame_recall=float(frame_tp/max(1,np.sum(ref)))
    return dict(true_positive=tp,false_positive=fp,missed=fn,notes=len(predicted),
        precision=round(tp/max(1,len(predicted)),4),recall=round(tp/max(1,len(truth)),4),
        frame_pitch_precision=round(frame_precision,4),frame_pitch_recall=round(frame_recall,4),
        onset_mae_ms=round(np.mean([abs(truth[i][0]-predicted[j][0]) for i,j in pairs])*1000,1) if pairs else None,
        duration_mae_ms=round(np.mean([abs((truth[i][1]-truth[i][0])-(predicted[j][1]-predicted[j][0])) for i,j in pairs])*1000,1) if pairs else None)


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--holdout',action='store_true');parser.add_argument('--cases',default='ABCDEFGH');parser.add_argument('--reuse',action='store_true')
    args=parser.parse_args();BENCH.mkdir(exist_ok=True)
    fixture_file=BENCH/f'{"holdout_" if args.holdout else ""}fixtures.json'
    cases=json.loads(fixture_file.read_text()) if args.reuse and fixture_file.exists() else fixtures(args.holdout)
    from worker import transcribe
    results=[]
    for case in cases:
        if case['case'][-1] not in args.cases:continue
        entry={k:case[k] for k in ('case','target','instruments')}
        for route in ('solo','mixed'):
            dest=BENCH/f'{case["case"]}_{route}.json'
            print('BENCH',case['case'],route,flush=True);start=time.perf_counter()
            try:
                if not (args.reuse and dest.exists() and route == 'solo'):transcribe(case['path'],case['target'],dest,route)
                result=json.loads(dest.read_text(encoding='utf-8'))
                entry[route]=metrics(case['truth'],result['notes'])
                entry[route]['isolation']=result.get('isolation')
            except ValueError as error:
                entry[route]=metrics(case['truth'],[])
                entry[route]['error']=str(error)
            entry[route]['wall_seconds']=round(time.perf_counter()-start,2)
        print('METRICS',json.dumps(entry),flush=True);results.append(entry)
        (BENCH/f'{"holdout_" if args.holdout else ""}metrics.json').write_text(json.dumps(results,indent=2),encoding='utf-8')


if __name__=='__main__':main()
