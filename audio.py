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


@dataclass
class ImpactMetrics:
    """כמה הקאבר "נותן בראש" ביחס למקור.

    זה המדד שהחליף את ניחוש הרשימות: קאבר לטריילר לוקח שיר מקורי קטן והופך
    אותו לענק — איטי יותר, עם קשת חדה מהשקט לדרופ ועם שיא חזק בהרבה.
    """
    tempo_ratio: float = 0.0    # מקור חלקי קאבר. מעל 1: הקאבר איטי יותר
    peak_delta: float = 0.0     # שיא הקאבר פחות שיא המקור
    buildup_ratio: float = 0.0  # קשת הקאבר חלקי קשת המקור
    impact: int = 0             # 0..100
    analyzed: bool = False      # False = לא נמדד, לא "אפס"
    reason: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


# משקלים: הקשת והשיא הם התרגום הישיר של "מקור קטן, קאבר ענק".
# הטמפו משני — קאבר לטריילר כמעט תמיד איטי מהמקור, אבל זה מלווה ולא מגדיר.
W_BUILDUP, W_PEAK, W_TEMPO = 45, 35, 20


def _scaled(value: float, full_credit: float) -> float:
    """0..1 ליניארי עד לערך שמזכה בניקוד מלא."""
    if full_credit <= 0:
        return 0.0
    return max(0.0, min(value / full_credit, 1.0))


def compare_to_original(cover: AudioFeatures, original: AudioFeatures) -> ImpactMetrics:
    """משווה קאבר למקור. לא מחזיר אפס כשאי אפשר למדוד — מחזיר analyzed=False."""
    if cover.error or original.error:
        return ImpactMetrics(reason=cover.error or original.error)
    if not cover.bpm or not original.bpm:
        return ImpactMetrics(reason="חסר ניתוח לאחד הצדדים")

    tempo_ratio = round(original.bpm / cover.bpm, 2) if cover.bpm else 0.0
    peak_delta = round(cover.peak_energy - original.peak_energy, 3)
    buildup_ratio = (round(cover.buildup / original.buildup, 2)
                     if original.buildup else 0.0)

    # קאבר עם קשת גדולה פי 2 מהמקור מקבל ניקוד מלא על הקשת;
    # שיא גבוה ב-0.3 מקבל ניקוד מלא; האטה של פי 1.6 מקבלת ניקוד מלא.
    score = (
        W_BUILDUP * _scaled(buildup_ratio - 1, 1.0)
        + W_PEAK * _scaled(peak_delta, 0.3)
        + W_TEMPO * _scaled(tempo_ratio - 1, 0.6)
    )

    return ImpactMetrics(
        tempo_ratio=tempo_ratio,
        peak_delta=peak_delta,
        buildup_ratio=buildup_ratio,
        impact=int(round(score)),
        analyzed=True,
    )


def impact_for(cover: dict, original: dict) -> ImpactMetrics:
    """נוחות: מנתח את שני הצדדים (מהקאש כשאפשר) ומשווה."""
    if not cover.get("preview_url"):
        return ImpactMetrics(reason="אין preview לקאבר")
    if not original or not original.get("preview_url"):
        return ImpactMetrics(reason="אין preview לגרסה המקורית")
    return compare_to_original(features_for(cover), features_for(original))


def matches_tempo(features: AudioFeatures, tempo_filter: str) -> bool:
    """סינון לפי BPM נמדד במקום לפי מילה שנדחפה לשאילתה."""
    if not tempo_filter or tempo_filter == "הכל" or not features.bpm:
        return True
    if tempo_filter == "Fast Action":
        return features.bpm >= 120
    if tempo_filter == "Slow Build-up":
        return features.bpm < 120
    return True
