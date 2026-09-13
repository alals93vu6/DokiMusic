"""Versioned comment-only score import. Never evaluate imported Python."""
import base64
import json
import math
from arrangement import KEYS, STEPS, settings, compile_events

MARKER = '# KEYSCORE_EDITABLE_SCORE_V1'
PREFIX = '# KEYSCORE_DATA: '
MAX_BYTES = 8 * 1024 * 1024


def validate_score(data):
    if not isinstance(data, dict) or data.get('version') != 1:
        raise ValueError('不支援的樂譜版本。')
    cfg = settings(data.get('settings', {}))
    title = data.get('title', '未命名樂譜')
    if not isinstance(title, str) or len(title) > 500:
        raise ValueError('曲名無效。')
    raw = data.get('notes')
    if not isinstance(raw, list) or not 1 <= len(raw) <= 20000:
        raise ValueError('樂譜需包含 1–20,000 個音符。')
    notes = []
    for n in raw:
        if not isinstance(n, dict) or n.get('k') not in list(KEYS):
            raise ValueError('音符按鍵無效。')
        vals = [n.get('s'), n.get('e'), n.get('v', .8)]
        if any(type(x) not in (int, float) or not math.isfinite(x) for x in vals):
            raise ValueError('音符時間或強度無效。')
        s, e, v = vals
        s, e = round(s, 3), round(e, 3)
        if not 0 <= s < e <= 2400 or e-s < .0499 or not 0 <= v <= 1:
            raise ValueError('音符需至少 0.05 秒，範圍 0–2400 秒，強度 0–1。')
        notes.append(dict(s=s, e=e, k=n['k'], p=cfg['root']+STEPS[KEYS.index(n['k'])], v=v))
    last = {}
    for n in sorted(notes, key=lambda n: (n['s'], n['e'])):
        if n['k'] in last and n['s'] < last[n['k']]-1e-6:
            raise ValueError(f"{n['k']} 鍵有重疊音符，請移動或縮短後再匯出。")
        last[n['k']] = n['e']
    notes.sort(key=lambda n: (n['s'], n['p']))
    events = compile_events(notes)
    held = set(); peak = 0
    for _, releases, presses in events:
        held.difference_update(releases); held.update(presses)
        peak = max(peak, len(held))
    if peak > 8:
        raise ValueError('同時發聲超過 8 音，請刪減或錯開音符。')
    cfg['max_voices'] = max(cfg['max_voices'], peak)
    return dict(version=1, title=title, settings=cfg, notes=notes)


def score_result(data):
    score = validate_score(data)
    return dict(title=score['title'], settings=score['settings'], notes=score['notes'],
                events=compile_events(score['notes']))


def encode_score(title, result):
    score = validate_score(dict(version=1, title=title, notes=result['notes'], settings=result['settings']))
    return base64.b64encode(json.dumps(score, ensure_ascii=True, separators=(',', ':')).encode()).decode()


def read_score(source):
    if len(source.encode('utf-8')) > MAX_BYTES:
        raise ValueError('Python 檔案超過 8 MB。')
    lines = source.splitlines()
    if len(lines) < 3 or lines[1] != MARKER or not lines[2].startswith(PREFIX):
        raise ValueError('缺少第 2 行 KeyScore V1 標記或第 3 行樂譜資料。舊版腳本請重新分析後匯出。')
    try:
        payload = base64.b64decode(lines[2][len(PREFIX):], validate=True)
        data = json.loads(payload)
        return validate_score(data)
    except (ValueError, TypeError, KeyError, RecursionError) as error:
        raise ValueError('樂譜資料無效：'+str(error)) from error
