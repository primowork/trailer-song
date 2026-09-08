"""תגי השימוש: שהכללים חיים, מובחנים, ולא ממציאים מה שלא נמדד.

הטסטים בונים מדידות מתוך הטווחים המתועדים ב-`audio.py` עצמו ולא ממספרי
קסם, כי הטווחים האלה הם ההגדרה של "גבוה" ו"נמוך" כאן. כך שינוי בטווחים
מגיע לטסטים במקום להשאיר אותם ירוקים על הנחות ישנות.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import audio  # noqa: E402
import tags as tags_module  # noqa: E402

# הרצפה והערך לניקוד מלא לכל מדד, משני המקורות שמגדירים אותם
RANGES = {name: (floor, full) for name, (_, floor, full) in audio.WEIGHTS.items()}
RANGES.update(audio.TIMBRE_RANGES)


def _at(level: float) -> dict:
    """מדידה גולמית שכל מדדיה יושבים על אותו מקום יחסי בטווח שלהם."""
    return {name: floor + level * (full - floor)
            for name, (floor, full) in RANGES.items()}


def _raw(**levels) -> dict:
    """מדידה גולמית: רמה יחסית לכל מדד שנקבע, והשאר באמצע."""
    features = _at(0.45)
    for name, level in levels.items():
        floor, full = RANGES[name]
        features[name] = floor + level * (full - floor)
    return features


def test_every_tag_can_actually_fire():
    """כלל שאי אפשר לספק אינו כלל.

    זו הבדיקה שהתפלגות אמיתית לא יכולה לתת כאן: בסביבת הפיתוח יש רק
    מדידות סינתטיות שכל ערכיהן מתחת לרצפות, ולכן `tools/tag_report.py`
    מראה שישה תגים שלא נדלקים אף פעם. הטסט הזה מפריד בין "לא נדלק כי
    הנתונים סינתטיים" לבין "לא נדלק כי הכלל סותר את עצמו".
    """
    firing = {
        tags_module.ACTION: _raw(onset_rate=0.9, loudness=0.9),
        tags_module.SLOW_BURN: _raw(dynamic_span=0.9, onset_rate=0.05),
        tags_module.RELENTLESS: _raw(flux=0.9, onset_rate=0.9, dynamic_span=0.05),
        tags_module.DARK: _raw(centroid=0.05, low_end=0.9),
        tags_module.BRIGHT: _raw(centroid=0.9, air=0.9),
        tags_module.GRITTY: _raw(flatness=0.9, presence=0.9),
        tags_module.INTIMATE: _raw(loudness=0.05, low_end=0.05, flux=0.05),
    }
    assert set(firing) == set(tags_module.VOCABULARY), "תג בלי בדיקה שהוא נדלק"
    for name, features in firing.items():
        assert name in tags_module.derive(features), f"{name} לא נדלק על מדידה שנבנתה עבורו"


def test_no_measurement_means_no_tag_rather_than_a_guess():
    assert tags_module.derive(None) == []
    assert tags_module.derive({}) == []
    assert tags_module.derive({"error": "decode failed"}) == []


def test_an_unmeasured_version_passes_the_filter_instead_of_vanishing():
    """אותה החלטה שכבר התקבלה ב-`audio.matches_tempo`: מסנן שמעלים את מה
    שטרם נמדד היה מרוקן את המסך בדיוק בזמן שהמדידה רצה."""
    assert tags_module.matches(None, tags_module.ACTION) is True
    assert tags_module.matches({}, tags_module.ACTION) is True


def test_the_filter_selects_on_a_real_measurement():
    quiet = _raw(loudness=0.05, low_end=0.05, flux=0.05)
    assert tags_module.matches(quiet, tags_module.INTIMATE) is True
    assert tags_module.matches(quiet, tags_module.ACTION) is False


def test_an_unknown_filter_value_does_not_hide_everything():
    """"Any" ושאר ערכי תווית שאינם תגים חייבים לעבור, אחרת בחירת ברירת
    המחדל במסנן הייתה מרוקנת את התוצאות."""
    loud = _raw(onset_rate=0.9, loudness=0.9)
    assert tags_module.matches(loud, "Any") is True


def test_old_measurements_without_timbre_still_work():
    """מדידות שנשמרו לפני שמדדי הגוון נוספו עדיין תקפות (ראו
    `audio.normalized`) — הן פשוט לא מזכות בתגים שדורשים אותם."""
    old = {name: floor + 0.9 * (full - floor)
           for name, (floor, full) in RANGES.items() if name in audio.WEIGHTS}
    found = tags_module.derive(old)
    assert tags_module.ACTION in found
    assert tags_module.DARK not in found
    assert tags_module.BRIGHT not in found


def test_a_version_does_not_collect_every_tag():
    """תג שמופיע על כל שורה אינו תג. אף מדידה בודדת לא אמורה לגרוף את כל
    אוצר המילים — הכללים חייבים להיות מובחנים זה מזה."""
    for level in (0.0, 0.25, 0.5, 0.75, 1.0):
        found = tags_module.derive(_at(level))
        assert len(found) < len(tags_module.VOCABULARY), f"רמה {level} גרפה הכל"
