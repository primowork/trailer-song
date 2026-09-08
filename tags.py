"""תגי שימוש: לְמָה הגרסה הזו מתאימה, מתוך מה שכבר נמדד.

**למה לא מודל שפה.** המשתמש ביקש במפורש פתרון שאינו דורש לשלם על API,
ולמודל שפה יש כאן ממילא חיסרון מבני: הוא לא שומע את הטראק. הוא היה מנחש
מהכותרת ומהאמן — בדיוק המידע שכבר יש, ושכבר מנוצל ב-`search.trailer_indicators`.

מה שכן שומע את הטראק הוא הדפדפן של המשתמש, שכבר מודד תשעה מספרים לכל
גרסה (`components/audio_meter`, ראו `audio.py`). המדידות האלה משותפות לכל
המשתמשים, נצברות מעצמן עם השימוש, ולא עולות דבר. התגים כאן נגזרים מהן.

**התגים אינם נשמרים.** הם פונקציה טהורה של המדידה, שכבר שמורה — שמירה
שלהם הייתה יוצרת עותק שני שמתיישן ברגע שהכיול משתנה.

## על הכיול

הסִפִּים כאן נמצאים במרחב המנורמל של `audio.normalized()` (0..1), שכויל
בעבר מול מדידות אמיתיות. **הם עצמם עדיין לא כוילו מול התפלגות אמיתית**:
בסביבת הפיתוח יש רק מדידות סינתטיות. `tools/tag_report.py` מדפיס את
התפלגות התגים מול קובץ מדידות אמיתי, וזו הבדיקה שצריכה לרוץ לפני שסומכים
עליהם.

**ולא כל התגים שווים בביטחון.** ארבעת מדדי `WEIGHTS`
(עוצמה, בס, מכות, קשת) כוילו מול מדידות אמיתיות; חמשת מדדי
`TIMBRE_RANGES` מסומנים בקוד עצמו כ"הערכה ומיועדים לכיול על ייצוא
אמיתי". לכן ACTION, SLOW BURN ו-INTIMATE נשענים על קרקע מוצקה יותר
מ-DARK, ‏BRIGHT ו-GRITTY. `tools/tag_report.py` מפריד ביניהם בפלט.

זו אינה זהירות תיאורטית. ההערה ליד `WEIGHTS` ב-`audio.py` מתעדת בדיוק את
הכשל הזה: כיול ראשון שנתן ניקוד מלא כמעט לכל טראק, כלומר "מדד שכולם
מקבלים עליו ניקוד מלא אינו מדד". תג שמופיע על כל שורה אינו תג.
"""
from __future__ import annotations

import audio

# "גבוה" ו"נמוך" במרחב המנורמל. שני ספים ולא אחד, כי חלק מהתגים מוגדרים
# דווקא בהיעדר של משהו (שקט, בלי מכות) ולא בנוכחות שלו.
HIGH = 0.60
LOW = 0.25

# כל תג דורש **שני** תנאים לפחות. תנאי יחיד היה הופך כל תג למחצית
# מהתוצאות, וזה בדיוק המצב שבו התג מפסיק להבדיל בין שורות.
#
# הסדר הוא סדר עדיפות התצוגה: השורה מציגה שני תגים לכל היותר (מגבלת
# פריסה אמיתית — שלושה תגים דחסו את שם האמן ל-16px), ולכן מה שראשון כאן
# הוא מה שייראה.
ACTION = "ACTION"
SLOW_BURN = "SLOW BURN"
RELENTLESS = "RELENTLESS"
DARK = "DARK"
BRIGHT = "BRIGHT"
GRITTY = "GRITTY"
INTIMATE = "INTIMATE"

VOCABULARY = (ACTION, SLOW_BURN, RELENTLESS, DARK, BRIGHT, GRITTY, INTIMATE)


def _rules(n: dict) -> list[tuple[str, bool]]:
    """הכללים עצמם, מופרדים מהחיווט כדי שיהיו קריאים ובדיקים.

    `n.get(name)` ולא `n[name]`: מדידות שנשמרו לפני שמדדי הגוון נוספו
    עדיין תקפות (ראו `audio.normalized`), והן פשוט לא מזכות בתגים שדורשים
    אותם — במקום להפיל את הגזירה כולה.
    """
    def high(name: str) -> bool:
        value = n.get(name)
        return value is not None and value >= HIGH

    def low(name: str) -> bool:
        value = n.get(name)
        return value is not None and value <= LOW

    return [
        # חיתוך מהיר: הרבה מכות וגם חזק בפועל
        (ACTION, high("onset_rate") and high("loudness")),
        # מתחיל בשקט ונפתח — הקשת היא מה שמגדיר אותו, לא הקצב
        (SLOW_BURN, high("dynamic_span") and low("onset_rate")),
        # קיר קבוע בלי הרפיה: תנועה מתמדת דווקא בלי קשת
        (RELENTLESS, high("flux") and high("onset_rate") and low("dynamic_span")),
        # שלושת הבאים נשענים על `TIMBRE_RANGES`, שמסומנים ב-`audio.py`
        # כהערכה שטרם כוילה — ולכן הם הראשונים לבדיקה מול נתונים אמיתיים
        (DARK, low("centroid") and high("low_end")),
        (BRIGHT, high("centroid") and high("air")),
        # רועש/מעוות במובן הספקטרלי, לא "לא מוצלח"
        (GRITTY, high("flatness") and high("presence")),
        (INTIMATE, low("loudness") and low("low_end") and low("flux")),
    ]


def derive(features: "dict | None") -> list[str]:
    """התגים של גרסה אחת. רשימה ריקה כשאין מדידה — ולא ניחוש."""
    normalized = audio.normalized(features)
    if not normalized:
        return []
    return [name for name, matched in _rules(normalized) if matched]


def matches(features: "dict | None", wanted: str) -> bool:
    """האם הגרסה נושאת את התג המבוקש.

    גרסה שטרם נמדדה **עוברת** את המסנן במקום להיעלם: אותה החלטה שכבר
    התקבלה ב-`audio.matches_tempo`. מסנן שמעלים את מה שעוד לא נמדד היה
    מרוקן את המסך בדיוק ברגע שבו המדידה עוד רצה.
    """
    if wanted not in VOCABULARY:
        return True
    if not audio.measured(features):
        return True
    return wanted in derive(features)
