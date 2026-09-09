"""תגיות שנגזרות מהמדידה שרצה בדפדפן — "איך הטראק נשמע", לא "מה כתוב בכותרת".

`search.trailer_indicators` קורא את הכותרת, ולכן הוא יודע רק מה שמישהו *הצהיר*
("Epic Trailer Version"). הקובץ הזה קורא את המספרים שהרכיב `audio_meter` מדד
בדפדפן, ולכן הוא מתאר את מה שבאמת נשמע — גם כשהכותרת שותקת או משקרת.

אין מודל שפה כאן וזו לא פשרה: הוא לא יכול לשמוע את הפריוויו, ולכן היה מנחש
מהכותרת ומהאמן — בדיוק המידע שכבר מנוצל ב-`search.py`. הדפדפן של המאזין כן
שומע, הוא מודד תשעה מספרים לכל גרסה, המדידה נשמרת ומשותפת בין המשתמשים,
והיא לא עולה כלום.

התגיות **אינן נשמרות**. הן פונקציה טהורה של מדידה ששמורה ממילא, ולכן עותק
שמור היה מתיישן ברגע שהספים כאן משתנים.
"""

import audio

# אוצר המילים סגור ולא טקסט חופשי: המסנן ב-UI חייב להשוות מול ערך ידוע.
ACTION = "Action"
SLOW_BURN = "Slow burn"
RELENTLESS = "Relentless"
DARK = "Dark"
BRIGHT = "Bright"
GRITTY = "Gritty"
INTIMATE = "Intimate"

# ארבע הראשונות נשענות על `audio.WEIGHTS`, שטווחיו כוילו מול מדידות אמיתיות.
# שלוש האחרונות נשענות על `audio.TIMBRE_RANGES`, שהקובץ שלו מצהיר במפורש
# שהוא "הערכה ומיועד לכיול על ייצוא אמיתי" — כלומר הן עומדות על שכבת הערכה
# נוספת. ההפרדה כאן ולא בהערה בלבד, כדי ש-`tools/tag_report.py` יוכל לדווח
# עליהן בנפרד ולא לערבב ודאות עם ניחוש.
CALIBRATED_TAGS = (ACTION, SLOW_BURN, RELENTLESS, INTIMATE)
ESTIMATED_TAGS = (DARK, BRIGHT, GRITTY)

# הסדר הוא סדר התצוגה: מה שמופיע ראשון הוא מה שנבחר כתג היחיד בשורה.
TAGS = (*CALIBRATED_TAGS[:3], *ESTIMATED_TAGS, INTIMATE)


def _rules(values: dict) -> "list[tuple[str, bool]]":
    """הכללים עצמם, על הערכים המנורמלים 0..1 של `audio.normalized`.

    נורמול ולא מספרים גולמיים: סף על `onset_rate` גולמי היה מספר קסם שאיש
    לא יכול לקשר לטווח שממנו הוא נגזר, ושינוי טווח ב-`audio.py` היה מזיז
    את המשמעות של התגית בלי לגעת בקובץ הזה.

    `.get(..., None)` על מדדי הגוון: מדידות שנשמרו לפני שהם נוספו עדיין
    תקפות, והן פשוט לא מזכות בתגיות גוון. ברירת מחדל 0.0 הייתה מתייגת כל
    מדידה ישנה כ-DARK.
    """
    loud = values.get("loudness", 0.0)
    hits = values.get("onset_rate", 0.0)
    span = values.get("dynamic_span", 0.0)
    low = values.get("low_end", 0.0)
    centroid = values.get("centroid")
    air = values.get("air")
    flatness = values.get("flatness")
    return [
        (ACTION, hits >= 0.55 and loud >= 0.45),
        # קצב גבוה *בלי* קשת: מכה אחידה מתחילתה ועד סופה. זה ההפך מ-SLOW BURN
        # ולא וריאציה של ACTION, ולכן תגית משלו.
        (RELENTLESS, hits >= 0.55 and span <= 0.30),
        (SLOW_BURN, span >= 0.55 and hits <= 0.35),
        (DARK, centroid is not None and air is not None
         and centroid <= 0.30 and air <= 0.35),
        (BRIGHT, centroid is not None and air is not None
         and centroid >= 0.55 and air >= 0.35),
        (GRITTY, flatness is not None and flatness >= 0.50),
        (INTIMATE, loud <= 0.30 and hits <= 0.35 and low <= 0.40),
    ]


def tags_for(features: "dict | None") -> "list[str]":
    """כל התגיות שהמדידה הזו מזכה בהן, בסדר התצוגה. בלי מדידה — רשימה ריקה.

    "לא נמדד" אינו "לא מתאים": שורה בלי מדידה לא מקבלת תגית, והמסנן למטה
    מעביר אותה הלאה במקום להעלים אותה.
    """
    values = audio.normalized(features)
    if not values:
        return []
    fired = {name for name, hit in _rules(values) if hit}
    return [name for name in TAGS if name in fired]


def primary_tag(features: "dict | None") -> "str | None":
    """התגית האחת שמוצגת בשורה, או None.

    אחת ולא כולן: השורה מציגה כבר תג *מוצהר* אחד, ושני תגים נוספים דחסו
    את שם האמן (אותה מדידה שמתועדת ב-`render_track`).
    """
    found = tags_for(features)
    return found[0] if found else None


def matches(features: "dict | None", wanted: str) -> bool:
    """סינון "נשמע כמו". ערך שאינו תגית מוכרת — כולל תווית "בלי סינון" —
    מכבה את המסנן.

    בדיקה חיובית ("האם ביקשו תגית שאני מכיר") ולא השוואה לתווית "הכל"
    שהוקלדה כאן ביד: התווית מוגדרת ב-`search.py`, ותרגום שלה שם היה
    משתיק את המסנן בשקט ובלי שום סימן. בדיקה חיובית לא יכולה להישבר
    ככה, והיא גם שומרת על הקובץ הזה בלי תלות בתוויות התצוגה.

    בלי מדידה הכל עובר: אחרת המסנן היה מרוקן את הרשימה בכל חיפוש חדש,
    לפני שהדפדפן הספיק למדוד ולו שורה אחת.
    """
    if wanted not in TAGS:
        return True
    if not audio.measured(features):
        return True
    return wanted in tags_for(features)
