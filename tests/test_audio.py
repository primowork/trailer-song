import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import audio


def test_no_preview_returns_error_not_exception():
    result = audio.analyze_url("")
    assert result.error == "אין preview"
    assert result.bpm == 0.0


def test_analyze_url_never_raises_on_bad_url(monkeypatch):
    monkeypatch.setattr(audio, "librosa_available", lambda: True)
    result = audio.analyze_url("http://127.0.0.1:1/nope.m4a")
    assert result.error  # שגיאה מוחזרת, לא נזרקת


def test_missing_librosa_degrades_quietly(monkeypatch):
    monkeypatch.setattr(audio, "librosa_available", lambda: False)
    assert audio.analyze_url("http://x/y.m4a").error == "librosa לא מותקנת"


def test_matches_tempo_uses_measured_bpm():
    fast = audio.AudioFeatures(bpm=140)
    slow = audio.AudioFeatures(bpm=80)
    assert audio.matches_tempo(fast, "Fast Action")
    assert not audio.matches_tempo(slow, "Fast Action")
    assert audio.matches_tempo(slow, "Slow Build-up")
    assert not audio.matches_tempo(fast, "Slow Build-up")


def test_matches_tempo_passes_everything_without_measurement():
    unmeasured = audio.AudioFeatures(bpm=0)
    assert audio.matches_tempo(unmeasured, "Fast Action")
    assert audio.matches_tempo(audio.AudioFeatures(bpm=140), "הכל")


def test_features_for_uses_cache(monkeypatch, tmp_path):
    audio._cache = {}
    calls = []
    monkeypatch.setattr(audio, "analyze_url", lambda url: calls.append(url) or audio.AudioFeatures(bpm=128))
    monkeypatch.setattr(audio.storage, "_save_json", lambda *a, **k: True)

    track = {"artist": "2WEI", "track": "Zombie", "preview_url": "http://p"}
    first = audio.features_for(track)
    second = audio.features_for(track)
    assert first.bpm == second.bpm == 128
    assert len(calls) == 1  # הקריאה השנייה הגיעה מהקאש


def test_failed_analysis_is_not_cached(monkeypatch):
    audio._cache = {}
    monkeypatch.setattr(audio, "analyze_url", lambda url: audio.AudioFeatures(error="boom"))
    monkeypatch.setattr(audio.storage, "_save_json", lambda *a, **k: True)
    audio.features_for({"artist": "A", "track": "B", "preview_url": "http://p"})
    assert audio._cache == {}
