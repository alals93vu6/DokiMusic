"""Isolated, cancellable local audio transcription worker."""
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import traceback

os.environ.setdefault('NUMBA_NUM_THREADS', '4')
os.environ.setdefault('OMP_NUM_THREADS', '4')


def status(progress, message):
    print('KEYSCORE:' + json.dumps(dict(progress=progress, message=message), ensure_ascii=True), flush=True)


def transcribe(audio_path, mode, output_path, isolation_mode='solo', strictness='balanced', device='auto'):
    if isolation_mode not in ('solo', 'mixed') or strictness not in ('balanced', 'strict') or device not in ('auto', 'cpu'):
        raise ValueError('無效的分離設定。')
    status(3, '正在解碼 MP3…')
    import imageio_ffmpeg
    import soundfile as sf
    import numpy as np
    with tempfile.TemporaryDirectory(prefix='keyscore-') as temp:
        wav = Path(temp) / 'source.wav'
        cmd = [imageio_ffmpeg.get_ffmpeg_exe(), '-nostdin', '-v', 'error', '-y', '-i',
               str(audio_path), '-t', '1201', '-ac', '1', '-ar', '32000' if isolation_mode == 'mixed' else '22050', str(wav)]
        completed = subprocess.run(cmd, capture_output=True, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        if completed.returncode:
            raise ValueError('無法解碼這個音訊檔。請確認 MP3 可以正常播放。')
        info = sf.info(wav)
        duration = info.duration
        if duration > 1200:
            raise ValueError('第一版支援最長 20 分鐘，請先裁切音訊。')
        if duration < .2:
            raise ValueError('音訊太短，請選擇至少 0.2 秒的音訊。')
        isolated = None
        isolation_report = dict(enabled=False, engine='原始獨奏流程', candidate_notes=0,
                                accepted_notes=0, rejected_notes=0, rejected_reasons={})
        if isolation_mode == 'mixed':
            from isolation import AudioSepIsolationService, prepare_segment
            from isolation_profiles import get_profile
            profile = get_profile(mode)
            status(6, '正在載入目標樂器分離模型…')
            service = AudioSepIsolationService(device=device)
            try:
                isolated = service.isolate(wav, Path(temp), profile,
                    lambda f, text: status(8 + int(f*48), text))
                isolation_report = isolated.report
                isolation_report['rejected_reasons'] = {}
            finally:
                service.close()
        status(58 if isolated else 8, '正在載入音符辨識模型；首次分析需要較久…')
        import basic_pitch
        from basic_pitch.inference import Model, predict
        model_path = Path(basic_pitch.__file__).parent / 'saved_models' / 'icassp_2022' / 'nmp.onnx'
        if not model_path.exists():
            models = list(Path(basic_pitch.__file__).parent.rglob('*.onnx'))
            if len(models) != 1:
                raise RuntimeError('找不到已安裝的 ONNX 模型。')
            model_path = models[0]
        model = Model(model_path)
        # Keep CPU usage reasonable on a gaming PC.
        import onnxruntime as ort
        options = ort.SessionOptions()
        options.intra_op_num_threads = 4
        options.inter_op_num_threads = 1
        model.model = ort.InferenceSession(str(model_path), sess_options=options, providers=['CPUExecutionProvider'])
        chunks = math.ceil(duration / 30)
        notes = []
        wave_peaks = []
        for i in range(chunks):
            left, right = i * 30, min(duration, (i + 1) * 30)
            context_start = max(0, left - 1)
            context_end = min(duration, right + 1)
            evidence = None
            if isolated:
                status(60 + int(34*i/chunks), f'正在強化目標訊號與辨識音符：第 {i+1} / {chunks} 段…')
                evidence = prepare_segment(isolated, context_start, context_end, profile, strictness == 'strict')
                data, sr = evidence.audio, 22050
            else:
                data, sr = sf.read(wav, start=round(context_start * 22050), stop=round(context_end * 22050), dtype='float32')
            segment = Path(temp) / 'segment.wav'
            sf.write(segment, data, sr, subtype='FLOAT')
            if not isolated:
                status(12 + int(78 * i / chunks), f'正在辨識音符：第 {i + 1} / {chunks} 段…')
            _, _, found = predict(segment, model_or_model_path=model,
                onset_threshold=.5 if mode == 'piano' else .45,
                frame_threshold=.3, minimum_note_length=90 if mode == 'piano' else 130,
                minimum_frequency=27.5, maximum_frequency=4186, multiple_pitch_bends=False)
            if evidence:
                original_count = len(found)
                found = evidence.consolidate(found)
                isolation_report['merged_fragments'] = isolation_report.get('merged_fragments', 0) + original_count-len(found)
            for s, e, pitch, strength, _ in found:
                relative_start, relative_end = float(s), float(e)
                s, e = relative_start + context_start, min(duration, relative_end + context_start)
                if s < right and e > left:
                    isolation_report['candidate_notes'] += 1
                    if evidence:
                        accepted, confidence, reason = evidence.assess(relative_start, relative_end, int(pitch), float(strength))
                        if not accepted:
                            isolation_report['rejected_notes'] += 1
                            reasons = isolation_report['rejected_reasons']
                            reasons[reason] = reasons.get(reason, 0) + 1
                            continue
                        strength = float(strength)*confidence
                    isolation_report['accepted_notes'] += 1
                    notes.append([round(max(s, left), 4), round(min(e, right), 4),
                                  int(pitch), float(strength), s < left])
            core = data[round((left - context_start) * sr):round((right - context_start) * sr)]
            for block in np.array_split(core, max(1, round((right - left) * 8))):
                wave_peaks.append(round(float(np.max(np.abs(block))) if len(block) else 0, 4))
        # Stitch a sustained note across chunk boundaries when the contextual
        # window detects the same note again near a boundary.
        notes.sort(key=lambda n: (n[2], n[0]))
        stitched = []
        for n in notes:
            if stitched and n[4] and n[2] == stitched[-1][2] and abs(n[0] - stitched[-1][1]) < .03:
                stitched[-1][1] = max(stitched[-1][1], n[1])
            else:
                stitched.append(n)
        stitched.sort(key=lambda n: (n[0], n[2]))
        stitched = [n[:4] for n in stitched]
        if not stitched:
            if isolated:
                raise ValueError(f'沒有足夠可信的目標樂器音符（已篩除 {isolation_report["rejected_notes"]} 個候選）。請確認原曲有此樂器，或將嚴格度改為標準。純獨奏可明確選擇原流程。')
            raise ValueError('未辨識到音符。請使用清晰的鋼琴或大提琴獨奏音訊。')
        Path(output_path).write_text(json.dumps(dict(notes=stitched, duration=duration, waveform=wave_peaks,
                                                    isolation=isolation_report)), encoding='utf-8')
        status(98, '音符辨識完成，正在編排遊戲按鍵…')


if __name__ == '__main__':
    try:
        transcribe(*sys.argv[1:])
    except Exception as error:
        print('KEYSCORE_ERROR:' + json.dumps(str(error), ensure_ascii=True), flush=True)
        traceback.print_exc()
        sys.exit(1)
