import json
from score import MARKER, PREFIX, encode_score
from pathlib import Path


def generate(title, result):
    song = dict(title=title, countdown=result['settings']['countdown'], events=result['events'])
    template = Path(__file__).with_name('player_template.py').read_text(encoding='utf-8')
    source = template.replace("'__SONG_JSON__'", repr(json.dumps(song, ensure_ascii=True, separators=(',', ':'))))
    source = '# -*- coding: utf-8 -*-\n' + MARKER + '\n' + PREFIX + encode_score(title, result) + '\n' + source
    compile(source, '<exported song>', 'exec')
    return source
