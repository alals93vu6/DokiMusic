"""Instrument-specific preprocessing policy, independent of transcription."""
from dataclasses import dataclass


@dataclass(frozen=True)
class IsolationProfile:
    name: str
    prompt: str
    competitor: str
    harmonic_mix: float
    min_duration: float
    min_confidence: float
    min_retention: float
    min_relative_energy: float
    min_consistency: float


PianoIsolationProfile = IsolationProfile('piano', 'piano', 'cello', .12, .09, .46, .12, .008, .3)
CelloIsolationProfile = IsolationProfile('cello', 'cello', 'piano', .45, .15, .50, .14, .012, .5)
PROFILES = {p.name: p for p in (PianoIsolationProfile, CelloIsolationProfile)}
PROFILE_VERSION = 'audiosep-v2'


def get_profile(name):
    if name not in PROFILES:
        raise ValueError('不支援的目標樂器。')
    return PROFILES[name]
