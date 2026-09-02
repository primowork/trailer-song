"""ציון "גודל" מוחלט לטראק, מתוך מדדים שנמדדו בדפדפן.

המדידה עצמה רצה אצל המשתמש ב-Web Audio API (`components/audio_meter/index.html`)
ומחזירה ארבעה מספרים גולמיים. כאן מתבצע רק התרגום שלהם לציון אחד — ולכן הקובץ
הזה נבדק במלואו בלי דפדפן, בלי רשת ובלי תלות כבדה.

למה מוחלט ולא יחסי: הגרסה הקודמת השוותה כל קאבר ל"מקור" ודרשה preview לשני
הצדדים. "האם הטראק הזה ענק" היא תכונה של הטראק עצמו. בנוסף המדד הישן חתך את
העוצמה ב-1.0, כך שכל טראק ממוסטר קיבל בדיוק 1.0 וההבדל בין חזק לחזק-מאוד נמחק.
"""

# המדדים שהרכיב בדפדפן מחזיר, והערך שמזכה בניקוד מלא:
#   loudness   RMS על כל הדגימות, בלי חיתוך
#   low_end    יחס האנרגיה מתחת ל-200Hz — שם יושבים התופים וה-braam
#   onset_rate קפיצות אנרגיה לשנייה — צפיפות מכות
#   crest      max|x| חלקי RMS — הקשת מהשקט לדרופ
# (משקל, רצפה, ערך לניקוד מלא). הרצפה קיימת כי לכל טראק ממוסטר יש כבר עוצמה,
# בס וקשת מסוימים — בלעדיה גם בלדה אקוסטית אוספת ניקוד על עצם היותה מוקלטת.
WEIGHTS = {
    "loudness": (35, 0.04, 0.22),
    "low_end": (30, 0.12, 0.45),
    "onset_rate": (20, 0.8, 3.5),
    "crest": (15, 1.6, 3.0),
}

# מעל הסף הזה הגרסה נחשבת "גדולה מהחיים" לפי המדידה, בלי קשר לכותרת שלה
BIG_VERSION_THRESHOLD = 60


def _scaled(value: float, floor: float, full_credit: float) -> float:
    """0..1 ליניארי מהרצפה ועד לערך שמזכה בניקוד מלא."""
    span = full_credit - floor
    if span <= 0:
        return 0.0
    try:
        value = float(value)
    except (TypeError, ValueError):
        return 0.0
    return max(0.0, min((value - floor) / span, 1.0))


def bigness(features: "dict | None") -> int:
    """ציון 0..100. מקבל את ה-dict שהרכיב בדפדפן החזיר."""
    if not features or features.get("error"):
        return 0
    score = sum(weight * _scaled(features.get(name, 0.0), floor, full)
                for name, (weight, floor, full) in WEIGHTS.items())
    return int(round(max(0.0, min(score, 100.0))))


def measured(features: "dict | None") -> bool:
    """האם יש מדידה בכלל. 'לא נמדד' אינו 'קטן'."""
    return bool(features) and not features.get("error")


def is_big_version(features: "dict | None",
                   threshold: int = BIG_VERSION_THRESHOLD) -> bool:
    return measured(features) and bigness(features) >= threshold


def describe(features: "dict | None") -> str:
    """המספרים הגולמיים לתצוגה, כדי שהכיול הבא יהיה מבוסס ולא ניחוש."""
    if not measured(features):
        return ""
    return (f"עוצמה {features.get('loudness', 0):.2f} · "
            f"בס {features.get('low_end', 0):.2f} · "
            f"מכות {features.get('onset_rate', 0):.1f}/שנ׳ · "
            f"קשת ×{features.get('crest', 0):.1f}")


def matches_tempo(features: "dict | None", tempo_filter: str) -> bool:
    """סינון קצב לפי צפיפות המכות שנמדדה. בלי מדידה — הכל עובר."""
    if not tempo_filter or tempo_filter == "הכל" or not measured(features):
        return True
    rate = features.get("onset_rate", 0.0)
    if not rate:
        return True
    if tempo_filter == "Fast Action":
        return rate >= 2.0
    if tempo_filter == "Slow Build-up":
        return rate < 2.0
    return True
