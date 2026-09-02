"""המדד שהחליף את ניחוש הרשימות: כמה הקאבר גדול ביחס למקור."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import audio
import covers

# מקור קטן: פופ מהיר, דינמיקה שטוחה
SMALL_ORIGINAL = audio.AudioFeatures(bpm=120, energy=0.40, peak_energy=0.45, buildup=1.2)
# קאבר ענק: איטי, קשת חדה מהשקט לדרופ, שיא גבוה
HUGE_COVER = audio.AudioFeatures(bpm=75, energy=0.30, peak_energy=0.85, buildup=3.1)


def test_small_original_huge_cover_scores_high():
    """הקריטריון שהמשתמש נתן, ישירות."""
    result = audio.compare_to_original(HUGE_COVER, SMALL_ORIGINAL)
    assert result.analyzed
    assert result.impact >= 80
    assert result.tempo_ratio > 1      # הקאבר איטי יותר
    assert result.peak_delta > 0       # והחזק יותר


def test_identical_recordings_score_zero():
    assert audio.compare_to_original(SMALL_ORIGINAL, SMALL_ORIGINAL).impact == 0


def test_a_quieter_flatter_cover_does_not_score():
    weak = audio.AudioFeatures(bpm=125, energy=0.35, peak_energy=0.38, buildup=1.1)
    assert audio.compare_to_original(weak, SMALL_ORIGINAL).impact == 0


def test_buildup_outweighs_tempo():
    """קשת גדולה שווה יותר מהאטה — האטה לבדה אינה קאבר לטריילר."""
    slow_only = audio.AudioFeatures(bpm=70, energy=0.40, peak_energy=0.45, buildup=1.2)
    arc_only = audio.AudioFeatures(bpm=120, energy=0.40, peak_energy=0.45, buildup=2.4)
    assert (audio.compare_to_original(arc_only, SMALL_ORIGINAL).impact
            > audio.compare_to_original(slow_only, SMALL_ORIGINAL).impact)


def test_unmeasurable_is_not_zero():
    """הבחנה קריטית: 'לא נמדד' אינו 'נמדד ויצא אפס'."""
    result = audio.compare_to_original(audio.AudioFeatures(error="download failed"),
                                       SMALL_ORIGINAL)
    assert result.analyzed is False
    assert result.reason == "download failed"


def test_missing_preview_reports_which_side():
    cover = {"artist": "X", "track": "Y", "preview_url": ""}
    original = {"artist": "O", "track": "Y", "preview_url": "http://p"}
    assert "לקאבר" in audio.impact_for(cover, original).reason
    assert "המקורית" in audio.impact_for({**cover, "preview_url": "http://p"}, None).reason


def test_impact_is_bounded():
    absurd = audio.AudioFeatures(bpm=20, energy=0.1, peak_energy=1.0, buildup=50.0)
    assert 0 <= audio.compare_to_original(absurd, SMALL_ORIGINAL).impact <= 100


# ---------- זיהוי הגרסה המקורית ----------

VERSIONS = [
    {"artist": "Sia", "track": "California Dreamin'", "year": "2015"},
    {"artist": "The Mamas & the Papas", "track": "California Dreamin'", "year": "1965"},
    {"artist": "Bobby Womack", "track": "California Dreamin'", "year": "1968"},
]


def test_original_defaults_to_the_earliest_year():
    assert covers.pick_original(VERSIONS)["artist"] == "The Mamas & the Papas"


def test_typed_artist_wins_over_the_year():
    assert covers.pick_original(VERSIONS, "Sia")["artist"] == "Sia"


def test_original_without_years_falls_back_to_the_first():
    undated = [{"artist": "A", "track": "T"}, {"artist": "B", "track": "T"}]
    assert covers.pick_original(undated)["artist"] == "A"


def test_no_versions_no_original():
    assert covers.pick_original([]) is None


# ---------- "גדולה מהחיים" נקבע במדידה, לא בכותרת ----------

def test_measured_big_version_regardless_of_title():
    assert audio.is_big_version({"analyzed": True, "impact": 85})
    assert not audio.is_big_version({"analyzed": True, "impact": 30})


def test_unmeasured_is_not_declared_small():
    """'לא נמדד' אינו 'לא גדול' — אסור לפסול גרסה שלא נבדקה."""
    assert not audio.is_big_version({"analyzed": False, "impact": 0})
    assert not audio.is_big_version(None)


def test_threshold_is_adjustable():
    assert audio.is_big_version({"analyzed": True, "impact": 50}, threshold=40)
    assert not audio.is_big_version({"analyzed": True, "impact": 50}, threshold=70)


def test_dataclass_and_dict_agree():
    metrics = audio.compare_to_original(HUGE_COVER, SMALL_ORIGINAL)
    assert audio.is_big_version(metrics) == audio.is_big_version(metrics.to_dict())
