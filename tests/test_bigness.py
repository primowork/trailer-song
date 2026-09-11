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


# ---------- קלט פגום מהדפדפן ----------

def test_a_non_numeric_measurement_does_not_crash_the_card():
    """המדידה מגיעה מהדפדפן ואינה נתון מהימן; ערך שאינו מספר הפיל את
    הכרטיס כולו על שגיאת פורמט."""
    for bad in ({"loudness": None}, {"loudness": "x"}, {"low_end": []},
                {"onset_rate": "fast"}):
        assert isinstance(audio.describe(bad), str)
        assert isinstance(audio.bigness(bad), int)
        assert audio.normalized(bad) is None or isinstance(audio.normalized(bad), dict)


# ---------- כרומה: מהלך הרמוני, לא עוצמה ----------

def _measured(chroma):
    """מדידה תקינה שנושאת את פרופיל הכרומה הזה."""
    return {**BALLAD, "chroma": list(chroma)}


# דו מז'ור: דו, מי, סול בולטים (מחלקות 0, 4, 7)
C_MAJOR = [.20, .02, .05, .02, .18, .05, .02, .19, .02, .06, .03, .04]
# אותו שיר בדיוק, מועבר שני חצאי-טונים למעלה (רה מז'ור) — מה שקורה כשזמרת
# עם טווח אחר שרה את אותו שיר
D_MAJOR = C_MAJOR[-2:] + C_MAJOR[:-2]
# מבנה מרווחים אחר לגמרי: שלושה חצאי-טונים צמודים במקום משולש מז'ורי.
# *לא* סתם "אותם אקורדים בסולם אחר" — העברת טונציה מכוסה ממילא על ידי
# ההשוואה לכל ההזזות, ולכן מה שיכול להבדיל הוא המרווחים עצמם.
CLUSTER = [.20, .19, .18, .02, .03, .02, .02, .03, .02, .06, .03, .04]
# משולש מינורי (0, 3, 7): חולק שני צלילים מתוך שלושה עם המז'ורי
MINOR_TRIAD = [.20, .02, .05, .18, .03, .05, .02, .19, .02, .06, .03, .04]


def test_a_transposed_version_still_matches():
    """קאבר מועבר טונציה הוא אותו שיר, ולכן ההשוואה עוברת על כל
    שתים-עשרה ההזזות ולוקחת את הטובה."""
    assert audio.chroma_similarity(_measured(C_MAJOR), _measured(D_MAJOR)) > 0.99


def test_a_different_interval_structure_scores_lower():
    same = audio.chroma_similarity(_measured(C_MAJOR), _measured(C_MAJOR))
    cluster = audio.chroma_similarity(_measured(C_MAJOR), _measured(CLUSTER))
    assert same > 0.99
    assert cluster < same - 0.3, (same, cluster)


def test_the_signal_is_soft_and_the_test_says_so():
    """התיעוד של מה שהמדד הזה *לא* עושה, כמספר ולא כהבטחה: משולש מינורי
    הוא לא אותו אקורד, אבל הוא חולק איתו שני צלילים ולכן מקבל ציון גבוה
    למדי. לכן `RANK_HARMONY` הוא משקל קטן ולא מסנן — שני שירים שונים
    בעלי אופי הרמוני דומה *יקבלו* כאן ציון גבוה."""
    close_but_different = audio.chroma_similarity(
        _measured(C_MAJOR), _measured(MINOR_TRIAD))
    assert 0.7 < close_but_different < 0.9, close_but_different


def test_a_flat_profile_does_not_pretend_to_match():
    """רעש לבן, או קליפ שלא נמצא בו שום גובה צליל, מפיק פרופיל שטוח —
    ומתאם מול שטוח אינו מוגדר, לא 'התאמה מושלמת'."""
    flat = _measured([1 / 12] * 12)
    assert audio.chroma_similarity(flat, _measured(C_MAJOR)) == 0.5


def test_no_similarity_without_two_real_measurements():
    assert audio.chroma_similarity(_measured(C_MAJOR), None) is None
    assert audio.chroma_similarity(_measured(C_MAJOR), BALLAD) is None
    assert audio.chroma_similarity(_measured(C_MAJOR), {"error": "cors"}) is None
    # אורך שגוי או ערכים שאינם מספרים מגיעים מהדפדפן ואינם נתון מהימן
    assert audio.chroma_similarity(_measured(C_MAJOR), _measured([.5, .5])) is None
    assert audio.chroma(_measured(["a"] * 12)) == []
