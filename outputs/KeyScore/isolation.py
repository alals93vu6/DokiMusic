"""Target-aware separation/enhancement before the existing note detector.

AudioSep provides semantic instrument conditioning. HPSS is used only as mild
postprocessing, never as a substitute for identifying piano versus cello.
Confidence values below are evidence scores, NOT calibrated probabilities.
"""
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, Callable
import gc
import json
import time

import numpy as np
import soundfile as sf
from scipy.signal import resample_poly

from isolation_profiles import get_profile, IsolationProfile, PROFILE_VERSION

ROOT = Path(__file__).resolve().parent
MODEL_DIR = ROOT.parents[1] / 'work' / 'keyscore' / 'models' / 'audiosep'


class IAudioSourceIsolationService(Protocol):
    def isolate(self, source: Path, output_dir: Path, profile: IsolationProfile,
                progress: Callable[[float, str], None]): ...


@dataclass
class IsolationResult:
    source: Path
    target: Path
    competitor: Path
    report: dict


class AudioSepIsolationService:
    def __init__(self, device='auto'):
        import torch
        from safetensors.torch import load_file
        from vendor.audiosep.resunet import ResUNet30
        for name in ('separator.safetensors', 'queries.safetensors', 'manifest.json'):
            if not (MODEL_DIR / name).is_file():
                raise RuntimeError('目標樂器分離模型未安裝完整。請重新安裝模型，或明確選擇「純獨奏／原流程」。')
        torch.set_num_threads(4)
        self.device = 'cuda' if device == 'auto' and torch.cuda.is_available() else ('cpu' if device == 'auto' else device)
        self.model = ResUNet30(1, 1, 512).eval()
        self.model.load_state_dict(load_file(str(MODEL_DIR / 'separator.safetensors')), strict=True)
        self.model.to(self.device)
        self.queries = load_file(str(MODEL_DIR / 'queries.safetensors'), device=self.device)

    def _predict(self, samples, prompt):
        import torch
        if prompt not in self.queries:
            raise RuntimeError('此樂器的模型查詢尚未準備完成。')
        with torch.inference_mode():
            inp = torch.from_numpy(samples).view(1, 1, -1).to(self.device)
            result = self.model({'mixture': inp, 'condition': self.queries[prompt]})['waveform']
            return result[0, 0].float().cpu().numpy()

    def isolate(self, source, output_dir, profile, progress=lambda *_: None):
        started = time.perf_counter()
        audio, sr = sf.read(source, dtype='float32')
        if sr != 32000 or audio.ndim != 1:
            raise ValueError('Isolation requires decoded 32 kHz mono audio.')
        if not np.isfinite(audio).all():
            raise ValueError('音訊含有無效數值。')
        n = len(audio)
        if n == 0:
            raise ValueError('音訊是空白的。')
        target, competitor, weight = [np.zeros(n, dtype=np.float32) for _ in range(3)]
        size, hop = 5 * sr, 3 * sr
        positions = range(0, n, hop)
        for i, start in enumerate(positions):
            stop = min(n, start + size)
            samples = audio[start:stop]
            count = len(samples)
            padded = np.pad(samples, (0, size-count))
            progress(i / len(positions), f'分離 {profile.name}：{i+1} / {len(positions)} 段（{self.device.upper()}）')
            try:
                a = self._predict(padded, profile.prompt)[:count]
                b = self._predict(padded, profile.competitor)[:count]
            except Exception as error:
                import torch
                if isinstance(error, torch.cuda.OutOfMemoryError):
                    raise RuntimeError('GPU 記憶體不足。請改選 CPU，或關閉佔用顯示記憶體的程式後重試。') from error
                raise
            if not np.isfinite(a).all() or not np.isfinite(b).all():
                raise RuntimeError('分離模型輸出無效，已停止，未回退到原混音。')
            win = np.hanning(size + 2)[1:count+1].astype(np.float32)
            win = np.maximum(win, .01)
            target[start:stop] += a * win
            competitor[start:stop] += b * win
            weight[start:stop] += win
        target /= np.maximum(weight, 1e-8)
        competitor /= np.maximum(weight, 1e-8)
        output_dir = Path(output_dir)
        target_path, competitor_path = output_dir / 'target.wav', output_dir / 'competitor.wav'
        sf.write(target_path, target, sr, subtype='FLOAT')
        sf.write(competitor_path, competitor, sr, subtype='FLOAT')
        source_rms = float(np.sqrt(np.mean(audio**2) + 1e-12))
        target_rms = float(np.sqrt(np.mean(target**2) + 1e-12))
        report = dict(engine='AudioSep', version=PROFILE_VERSION, profile=profile.name,
            device=self.device.upper(), enabled=True, seconds=round(time.perf_counter()-started, 2),
            target_energy_ratio=round((target_rms / source_rms)**2, 4),
            confidence_kind='heuristic spectral evidence; not probability',
            candidate_notes=0, rejected_notes=0, accepted_notes=0)
        return IsolationResult(Path(source), target_path, competitor_path, report)

    def close(self):
        import torch
        self.model = None
        self.queries = None
        gc.collect()
        if self.device == 'cuda':
            torch.cuda.empty_cache()


def _read_segment(path, start, end):
    info = sf.info(path)
    audio, sr = sf.read(path, start=round(start*info.samplerate), stop=round(end*info.samplerate), dtype='float32')
    if sr != 22050:
        from math import gcd
        d = gcd(sr, 22050)
        audio = resample_poly(audio, 22050//d, sr//d).astype(np.float32)
    return audio


class SignalEvidence:
    def __init__(self, source, target, competitor, profile, strict=False):
        import librosa
        self.profile, self.strict = profile, strict
        self.sr, self.hop, self.nfft = 22050, 256, 2048
        self.source = np.abs(librosa.stft(source, n_fft=self.nfft, hop_length=self.hop))
        spectrum = librosa.stft(target, n_fft=self.nfft, hop_length=self.hop)
        self.target = np.abs(spectrum)
        self.competitor = np.abs(librosa.stft(competitor, n_fft=self.nfft, hop_length=self.hop))
        self.reference = max(float(np.max(self.target)), 1e-8)
        # Keep piano attacks; increase harmonic preference only for cello.
        harmonic, _ = librosa.decompose.hpss(spectrum, kernel_size=(21, 21), margin=(1.0, 2.0))
        enhanced = (1-profile.harmonic_mix)*spectrum + profile.harmonic_mix*harmonic
        # Gentle time-frequency gate relative to the retained target itself.
        floor = np.maximum(self.source*.025, self.reference*.0005)
        gate = np.clip(self.target / (self.target + floor + 1e-8), 0, 1)
        enhanced *= .35 + .65*gate
        if profile.name == 'cello':
            ownership = self.target / (self.target + self.competitor + 1e-8)
            enhanced *= np.clip(ownership * 1.5, .05, 1.)
        self.audio = librosa.istft(enhanced, hop_length=self.hop, length=len(target)).astype(np.float32)
        # Do not normalize every weak residual into a loud, convincing stem.
        peak = float(np.max(np.abs(self.audio)))
        if peak > .98:
            self.audio *= .98/peak

    def assess(self, start, end, pitch, strength):
        p = self.profile
        left = max(0, int(start*self.sr/self.hop))
        right = min(self.target.shape[1], max(left+1, int(end*self.sr/self.hop)))
        if right <= left:
            return False, 0., 'no_evidence'
        f0 = 440 * 2**((pitch-69)/12)
        values = []
        for h in range(1, 6):
            hz = f0*h
            idx = int(round(hz*self.nfft/self.sr))
            if idx+1 >= self.target.shape[0]:
                break
            lo, hi = max(0, idx-1), min(self.target.shape[0], idx+2)
            a = np.max(self.target[lo:hi, left:right], axis=0)
            b = np.max(self.competitor[lo:hi, left:right], axis=0)
            mix = np.max(self.source[lo:hi, left:right], axis=0)
            values.append((1/h, a, b, mix))
        if not values or right <= left:
            return False, 0., 'no_evidence'
        a = sum(w*x for w,x,_,_ in values)
        b = sum(w*x for w,_,x,_ in values)
        mix = sum(w*x for w,_,_,x in values)
        active = a > max(self.reference*.006, float(np.max(a))*.12)
        consistency = float(np.mean(active))
        ownership = float(np.sum(a)/(np.sum(a+b)+1e-8))
        retention = float(np.sum(a)/(np.sum(mix)+1e-8))
        relative = float(np.max(a))/self.reference
        confidence = .65*ownership + .25*min(1.,retention) + .1*consistency
        bonus = .08 if self.strict else 0
        if end-start < p.min_duration: return False, confidence, 'short'
        if strength < .2 or relative < p.min_relative_energy: return False, confidence, 'weak'
        if retention < p.min_retention: return False, confidence, 'bleed'
        if consistency < p.min_consistency: return False, confidence, 'unstable'
        if confidence < p.min_confidence+bonus: return False, confidence, 'target_confidence'
        return True, min(1.,confidence), 'accepted'

    def consolidate(self, notes):
        """Join cello vibrato fragments only when no fresh energy attack exists."""
        if self.profile.name != 'cello':
            return notes
        merged = []
        for note in sorted(notes, key=lambda n: (n[2], n[0])):
            s, e, pitch, strength, bends = note
            if merged and pitch == merged[-1][2] and abs(s-merged[-1][1]) < .025:
                idx = round(440*2**((pitch-69)/12)*self.nfft/self.sr)
                frame = round(s*self.sr/self.hop)
                envelope = np.max(self.target[max(0,idx-1):idx+2], axis=0)
                before = envelope[max(0,frame-6):frame]
                after = envelope[frame:frame+4]
                attack = (len(before) == 0 or len(after) == 0 or
                          np.mean(after) > max(np.mean(before)*1.6, self.reference*.01))
                if not attack:
                    prev = merged[-1]
                    prev[3] = (prev[3]*(prev[1]-prev[0])+strength*(e-s))/(e-prev[0])
                    prev[1] = e
                    continue
            merged.append([s,e,pitch,strength,bends])
        return merged


def prepare_segment(result, start, end, profile, strict=False):
    source = _read_segment(result.source, start, end)
    target = _read_segment(result.target, start, end)
    competitor = _read_segment(result.competitor, start, end)
    size = min(len(source), len(target), len(competitor))
    return SignalEvidence(source[:size], target[:size], competitor[:size], profile, strict)
