"""מייצר את `chart_data.py` מנתוני מצעד בילבורד Hot 100 ההיסטוריים.

למה גנרטור אופליין ולא שליפה בזמן ריצה: מקור הנתונים הוא קובץ של ~44MB,
וטעינתו בכל רינדור של האפליקציה אינה אופציה. חוץ מזה ההיסטוריה 1958–2020
אינה משתנה, ולכן אין מה לרענן. הפלט הוא מודול פייתון סטטי שנכנס לגיט,
נקרא בעיניים בדיף, ורץ בלי רשת — בדיוק כמו `classics.py` שלצידו.

למה בכלל נתוני מצעד: הרשימות האצורות ב-`classics.py` נכתבו מהזיכרון, ולכן
אין בהן מדד ל"כמה השיר הזה מוכר" — וזו בדיוק התלונה שהובילה לקובץ הזה.
כאן ההיכרות נמדדת מהופעות בפועל במצעד לאורך שבעה עשורים.

הרצה:
    python tools/build_charts.py               # מוריד את המקור
    python tools/build_charts.py --source X    # משתמש בקובץ מקומי

מקור: https://github.com/mhollingshead/billboard-hot-100 (CC, מתעדכן יומית)
"""
import argparse
import collections
import json
import re
import sys
import urllib.request

SOURCE_URL = "https://raw.githubusercontent.com/mhollingshead/billboard-hot-100/main/all.json"
OUTPUT = "chart_data.py"

# חלון הכניסה: נספרים רק שבועות בשלוש השנים הראשונות של השיר במצעד.
# בלי זה "Running Up That Hill" (1985) מוביל את שנות ה-80 בזכות הוויראליות
# של 2022, ושיר משנת 1958 צובר 67 שבועות שמפוזרים על ארבעה עשורים.
ENTRY_WINDOW_YEARS = 2

# שירי חג נכנסים מחדש כל דצמבר במשך שישים שנה, ולכן סוחפים כל דירוג
# שמבוסס על ותק — עד כדי כך ש"All I Want For Christmas" היה השיר המוביל
# של שנות ה-2000 לפני המסנן הזה.
SEASONAL = re.compile(
    r"christmas|santa|jingle|rudolph|sleigh|mistletoe|winter wonderland|"
    r"silent night|feliz navidad|noel|xmas|auld lang|little drummer",
    re.IGNORECASE)

# תקרת חזרתיות: הבעיה שהמשתמש דיווח עליה. שני שירים לאמן בעשור.
ARTIST_CAP = 2
PER_DECADE = 120

# מיקוד השם לחיפוש קאברים: "Usher Featuring Lil Jon & Ludacris" הוא שאילתה
# גרועה. נחתכים רק צירופים חד-משמעיים — "&" ו-"and" נשארים, כי
# "Simon & Garfunkel" ו-"Derek And The Dominos" הם שם של הרכב אחד, ואין
# דרך אמינה להבדיל ביניהם לבין שיתוף פעולה חד-פעמי.
FEATURING = re.compile(
    r"\s+(?:featuring|feat\.?|f/|a\s+duet\s+with|duet\s+with|with)\s+.*$",
    re.IGNORECASE)

# עשור מלא מקבל 120 שירים. שנות ה-50 מקבלות פחות כי ה-Hot 100 מתחיל רק
# באוגוסט 1958 — 17 חודשי מצעד בלבד, ומעבר לכ-60 שירים הרשימה נגררת
# לשוליים במקום להישאר בשירים המוכרים.
DECADES = (("50's", 1958, 1959, 60), ("60's", 1960, 1969, 120),
           ("70's", 1970, 1979, 120), ("80's", 1980, 1989, 120),
           ("90's", 1990, 1999, 120), ("2000's", 2000, 2009, 120),
           ("2010's", 2010, 2020, 120))


def clean_artist(name: str) -> str:
    trimmed = FEATURING.sub("", (name or "").strip()).strip(" ,&")
    return trimmed or (name or "").strip()


def aggregate(charts: list) -> dict:
    """מקבץ את כל שבועות המצעד לכדי רשומה אחת לכל שיר."""
    debut = {}
    for chart in charts:
        year = int(chart["date"][:4])
        for row in chart["data"]:
            key = (row["artist"].strip(), row["song"].strip())
            if year < debut.get(key, 9999):
                debut[key] = year

    songs = {}
    for chart in charts:
        year = int(chart["date"][:4])
        for row in chart["data"]:
            key = (row["artist"].strip(), row["song"].strip())
            if year > debut[key] + ENTRY_WINDOW_YEARS:
                continue
            entry = songs.setdefault(key, {"weeks": 0, "top10": 0, "number_one": 0,
                                           "peak": 101, "points": 0, "year": debut[key]})
            position = row["this_week"]
            entry["weeks"] += 1
            entry["points"] += 101 - position
            entry["peak"] = min(entry["peak"], row["peak_position"])
            if position <= 10:
                entry["top10"] += 1
            if position == 1:
                entry["number_one"] += 1
    return songs


def familiarity(entry: dict) -> int:
    """ציון היכרות: ותק במצעד, ועל גביו פרמיה על השיא.

    הוותק לבדו מעלה לראש סלואוז ארוכי-טווח על פני להיטים איקוניים —
    "I Go Crazy" הופיע מעל "Stayin' Alive" בשנות ה-70. רכיבי השיא מתקנים.
    """
    return entry["points"] + 40 * entry["top10"] + 120 * entry["number_one"]


def pick(songs: dict, first: int, last: int, cap: int = ARTIST_CAP,
         limit: int = PER_DECADE) -> list:
    ranked = sorted(
        ((key, value) for key, value in songs.items()
         if first <= value["year"] <= last and not SEASONAL.search(key[1])),
        key=lambda item: -familiarity(item[1]))

    chosen, seen = [], collections.Counter()
    for (artist, song), value in ranked:
        name = clean_artist(artist)
        if seen[name.lower()] >= cap:
            continue
        seen[name.lower()] += 1
        chosen.append({"artist": name, "track": song, "year": value["year"]})
        if len(chosen) >= limit:
            break
    return chosen


def render(decades: list) -> str:
    lines = ['"""שירי המצעד המוכרים ביותר לפי עשור — נוצר, לא נערך ידנית.',
             "",
             "נוצר על ידי `tools/build_charts.py` מתוך מצעדי Billboard Hot 100",
             "ההיסטוריים (https://github.com/mhollingshead/billboard-hot-100).",
             "כל עשור מדורג לפי ביצועים בפועל במצעד, עם תקרה של שני שירים לאמן.",
             "",
             "ה-Hot 100 מתחיל ב-4 באוגוסט 1958, ולכן 1950–1957 מגיעות",
             'מהרשימות האצורות ב-`classics.py` ולא מכאן.',
             '"""',
             "",
             "DECADE_HITS: dict[str, tuple[dict, ...]] = {"]
    for label, entries in decades:
        lines.append(f'    "{label}": (')
        for entry in entries:
            artist = entry["artist"].replace('"', '\\"')
            track = entry["track"].replace('"', '\\"')
            lines.append(f'        {{"artist": "{artist}", "track": "{track}", '
                         f'"year": {entry["year"]}}},')
        lines.append("    ),")
    lines.append("}")
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", help="קובץ all.json מקומי במקום הורדה")
    parser.add_argument("--output", default=OUTPUT)
    args = parser.parse_args()

    if args.source:
        with open(args.source, encoding="utf-8") as handle:
            charts = json.load(handle)
    else:
        print(f"מוריד {SOURCE_URL} …", file=sys.stderr)
        with urllib.request.urlopen(SOURCE_URL, timeout=300) as response:
            charts = json.load(response)

    songs = aggregate(charts)
    decades = [(label, pick(songs, first, last, limit=limit))
               for label, first, last, limit in DECADES]
    with open(args.output, "w", encoding="utf-8") as handle:
        handle.write(render(decades))

    for label, entries in decades:
        print(f"{label}: {len(entries)} שירים", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
