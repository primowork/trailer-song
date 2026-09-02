"""ציון הגודל נבדק כאן במלואו: הוא פונקציה טהורה על dict, בלי דפדפן ובלי רשת."""
import audio

TRAILER = {"loudness": 0.25, "low_end": 0.50, "onset_rate": 4.0, "crest": 3.0}
BALLAD = {"loudness": 0.05, "low_end": 0.10, "onset_rate": 0.5, "crest": 1.5}


def test_trailer_scores_high_and_ballad_low():
    assert audio.bigness(TRAILER) >= 80
    assert audio.bigness(BALLAD) < 25


def test_each_component_moves_the_score_alone():
    for name in ("loudness", "low_end", "onset_rate", "crest"):
        louder = {**BALLAD, name: TRAILER[name]}
        assert audio.bigness(louder) > audio.bigness(BALLAD), name


def test_score_is_bounded_on_absurd_input():
    assert audio.bigness({"loudness": 99, "low_end": 99,
                          "onset_rate": 999, "crest": 99}) == 100
    assert audio.bigness({"loudness": -5, "low_end": -5,
                          "onset_rate": -5, "crest": -5}) == 0
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
    assert "0.25" in text and "0.50" in text
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
