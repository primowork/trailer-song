"""התגיות: שכל כלל *ניתן לסיפוק*, ושאין כלל מת.

הבדיקה הזו קיימת בגלל דוח ריק. `tools/tag_report.py` על נתוני הסביבה הזו
הראה ששש מתוך שבע התגיות לא נדלקות אף פעם — אבל הנתונים שם הם 44 רשומות
זהות-בייט משאריות של הרצות בדיקה, שערכי הגוון שלהן יושבים על הרצפה או
מתחתיה. מנתונים כאלה אי אפשר להסיק כלום.

מה שכן אפשר להוכיח בלי נתונים אמיתיים: שלכל תגית קיימת מדידה שמדליקה
אותה, ושהמדידה הזו נבנית **מהטווחים המתועדים ב-`audio.py` עצמו** ולא
ממספרים שהומצאו כאן. כך "אף תגית לא נדלקה" יכול להיות רק אשמת הנתונים,
ולעולם לא סתירה פנימית בכללים.
"""

import audio
import tags


def _raw(**normalized):
    """מדידה גולמית שערכיה המנורמלים הם בדיוק מה שביקשו.

    היפוך של `audio._scaled`: הטווחים נלקחים מ-`audio.py`, ולכן שינוי טווח
    שם מזיז את המדידה כאן יחד איתו. מספרים גולמיים קבועים בקובץ הזה היו
    הופכים ירוק לחסר-משמעות ברגע שהכיול הבא ישנה טווח.
    """
    features = {"loudness": 0.0, "low_end": 0.0,
                "onset_rate": 0.0, "dynamic_span": 0.0}
    for name, (_, floor, full) in audio.WEIGHTS.items():
        features[name] = floor + normalized.get(name, 0.0) * (full - floor)
    for name, (floor, full) in audio.TIMBRE_RANGES.items():
        if name in normalized:
            features[name] = floor + normalized[name] * (full - floor)
    return features


# מדידה אחת לכל תגית, שנבנתה כדי להדליק אותה. הערכים נבחרו במרווח מהסף
# ולא עליו בדיוק: בדיקה שנשענת על שוויון מדויק נשברת על שגיאת עיגול.
SATISFYING = {
    tags.ACTION: _raw(onset_rate=0.80, loudness=0.70, dynamic_span=0.50),
    tags.RELENTLESS: _raw(onset_rate=0.80, dynamic_span=0.10, loudness=0.70),
    tags.SLOW_BURN: _raw(dynamic_span=0.85, onset_rate=0.10, loudness=0.60),
    tags.INTIMATE: _raw(loudness=0.10, onset_rate=0.10, low_end=0.10),
    tags.DARK: _raw(centroid=0.10, air=0.10, loudness=0.50, onset_rate=0.45),
    tags.BRIGHT: _raw(centroid=0.80, air=0.70, loudness=0.50, onset_rate=0.45),
    tags.GRITTY: _raw(flatness=0.80, loudness=0.50, onset_rate=0.45),
}


def test_every_tag_is_reachable():
    """אף כלל אינו מת: לכל תגית יש מדידה שמדליקה אותה."""
    for name in tags.TAGS:
        assert name in tags.tags_for(SATISFYING[name]), name


def test_no_measurement_collects_the_whole_vocabulary():
    """ושום מדידה לא אוספת את כל אוצר המילים — אחרת התגיות לא מבדילות בין
    טראקים אלא רק מעידות שנמדדו."""
    for name, features in SATISFYING.items():
        assert set(tags.tags_for(features)) != set(tags.TAGS), name


def test_dark_and_bright_are_mutually_exclusive():
    """שתי התגיות שהן ממש הפכים לא יכולות לדלוק יחד — לא בגלל סדר הכללים
    אלא בגלל הספים עצמם."""
    for features in SATISFYING.values():
        found = tags.tags_for(features)
        assert not (tags.DARK in found and tags.BRIGHT in found)
        assert not (tags.ACTION in found and tags.INTIMATE in found)


def test_no_tags_without_a_measurement():
    """'לא נמדד' אינו 'שקט'."""
    assert tags.tags_for(None) == []
    assert tags.tags_for({}) == []
    assert tags.tags_for({"error": "blocked"}) == []
    assert tags.primary_tag(None) is None


def test_timbre_tags_need_timbre_numbers():
    """מדידה שנשמרה לפני שמדדי הגוון נוספו לא מקבלת תגיות גוון — ובוודאי
    לא DARK רק בגלל שהערכים חסרים."""
    old = _raw(loudness=0.50, onset_rate=0.45)
    assert not ({tags.DARK, tags.BRIGHT, tags.GRITTY} & set(tags.tags_for(old)))


def test_flux_catches_a_compressed_master_that_onset_rate_misses():
    """הבאג שדווח: קאבר דראם אנד בייס אגרסיבי, ממוסטר עד שה-RMS כמעט
    שטוח, קיבל onset_rate נמוך (כמעט אין קפיצות עוצמה בין פריימים) ונקרא
    'רגוע'. `flux` בודק תוכן ספקטרלי במקום עוצמה — היי-האטים, בסים
    מעוותים ו-drop-ים עדיין קופצים שם — והוא זה שאמור לתפוס את זה במקום."""
    fooled_onset = _raw(onset_rate=0.10, dynamic_span=0.10, loudness=0.70,
                        flux=0.90)
    found = tags.tags_for(fooled_onset)
    assert tags.RELENTLESS in found
    assert tags.ACTION in found

    # ובלי flux (מדידה ישנה, או טראק שבאמת שקט מכל הכיוונים) העדות
    # היחידה היא onset_rate לבדו — וזה עדיין צריך לעבוד כמו קודם
    genuinely_calm = _raw(onset_rate=0.10, dynamic_span=0.10, loudness=0.70)
    assert tags.RELENTLESS not in tags.tags_for(genuinely_calm)


def test_primary_tag_is_one_and_from_the_vocabulary():
    for name, features in SATISFYING.items():
        primary = tags.primary_tag(features)
        assert primary in tags.TAGS, name


def test_filter_passes_everything_when_it_is_off():
    """תווית שאינה תגית מוכרת מכבה את המסנן, ולא מרוקנת את הרשימה."""
    quiet = SATISFYING[tags.INTIMATE]
    assert tags.matches(quiet, "All")
    assert tags.matches(quiet, "")
    assert tags.matches(quiet, tags.INTIMATE)
    assert not tags.matches(quiet, tags.ACTION)


def test_unmeasured_rows_survive_the_filter():
    """שורה שטרם נמדדה לא נעלמת מהתוצאות בזמן שהדפדפן עוד מודד."""
    for name in tags.TAGS:
        assert tags.matches(None, name)
        assert tags.matches({"error": "cors"}, name)
