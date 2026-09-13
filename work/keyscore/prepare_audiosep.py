"""Prepare minimal inference weights and fixed instrument query embeddings.

The original checkpoint includes CLAP's audio encoder and optimizer state,
neither is needed for fixed text queries. No training or random weights used.
"""
import gc
import hashlib
import json
from pathlib import Path
import sys
import torch
from torch import nn
from transformers import RobertaConfig, RobertaModel, RobertaTokenizer
from safetensors.torch import save_file

WORK=Path(__file__).resolve().parent
APP=WORK.parents[1]/'outputs'/'KeyScore'
sys.path.insert(0,str(APP))
from vendor.audiosep.resunet import ResUNet30

MODELS=WORK/'models'/'audiosep'
torch.set_num_threads(4)
print('Loading verified original checkpoint',flush=True)
state=torch.load(MODELS/'audiosep_base_4M_steps.ckpt',weights_only=True,map_location='cpu')['state_dict']
ss={k.removeprefix('ss_model.'):v.contiguous() for k,v in state.items() if k.startswith('ss_model.')}
model=ResUNet30(1,1,512)
model.load_state_dict(ss,strict=True)
save_file(ss,str(MODELS/'separator.safetensors'))
del model,ss
print('Preparing exact CLAP text branch',flush=True)
cfg=RobertaConfig.from_pretrained(str(MODELS/'tokenizer'),local_files_only=True)
model=RobertaModel(cfg).eval()
prefix='query_encoder.model.text_branch.'
weights={k[len(prefix):]:v for k,v in state.items() if k.startswith(prefix)}
# position_ids was a persistent buffer in older Transformers, now generated.
weights.pop('embeddings.position_ids',None)
weights.pop('embeddings.token_type_ids',None)
model.load_state_dict(weights,strict=True)
projection=nn.Sequential(nn.Linear(768,512),nn.ReLU(),nn.Linear(512,512)).eval()
prefix='query_encoder.model.text_projection.'
projection.load_state_dict({k[len(prefix):]:v for k,v in state.items() if k.startswith(prefix)},strict=True)
del state,weights;gc.collect()
tokenizer=RobertaTokenizer.from_pretrained(str(MODELS/'tokenizer'),local_files_only=True)
prompts=['piano','cello','drums','bass','guitar','singing voice']
tokens=tokenizer(prompts,padding='max_length',truncation=True,max_length=512,return_tensors='pt')
with torch.inference_mode():
    vector=torch.nn.functional.normalize(projection(model(**tokens).pooler_output),dim=-1)
assert vector.shape==(len(prompts),512)
save_file({text:vector[i:i+1].contiguous() for i,text in enumerate(prompts)},str(MODELS/'queries.safetensors'))
manifest=json.loads((MODELS/'manifest.json').read_text())
for name in ('separator.safetensors','queries.safetensors'):
    h=hashlib.sha256()
    with (MODELS/name).open('rb') as f:
        for block in iter(lambda:f.read(4*1024*1024),b''):h.update(block)
    manifest[name]={'sha256':h.hexdigest(),'bytes':(MODELS/name).stat().st_size}
manifest['queries']=prompts
manifest['preparation']='Original ResUNet30 + original CLAP RoBERTa pooler/projection, L2-normalized. No audio encoder needed for text prompts.'
(MODELS/'manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
print(json.dumps(manifest,indent=2),flush=True)
