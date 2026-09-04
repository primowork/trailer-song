"""ציון "גודל" מוחלט לטראק, מתוך מדדים שנמדדו בדפדפן.

המדידה עצמה רצה אצל המשתמש ב-Web Audio API (`components/audio_meter/index.html`)
ומחזירה ארבעה מספרים גולמיים. כאן מתבצע רק התרגום שלהם לציון אחד — ולכן הקובץ
הזה נבדק במלואו בלי דפדפן, בלי רשת ובלי תלות כבדה.

למה מוחלט ולא יחסי: הגרסה הקודמת השוותה כל קאבר ל"מקור" ודרשה preview לשני
הצדדים. "האם הטראק הזה ענק" היא תכונה של הטראק עצמו. בנוסף המדד הישן חתך את
העוצמה ב-1.0, כך שכל טראק ממוסטר קיבל בדיוק 1.0 וההבדל בין חזק לחזק-מאוד נמחק.
"""

# המדדים שהרכיב בדפדפן מחזיר, והערך שמזכה בניקוד מלא:
#   loudness      RMS על כל הדגימות, בלי חיתוך
#   low_end       אנרגיה מתחת ל-120Hz חלקי האנרגיה ב-120–2000Hz
#   onset_rate    קפיצות אנרגיה לשנייה — צפיפות מכות
#   dynamic_span  10% החלונות החזקים חלקי 25% החלשים — הקשת מהשקט לדרופ
# (משקל, רצפה, ערך לניקוד מלא). הרצפה קיימת כי לכל טראק ממוסטר יש כבר עוצמה,
# בס וקשת מסוימים — בלעדיה גם בלדה אקוסטית אוספת ניקוד על עצם היותה מוקלטת.
#
# הטווחים כאן כוילו מחדש מול מדידות אמיתיות: הגרסה הראשונה נתנה ניקוד מלא על
# הבס ועל הקשת לכל טראק (הערכים בשטח היו 0.89–1.00 מול סף 0.45, ו-5.6–7.7 מול
# סף 3.0), כך ש-45 מ-100 הנקודות היו קבועות ו"light version" קיבל 68 מול 69 של
# "Epic Trailer Version". מדד שכולם מקבלים עליו ניקוד מלא אינו מדד.
WEIGHTS = {
    "loudness": (35, 0.08, 0.30),
    "low_end": (30, 0.8, 3.0),
    "onset_rate": (20, 0.8, 3.5),
    "dynamic_span": (15, 1.5, 6.0),
}

# מעל הסף הזה הגרסה נחשבת "גדולה מהחיים" לפי המדידה, בלי קשר לכותרת שלה
BIG_VERSION_THRESHOLD = 60
# ומתחת לזה היא באמת רגועה. מה שביניהם מוצג כ"בינוני" ולא מוכרע: הטווחים
# ב-WEIGHTS כוילו על מדגם קטן, וקביעה נחרצת באמצע היא יותר ממה שהם מצדיקים.
MID_VERSION_THRESHOLD = 35


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


# מדדי גוון, לשימוש `taste.py` בלבד — הם *לא* נכנסים לציון הגודל, כי "גדול"
# הוא שאלה של עוצמה ולא של צבע. ארבעת מדדי העוצמה שב-WEIGHTS הם כולם
# סטטיסטיקות RMS, ולכן braam אפל ופנפרה בהירה יכולים לקבל בהם ערכים כמעט
# זהים; אלה המדדים שמפרידים ביניהם.
# (רצפה, ערך עליון). הטווחים הם הערכה ומיועדים לכיול על ייצוא אמיתי.
TIMBRE_RANGES = {
    "centroid": (0.03, 0.18),    # מרכז ספקטרלי: אפל → בהיר
    "flatness": (0.005, 0.20),   # טונאלי ונקי → רועש ומעוות
    "air": (0.002, 0.10),        # אנרגיה מעל 8kHz
    "presence": (0.02, 0.30),    # אנרגיה 2.5–8kHz
    "flux": (0.05, 0.45),        # מיתרים מתמשכים → פרקושן קצבי
}


def normalized(features: "dict | None") -> "dict | None":
    """המדדים הגולמיים על סקאלה אחידה 0..1, או None כשאין מדידה.

    הנרמול חי כאן ולא אצל הקורא כי הטווחים הם ידע של המודול הזה. `taste.py`
    משווה טראקים זה לזה במרחב הזה, ומדדים בסקאלות שונות (עוצמה 0.1–0.3 מול
    קשת 1.5–6.0) אינם ברי-השוואה בלי הנרמול.

    מדדי הגוון מוחזרים רק כשהם קיימים בפועל: מדידות שנשמרו לפני שהם נוספו
    עדיין תקפות, והן פשוט מתוארות בפחות מימדים.
    """
    if not measured(features):
        return None
    result = {name: _scaled(features.get(name, 0.0), floor, full)
              for name, (_, floor, full) in WEIGHTS.items()}
    for name, (floor, full) in TIMBRE_RANGES.items():
        if features.get(name) is not None:
            result[name] = _scaled(features[name], floor, full)
    return result


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


def _number(features: dict, name: str) -> float:
    """מדד בודד כמספר. המדידה מגיעה מהדפדפן, ולכן אינה נתון מהימן: ערך
    שאינו מספר היה מפיל את הכרטיס כולו על שגיאת פורמט."""
    try:
        return float(features.get(name) or 0.0)
    except (TypeError, ValueError):
        return 0.0


def describe(features: "dict | None") -> str:
    """המספרים הגולמיים לתצוגה, כדי שהכיול הבא יהיה מבוסס ולא ניחוש."""
    if not measured(features):
        return ""
    return (f"עוצמה {_number(features, 'loudness'):.2f} · "
            f"בס ×{_number(features, 'low_end'):.2f} · "
            f"מכות {_number(features, 'onset_rate'):.1f}/שנ׳ · "
            f"קשת ×{_number(features, 'dynamic_span'):.1f}")


def matches_tempo(features: "dict | None", tempo_filter: str) -> bool:
    """סינון קצב לפי צפיפות המכות שנמדדה. בלי מדידה — הכל עובר."""
    if not tempo_filter or tempo_filter == "הכל" or not measured(features):
        return True
    rate = _number(features, "onset_rate")
    if not rate:
        return True
    if tempo_filter == "Fast Action":
        return rate >= 2.0
    if tempo_filter == "Slow Build-up":
        return rate < 2.0
    return True
