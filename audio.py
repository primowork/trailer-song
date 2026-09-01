"""ניתוח אודיו אמיתי מתוך ה-preview בן 30 השניות.

הפילטרים "סגנון" ו"קצב" נדחפו עד היום כטקסט לשאילתת החיפוש ולא מדדו דבר. כאן הם
נמדדים: BPM, אנרגיה, ועוצמת ה-build-up.

Spotify אינו אופציה: audio-features, audio-analysis וקישורי ה-preview הופסקו
ב-27.11.2024 ואפליקציות חדשות מקבלות 403.

librosa היא תלות כבדה ולכן אופציונלית: אם היא לא מותקנת המודול מחזיר None בשקט
והממשק פשוט לא מציג מדדים, במקום להפיל את האפליקציה.
"""
import os
import tempfile
from dataclasses import asdict, dataclass

import httpx

import storage
from search import track_key

CACHE_FILE = "audio_features.json"
ANALYSIS_SECONDS = 30

_cache: dict | None = None


@dataclass
class AudioFeatures:
    bpm: float = 0.0
    energy: float = 0.0        # RMS ממוצע, 0..1
    peak_energy: float = 0.0   # השיא, מסמן את עוצמת ה-drop
    buildup: float = 0.0       # יחס שיא לממוצע: כמה דרמטית ההתפתחות
    error: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


def librosa_available() -> bool:
    try:
        import librosa  # noqa: F401
        return True
    except Exception:
        return False


def _load_cache() -> dict:
    global _cache
    if _cache is None:
        _cache = storage._load_json(CACHE_FILE, {}) or {}
    return _cache


def _save_cache():
    if _cache is not None:
        storage._save_json(CACHE_FILE, _cache)


def analyze_url(preview_url: str) -> AudioFeatures:
    """מוריד preview ומחלץ ממנו מדדים. לא זורק חריגות."""
    if not preview_url:
        return AudioFeatures(error="אין preview")
    if not librosa_available():
        return AudioFeatures(error="librosa לא מותקנת")

    path = ""
    try:
        import librosa
        import numpy as np

        with httpx.Client(timeout=20.0, follow_redirects=True) as client:
            response = client.get(preview_url)
            response.raise_for_status()
            data = response.content

        with tempfile.NamedTemporaryFile(suffix=".m4a", delete=False) as handle:
            handle.write(data)
            path = handle.name

        y, sr = librosa.load(path, mono=True, duration=ANALYSIS_SECONDS)
        if y.size == 0:
            return AudioFeatures(error="קובץ ריק")

        tempo, _ = librosa.beat.beat_track(y=y, sr=sr)
        rms = librosa.feature.rms(y=y)[0]
        mean_rms = float(np.mean(rms))
        peak_rms = float(np.max(rms))

        return AudioFeatures(
            bpm=round(float(tempo), 1),
            energy=round(min(mean_rms * 5, 1.0), 3),
            peak_energy=round(min(peak_rms * 5, 1.0), 3),
            buildup=round(peak_rms / mean_rms, 2) if mean_rms else 0.0,
        )
    except Exception as exc:
        return AudioFeatures(error=str(exc)[:150])
    finally:
        if path and os.path.exists(path):
            try:
                os.remove(path)
            except Exception:
                pass


def features_for(track: dict, use_cache: bool = True) -> AudioFeatures:
    """מדדים לשיר בודד, עם קאש לפי אותו track_key ששאר המערכת משתמשת בו."""
    key = track_key(track.get("artist", ""), track.get("track", ""))
    cache = _load_cache()

    if use_cache and key in cache:
        try:
            return AudioFeatures(**cache[key])
        except TypeError:
            pass

    result = analyze_url(track.get("preview_url", ""))
    if not result.error:
        cache[key] = result.to_dict()
        _save_cache()
    return result


def matches_tempo(features: AudioFeatures, tempo_filter: str) -> bool:
    """סינון לפי BPM נמדד במקום לפי מילה שנדחפה לשאילתה."""
    if not tempo_filter or tempo_filter == "הכל" or not features.bpm:
        return True
    if tempo_filter == "Fast Action":
        return features.bpm >= 120
    if tempo_filter == "Slow Build-up":
        return features.bpm < 120
    return True
