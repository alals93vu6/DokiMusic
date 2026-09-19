"""Map transcribed notes onto the game's fifteen diatonic keys."""
import math
from collections import defaultdict

KEYS = 'ASDFGHJQWERTYUI'
STEPS = [0, 2, 4, 5, 7, 9, 11, 12, 14, 16, 17, 19, 21, 23, 24]


def settings(raw):
    mode = raw.get('mode', 'piano')
    if mode not in ('piano', 'cello', 'violin', 'harp'):
        raise ValueError('請選擇鋼琴或大提琴。')
    def number(key, default, low, high, integer=False):
        n = float(raw.get(key, default))
        if not math.isfinite(n) or not low <= n <= high:
            raise ValueError(f'{key} 超出允許範圍。')
        if integer and n != int(n):
            raise ValueError(f'{key} 必須是整數。')
        return int(n) if integer else n
    accidental = raw.get('accidental', 'nearest')
    if accidental not in ('nearest', 'skip'):
        raise ValueError('無效的升降音處理方式。')
    isolation = raw.get('isolation', 'mixed')
    strictness = raw.get('strictness', 'balanced')
    device = raw.get('device', 'auto')
    texture = raw.get('texture', 'full')
    if texture not in ('full', 'melody'):
        raise ValueError('無效的旋律模式。')
    if isolation not in ('mixed', 'solo') or strictness not in ('balanced', 'strict') or device not in ('auto', 'cpu'):
        raise ValueError('無效的目標樂器分離設定。')
    return dict(mode=mode, root=number('root', 60, 36, 72, True),
                transpose=number('transpose', 0, -12, 12, True),
                max_voices=number('max_voices', 8 if mode == 'piano' else 1, 1, 8, True),
                speed=number('speed', 1, .5, 1.5), countdown=number('countdown', 5, 3, 30, True),
                accidental=accidental, isolation=isolation, strictness=strictness, device=device, texture=texture)


def arrange(raw_notes, raw_settings):
    cfg = settings(raw_settings)
    scale = [cfg['root'] + x for x in STEPS]
    stats = dict(detected=len(raw_notes), octave_shifted=0, approximated=0, skipped=0)
    if cfg['texture'] == 'melody':
        from melody import extract_melody
        raw_notes = extract_melody(raw_notes)
        cfg['max_voices'] = 1
    stats['melody_removed'] = stats['detected']-len(raw_notes)
    buckets = defaultdict(list)
    for note in raw_notes:
        start, end, pitch, strength = note[:4]
        if not all(math.isfinite(float(x)) for x in (start, end, pitch, strength)) or end <= start:
            continue
        p = int(pitch) + cfg['transpose']
        shifted = p
        while shifted < scale[0]:
            shifted += 12
        while shifted > scale[-1]:
            shifted -= 12
        idx = min(range(15), key=lambda i: abs(scale[i] - shifted))
        altered = scale[idx] != shifted
        if altered and cfg['accidental'] == 'skip':
            stats['skipped'] += 1
            continue
        stats['approximated'] += int(altered)
        stats['octave_shifted'] += int(shifted != p)
        s = round(max(0, float(start)) / cfg['speed'], 3)
        e = round(float(end) / cfg['speed'], 3)
        if e - s >= .05:
            buckets[KEYS[idx]].append(dict(s=s, e=e, k=KEYS[idx], p=scale[idx], v=float(strength)))
    # One physical key cannot represent overlapping independent notes. Merge
    # near-simultaneous collisions; release briefly before a later re-strike.
    notes = []
    for key, group in buckets.items():
        group.sort(key=lambda n: (n['s'], -n['v']))
        clean = []
        for n in group:
            if clean and n['s'] - clean[-1]['s'] < .025:
                clean[-1]['e'] = max(clean[-1]['e'], n['e'])
                clean[-1]['v'] = max(clean[-1]['v'], n['v'])
                continue
            if clean and clean[-1]['e'] > n['s'] - .025:
                clean[-1]['e'] = max(clean[-1]['s'], round(n['s'] - .025, 3))
            clean.append(n)
        notes.extend(n for n in clean if n['e'] - n['s'] >= .05)
    if not notes:
        raise ValueError('沒有可演奏的音符。請換一段較清晰的獨奏，或改用「近似音」。')
    origin = min(n['s'] for n in notes)
    timeline = defaultdict(lambda: [[], []])
    for i, n in enumerate(notes):
        n['id'] = i
        n['s'] = round(n['s'] - origin, 3)
        n['e'] = round(n['e'] - origin, 3)
        timeline[n['s']][1].append(n)
        timeline[n['e']][0].append(n)
    active, sounding, output = {}, {}, []
    for t in sorted(timeline):
        ends, starts = timeline[t]
        for n in ends:
            active.pop(n['id'], None)
        for n in starts:
            active[n['id']] = n
        pool = list(active.values())
        if cfg['mode'] == 'cello':
            # Prefer the strongest detected line; allow double stops if chosen.
            ranked = sorted(pool, key=lambda n: (-n['v'], n['p']))
        else:
            # Preserve top melody and bass before filling inner harmony.
            ranked = []
            if pool:
                ranked.append(max(pool, key=lambda n: (n['p'], n['v'])))
            if len(pool) > 1:
                ranked.append(min(pool, key=lambda n: (n['p'], -n['v'])))
            ranked += sorted((n for n in pool if n not in ranked), key=lambda n: -n['v'])
        selected = {n['id']: n for n in ranked[:cfg['max_voices']]}
        for ident in list(sounding):
            if ident not in selected:
                segment = sounding.pop(ident)
                segment['e'] = t
                if t - segment['s'] >= .04:
                    output.append(segment)
        for ident, n in selected.items():
            if ident not in sounding:
                sounding[ident] = dict(s=t, e=n['e'], k=n['k'], p=n['p'], v=n['v'])
    output.sort(key=lambda n: (n['s'], n['p']))
    if not output:
        raise ValueError('音符太短，無法生成穩定按鍵。請嘗試其他音訊。')
    stats.update(playable=len(output), duration=round(max(n['e'] for n in output), 2),
                 trimmed_seconds=round(origin * cfg['speed'], 2))
    events = compile_events(output)
    current = set()
    peak = 0
    for _, releases, presses in events:
        current.difference_update(releases)
        current.update(presses)
        peak = max(peak, len(current))
    stats['peak_voices'] = peak
    return dict(notes=output, events=events, stats=stats, settings=cfg,
                keyboard=[dict(key=k, pitch=p) for k, p in zip(KEYS, scale)])


def compile_events(notes):
    events = defaultdict(lambda: [set(), set()])
    for n in notes:
        events[round(n['s'], 3)][1].add(n['k'])
        events[round(n['e'], 3)][0].add(n['k'])
    return [[t, sorted(release), sorted(press)] for t, (release, press) in sorted(events.items())]
