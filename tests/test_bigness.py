"""ציון הגודל נבדק כאן במלואו: הוא פונקציה טהורה על dict, בלי דפדפן ובלי רשת."""
import audio

TRAILER = {"loudness": 0.30, "low_end": 3.0, "onset_rate": 4.0, "dynamic_span": 6.0}
BALLAD = {"loudness": 0.05, "low_end": 0.6, "onset_rate": 0.5, "dynamic_span": 1.4}
# המספרים האמיתיים משלוש שורות שהמשתמש דיווח עליהן, בסדר שהאוזן קובעת
LIGHT = {"loudness": 0.10, "low_end": 0.9, "onset_rate": 1.0, "dynamic_span": 2.0}
EPIC = {"loudness": 0.16, "low_end": 1.5, "onset_rate": 2.0, "dynamic_span": 3.5}


def test_trailer_scores_high_and_ballad_low():
    assert audio.bigness(TRAILER) >= 80
    assert audio.bigness(BALLAD) < 25


def test_the_score_spreads_instead_of_saturating():
    """הכשל שתוקן: כל הטראקים נחתו ב-65..74 כי שני מדדים נתנו ניקוד מלא לכולם."""
    scores = [audio.bigness(f) for f in (BALLAD, LIGHT, EPIC, TRAILER)]
    assert scores == sorted(scores), scores
    assert max(scores) - min(scores) > 50, scores
    # שתי גרסאות שונות באוזן לא יושבות באותם עשר נקודות
    assert audio.bigness(EPIC) - audio.bigness(LIGHT) > 10


def test_each_component_moves_the_score_alone():
    for name in ("loudness", "low_end", "onset_rate", "dynamic_span"):
        louder = {**BALLAD, name: TRAILER[name]}
        assert audio.bigness(louder) > audio.bigness(BALLAD), name


def test_score_is_bounded_on_absurd_input():
    assert audio.bigness({"loudness": 99, "low_end": 99,
                          "onset_rate": 999, "dynamic_span": 99}) == 100
    assert audio.bigness({"loudness": -5, "low_end": -5,
                          "onset_rate": -5, "dynamic_span": -5}) == 0
    assert audio.bigness({"loudness": "x"}) == 0


def test_failed_measurement_is_not_small():
    failed = {"error": "cors_failed"}
    assert not audio.measured(failed)
    assert not audio.measured(None)
    assert not audio.is_big_version(failed)
    assert audio.measured(TRAILER)


def test_big_version_uses_the_threshold():
    assert audio.is_big_version(TRAILER)
    assert not audio.is_big_version(BALLAD)
    assert audio.is_big_version(BALLAD, threshold=0)


def test_describe_shows_raw_numbers_only_when_measured():
    text = audio.describe(TRAILER)
    assert "0.30" in text and "3.00" in text
    assert audio.describe({"error": "x"}) == ""


def test_matches_tempo_uses_measured_onsets():
    assert audio.matches_tempo(TRAILER, "Fast Action")
    assert not audio.matches_tempo(BALLAD, "Fast Action")
    assert audio.matches_tempo(BALLAD, "Slow Build-up")
    assert not audio.matches_tempo(TRAILER, "Slow Build-up")


def test_matches_tempo_passes_everything_without_measurement():
    assert audio.matches_tempo(None, "Fast Action")
    assert audio.matches_tempo({"error": "cors_failed"}, "Fast Action")
    assert audio.matches_tempo(TRAILER, "הכל")


# ---------- קלט פגום מהדפדפן ----------

def test_a_non_numeric_measurement_does_not_crash_the_card():
    """המדידה מגיעה מהדפדפן ואינה נתון מהימן; ערך שאינו מספר הפיל את
    הכרטיס כולו על שגיאת פורמט."""
    for bad in ({"loudness": None}, {"loudness": "x"}, {"low_end": []},
                {"onset_rate": "fast"}):
        assert isinstance(audio.describe(bad), str)
        assert isinstance(audio.bigness(bad), int)
        assert audio.matches_tempo(bad, "Fast Action") in (True, False)
