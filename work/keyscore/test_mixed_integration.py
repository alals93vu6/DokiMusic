"""Exercise real separation through the API, cache changes and cancellation."""
import json
from pathlib import Path
import sys
import time

WORK=Path(__file__).resolve().parent
sys.path.insert(0,str(WORK.parents[1]/'outputs'/'KeyScore'))
from app import Api
from test_integration import await_done

api=Api()
api._select(WORK/'benchmark'/'B.mp3')
assert api.analyze({'mode':'piano','isolation':'mixed'})['ok']
result=await_done(api)
assert result['status']=='done',result
assert result['result']['isolation']['enabled']
key=api._raw_key;raw=api._raw
assert api.analyze({'mode':'piano','isolation':'mixed','speed':.5})['ok']
assert await_done(api)['status']=='done'
assert api._raw is raw and api._raw_key==key
assert api.analyze({'mode':'piano','isolation':'solo'})['ok']
assert await_done(api)['status']=='done'
assert api._raw_key!=key and not api._raw['isolation']['enabled']
assert api.analyze({'mode':'piano','isolation':'mixed','device':'cpu'})['ok']
result=await_done(api)
assert result['status']=='done',result
assert result['result']['isolation']['device']=='CPU'
(WORK/'cpu-result.json').write_text(json.dumps(result['result']['isolation']),encoding='utf-8')
api.choose_demo()
assert api.analyze({'isolation':'mixed'})['ok']
deadline=time.monotonic()+90
while time.monotonic()<deadline:
    state=api.get_status()
    if state['progress']>=8 or state['status']!='running':break
    time.sleep(.02)
assert state['status']=='running',state
api.cancel()
assert await_done(api)['status']=='cancelled'
assert api.choose_demo()['ok']
print('PASS: mixed API, cache reuse/invalidation, real CPU inference, cancellation during separation. No keys sent.')
