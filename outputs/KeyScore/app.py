"""KeyScore desktop application: local WebView UI + isolated transcription."""
import copy
import json
import logging
import os
from pathlib import Path
import subprocess
import sys
import threading
import uuid

from arrangement import arrange, settings
from exporter import generate
from isolation_profiles import PROFILE_VERSION

ROOT = Path(__file__).resolve().parent
DATA = ROOT.parents[1] / 'work' / 'keyscore' / 'data'
DATA.mkdir(parents=True, exist_ok=True)
logging.basicConfig(filename=str(DATA / 'app.log'), level=logging.INFO,
                    format='%(asctime)s %(levelname)s %(message)s', encoding='utf-8')


class Api:
    def __init__(self):
        self._window = None
        self._lock = threading.RLock()
        self._file = None
        self._raw = None
        self._raw_key = None
        self._result = None
        self._process = None
        self._cancelled = False
        self._state = dict(status='idle', progress=0, message='選擇一首音樂，開始編排。', result=None)

    def get_status(self):
        with self._lock:
            return copy.deepcopy(self._state)

    def _select(self, path):
        with self._lock:
            if self._state['status'] == 'running':
                raise ValueError('請先取消目前的分析。')
            path = Path(path).resolve()
            if not path.is_file() or path.suffix.lower() not in ('.mp3', '.wav', '.flac', '.ogg', '.m4a'):
                raise ValueError('請選擇 MP3、WAV、FLAC、OGG 或 M4A 音訊。')
            size = path.stat().st_size
            if not 0 < size <= 100 * 1024 * 1024:
                raise ValueError('請選擇小於 100 MB 且非空白的音訊檔。')
            self._file = path
            self._raw = self._result = self._raw_key = None
            self._state = dict(status='idle', progress=0, message='音訊已匯入，可以開始分析。', result=None)
            return dict(name=path.name, size=size)

    def choose_file(self):
        try:
            import webview
            paths = self._window.create_file_dialog(webview.FileDialog.OPEN, allow_multiple=False,
                file_types=('Audio (*.mp3;*.wav;*.flac;*.ogg;*.m4a)',))
            if not paths:
                return dict(cancelled=True)
            return dict(ok=True, file=self._select(paths[0]))
        except Exception as error:
            return dict(ok=False, error=str(error))

    def choose_demo(self):
        try:
            return dict(ok=True, file=self._select(ROOT / 'assets' / 'demo.mp3'))
        except Exception as error:
            return dict(ok=False, error=str(error))

    def analyze(self, options):
        try:
            cfg = settings(options)
            with self._lock:
                if self._state['status'] == 'running':
                    raise ValueError('分析正在進行中。')
                if self._file is None:
                    raise ValueError('請先匯入音訊。')
                self._cancelled = False
                self._state = dict(status='running', progress=1, message='準備分析…', result=None)
                self._result = None
                threading.Thread(target=self._run, args=(self._file, cfg), daemon=True).start()
            return dict(ok=True)
        except Exception as error:
            return dict(ok=False, error=str(error))

    def _run(self, path, cfg):
        output = DATA / f'{uuid.uuid4().hex}.json'
        final_state = None
        try:
            stat = path.stat()
            raw_key = (str(path), stat.st_mtime_ns, stat.st_size, cfg['mode'], cfg['isolation'],
                       cfg['strictness'], cfg['device'], PROFILE_VERSION)
            if self._raw is None or self._raw_key != raw_key:
                env = os.environ.copy()
                env['PYTHONIOENCODING'] = 'utf-8'
                env['NUMBA_CACHE_DIR'] = str(DATA / 'numba')
                env['NUMBA_NUM_THREADS'] = '4'
                with self._lock:
                    if self._cancelled:
                        return
                    worker_python = Path(sys.executable).with_name('python.exe') if os.name == 'nt' else Path(sys.executable)
                    proc = subprocess.Popen([str(worker_python), '-u', str(ROOT / 'worker.py'),
                        str(path), cfg['mode'], str(output), cfg['isolation'], cfg['strictness'], cfg['device']], stdout=subprocess.PIPE,
                        stderr=subprocess.STDOUT, text=True, encoding='utf-8', errors='replace',
                        creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0), env=env)
                    self._process = proc
                error_message = None
                for line in proc.stdout:
                    logging.info('worker: %s', line.rstrip())
                    if line.startswith('KEYSCORE:'):
                        update = json.loads(line[len('KEYSCORE:'):])
                        with self._lock:
                            if not self._cancelled:
                                self._state.update(update)
                    elif line.startswith('KEYSCORE_ERROR:'):
                        error_message = json.loads(line[len('KEYSCORE_ERROR:'):])
                code = proc.wait()
                with self._lock:
                    self._process = None
                    if self._cancelled:
                        return
                if code != 0 or not output.exists():
                    raise RuntimeError(error_message or '分析程序未完成，請重試。詳細資訊已存入 app.log。')
                self._raw = json.loads(output.read_text(encoding='utf-8'))
                self._raw_key = raw_key
            result = arrange(self._raw['notes'], cfg)
            result['waveform'] = self._raw['waveform']
            result['source_duration'] = self._raw['duration']
            result['title'] = path.name
            result['isolation'] = self._raw.get('isolation', {'enabled':False})
            with self._lock:
                if not self._cancelled:
                    self._result = result
                    final_state = dict(status='done', progress=100, message='編排完成，可以試聽或下載 Python。', result=result)
        except Exception as error:
            logging.exception('Analysis failed')
            with self._lock:
                if not self._cancelled:
                    final_state = dict(status='error', progress=0, message=str(error), result=None)
        finally:
            if output.exists():
                output.unlink()
            with self._lock:
                self._process = None
                if self._cancelled:
                    self._state = dict(status='cancelled', progress=0, message='已取消，可重新分析。', result=None)
                elif final_state is not None:
                    self._state = final_state

    def cancel(self):
        with self._lock:
            if self._state['status'] != 'running':
                return dict(ok=True)
            self._cancelled = True
            self._state['message'] = '正在取消…'
            proc = self._process
        if proc and proc.poll() is None:
            subprocess.run(['taskkill', '/PID', str(proc.pid), '/T', '/F'], capture_output=True,
                           creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        return dict(ok=True)

    def save_python(self):
        try:
            with self._lock:
                result = copy.deepcopy(self._result)
            if result is None:
                raise ValueError('請先完成音訊分析。')
            import webview
            default = Path(result['title']).stem + '_play.py'
            selected = self._window.create_file_dialog(webview.FileDialog.SAVE,
                directory=str(Path.home() / 'Downloads'), save_filename=default,
                file_types=('Python (*.py)',))
            if not selected:
                return dict(cancelled=True)
            target = Path(selected if isinstance(selected, str) else selected[0])
            if target.suffix.lower() != '.py':
                target = target.with_name(target.name + '.py')
            target.write_text(generate(result['title'], result), encoding='utf-8')
            return dict(ok=True, path=str(target))
        except Exception as error:
            logging.exception('Export failed')
            return dict(ok=False, error=str(error))

    def import_score(self):
        try:
            import webview
            from score import read_score, MAX_BYTES
            paths = self._window.create_file_dialog(webview.FileDialog.OPEN, allow_multiple=False,
                                                   file_types=('KeyScore Python (*.py)',))
            if not paths:
                return dict(cancelled=True)
            path = Path(paths[0])
            if path.stat().st_size > MAX_BYTES:
                raise ValueError('Python 檔案超過 8 MB。')
            return dict(ok=True, score=read_score(path.read_text(encoding='utf-8-sig')))
        except Exception as error:
            return dict(ok=False, error=str(error))

    def export_score(self, data):
        try:
            import webview
            from score import score_result
            result = score_result(data)
            source = generate(result['title'], result)
            paths = self._window.create_file_dialog(webview.FileDialog.SAVE,
                save_filename=result['settings']['mode']+'_edited_play.py', file_types=('Python (*.py)',))
            if not paths:
                return dict(cancelled=True)
            path = Path(paths if isinstance(paths, str) else paths[0])
            if path.suffix.lower() != '.py':
                path = path.with_name(path.name+'.py')
            path.write_text(source, encoding='utf-8')
            return dict(ok=True, path=str(path))
        except Exception as error:
            return dict(ok=False, error=str(error))


def main():
    import webview
    api = Api()
    html = (ROOT / 'ui.html').read_text(encoding='utf-8')
    html = html.replace('/*__STYLE__*/', (ROOT / 'style.css').read_text(encoding='utf-8'))
    html = html.replace('/*__SCRIPT__*/', (ROOT / 'ui.js').read_text(encoding='utf-8'))
    html = html.replace('/*__EDITOR__*/', (ROOT / 'editor.js').read_text(encoding='utf-8'))
    api._window = webview.create_window('KeyScore · 樂曲轉按鍵', html=html, js_api=api,
        width=1180, height=850, min_size=(920, 680), background_color='#111517', text_select=True)
    def on_closing():
        api.cancel()
    api._window.events.closing += on_closing
    webview.start(gui='edgechromium', storage_path=str(DATA / 'webview'))


if __name__ == '__main__':
    try:
        main()
    except Exception:
        logging.exception('Application startup failed')
        raise
