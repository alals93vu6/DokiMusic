"""Fetch official pinned AudioSep sources/checkpoint, with LFS hash verification."""
import hashlib
import json
from pathlib import Path
import shutil
import time
import requests

WORK = Path(__file__).resolve().parent
APP = WORK.parents[1] / 'outputs' / 'KeyScore'
VENDOR = APP / 'vendor' / 'audiosep'
MODELS = WORK / 'models' / 'audiosep'
VENDOR.mkdir(parents=True, exist_ok=True)
MODELS.mkdir(parents=True, exist_ok=True)
session = requests.Session()


def get_json(url):
    r=session.get(url, timeout=60);r.raise_for_status();return r.json()


def download(url, path, sha=None):
    def digest():
        h = hashlib.sha256()
        with path.open('rb') as f:
            for block in iter(lambda: f.read(4*1024*1024), b''): h.update(block)
        return h.hexdigest()
    if path.exists() and (not sha or digest()==sha):
        return
    temp=path.with_name(path.name+'.part')
    for attempt in range(3):
        try:
            r=session.get(url,stream=True,timeout=(30,120));r.raise_for_status()
            h=hashlib.sha256();total=0;reported=0
            with temp.open('wb') as f:
                for block in r.iter_content(4*1024*1024):
                    f.write(block);h.update(block);total+=len(block)
                    if total-reported>128*1024*1024:
                        print(path.name,round(total/1024**2),'MB',flush=True);reported=total
            if sha and h.hexdigest()!=sha:raise RuntimeError('SHA256 mismatch: '+path.name)
            temp.replace(path)
            print('READY',path.name,total,h.hexdigest(),flush=True)
            return
        except Exception:
            if attempt==2:raise
            time.sleep(2)


commit='944583f18b84589dc965de3ad77525c945334252'
for name in ('base.py','resunet.py'):
    download(f'https://raw.githubusercontent.com/Audio-AGI/AudioSep/{commit}/models/{name}',VENDOR/name)
download(f'https://raw.githubusercontent.com/Audio-AGI/AudioSep/{commit}/LICENSE',VENDOR/'LICENSE')
(VENDOR/'__init__.py').write_text('',encoding='utf-8')
# Only adapt the import namespace; preserve the pretrained architecture.
p=VENDOR/'resunet.py'
p.write_text(p.read_text(encoding='utf-8').replace('from models.base import','from .base import'),encoding='utf-8')
revision='0807a713283035d8b0d0628f1b8e3d6580459f7b'
tree=get_json(f'https://huggingface.co/api/spaces/Audio-AGI/AudioSep/tree/{revision}/checkpoint')
weight=next(x for x in tree if x['path'].endswith('audiosep_base_4M_steps.ckpt'))
sha=weight['lfs']['oid']
print('Disk free GB:',round(shutil.disk_usage(WORK).free/1024**3,1),flush=True)
download(f'https://huggingface.co/spaces/Audio-AGI/AudioSep/resolve/{revision}/{weight["path"]}',MODELS/'audiosep_base_4M_steps.ckpt',sha)
roberta='e2da8e2f811d1448a5b465c236feacd80ffbac7b'
tok=MODELS/'tokenizer';tok.mkdir(exist_ok=True)
for name in ('config.json','vocab.json','merges.txt','tokenizer.json'):
    download(f'https://huggingface.co/FacebookAI/roberta-base/resolve/{roberta}/{name}',tok/name)
manifest=dict(source_repo='https://github.com/Audio-AGI/AudioSep',source_revision=commit,
              weights_repo='https://huggingface.co/spaces/Audio-AGI/AudioSep',weights_revision=revision,
              weights_sha256=sha,weights_size=weight['size'],roberta_revision=roberta,
              source_license='MIT',adaptations=['Relative base import only. Inference uses original ResUNet30 architecture.'])
(MODELS/'manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
(VENDOR/'provenance.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
print('DONE',flush=True)
