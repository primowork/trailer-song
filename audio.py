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


def envelope(features: "dict | None") -> "list[float]":
    """מעטפת העוצמה על פני התצוגה המקדימה, 0..1 לכל דגימה — איפה הגרסה
    מתפוצצת, לא רק כמה.

    מגיעה ישירות מהרכיב בדפדפן (`components/audio_meter`): ממוצע RMS
    בחלונות 50ms על פני כל הקליפ, מדוגם-מטה ומנורמל לשיא **של הטראק הזה
    עצמו** — ולכן זו צורה, לא עוצמה מוחלטת (זה כבר תפקיד `bigness`).

    מדידות שנשמרו לפני שהשדה הזה נוסף פשוט לא נושאות אותו: רשימה ריקה,
    ולא מעטפת בדויה. הקורא (שורת תוצאה, סרגל הנגן, Compare) מציג במקומה
    מצב סרק — אותו עיקרון בדיוק כמו ה-– של `_loudness_meter` כשאין ציון.
    """
    if not measured(features):
        return []
    values = features.get("envelope")
    if not isinstance(values, list):
        return []
    return [max(0.0, min(1.0, float(v))) for v in values
            if isinstance(v, (int, float))]


CHROMA_BINS = 12


def chroma(features: "dict | None") -> "list[float]":
    """פרופיל שנים-עשר הצלילים של הטראק, או רשימה ריקה.

    כמו `envelope`, מגיע כמו שהוא מהרכיב בדפדפן. מדידות שנשמרו לפני
    שהשדה נוסף פשוט לא נושאות אותו.
    """
    if not measured(features):
        return []
    values = features.get("chroma")
    if not isinstance(values, list) or len(values) != CHROMA_BINS:
        return []
    if not all(isinstance(v, (int, float)) for v in values):
        return []
    return [float(v) for v in values]


def _correlation(left: "list[float]", right: "list[float]") -> float:
    """מתאם פירסון בין שני וקטורים באותו אורך, -1..1.

    פירסון ולא קוסינוס: וקטורי כרומה הם כולם חיוביים ודי שטוחים, ולכן
    קוסינוס מחזיר ~0.9 גם לשני שירים שאין ביניהם שום קשר — הוא בעצם
    מודד שלשניהם יש אנרגיה. חיסור הממוצע מסלק בדיוק את הרכיב המשותף
    הזה, ומשאיר את מה שבאמת מבדיל: *אילו* צלילים בולטים מעל השאר.
    """
    size = len(left)
    mean_left = sum(left) / size
    mean_right = sum(right) / size
    numerator = sum((left[i] - mean_left) * (right[i] - mean_right)
                    for i in range(size))
    left_span = sum((value - mean_left) ** 2 for value in left) ** 0.5
    right_span = sum((value - mean_right) ** 2 for value in right) ** 0.5
    if left_span <= 0 or right_span <= 0:
        return 0.0
    return numerator / (left_span * right_span)


def chroma_similarity(features_a: "dict | None",
                      features_b: "dict | None") -> "float | None":
    """כמה שני טראקים חולקים מהלך הרמוני, 0..1 — או None בלי שתי מדידות.

    **חסין לטרנספוזיציה**: קאבר מועבר טונציה כל הזמן (זמרת עם טווח אחר,
    גיטרה מכוונת נמוך), וזו העברה של *כל* הפרופיל באותו מספר חצאי-טונים.
    לכן ההשוואה נעשית לכל שתים-עשרה ההזזות האפשריות והטובה שבהן נבחרת:
    אותו שיר בטונציה אחרת מקבל את אותו ציון כמו בטונציה המקורית.

    מה זה **לא**: זיהוי יצירה. הפרופיל ממוצע על פני הקליפ כולו ואינו
    מכיר סדר זמנים, ולכן שני שירים שונים באותו סולם עם אותם אקורדים
    שכיחים יקבלו ציון גבוה גם בלי שום קשר ביניהם. זה סימן נוסף בדירוג
    (ראו `RANK_HARMONY` ב-`app.py`), לא מסנן — ובמכוון: מסנן על סימן
    שלא כויל מול ייצוא אמיתי היה מעלים קאברים אמיתיים בשקט.
    """
    left, right = chroma(features_a), chroma(features_b)
    if not left or not right:
        return None
    best = max(_correlation(left, right[shift:] + right[:shift])
               for shift in range(CHROMA_BINS))
    # -1..1 → 0..1, כדי שיישב באותה סקאלה של שאר רכיבי הדירוג
    return max(0.0, min(1.0, (best + 1.0) / 2.0))


def describe(features: "dict | None") -> str:
    """המספרים הגולמיים לתצוגה, כדי שהכיול הבא יהיה מבוסס ולא ניחוש."""
    if not measured(features):
        return ""
    return (f"loudness {_number(features, 'loudness'):.2f} · "
            f"low end \u00d7{_number(features, 'low_end'):.2f} · "
            f"hits {_number(features, 'onset_rate'):.1f}/s · "
            f"dynamic span \u00d7{_number(features, 'dynamic_span'):.1f}")


# סינון הקצב חי היום ב-`tags.py`, כתגיות ACTION ו-SLOW BURN שנגזרות
# מאותה `onset_rate` שנמדדת כאן. `matches_tempo` שישב כאן לא נקרא מאף
# מקום בקוד המוצר: בררת ה-"Tempo" שבממשק רק הוסיפה את הטקסט שנבחר
# לשאילתת החנות, כלומר היא שינתה את החיפוש ולא סיננה לפי מה שנשמע.
# שני מנגנונים לאותה שאלה הם הדרך הבטוחה לכך שהם יסתרו זה את זה.
