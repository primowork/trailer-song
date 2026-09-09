"""מדפיס את פילוח התגיות על מטמון מדידות אמיתי — צעד הכיול של `tags.py`.

הספים ב-`tags.py` נבחרו מתוך הטווחים המתועדים ב-`audio.py`, ולא מתוך
התפלגות אמיתית של גרסאות. הכלי הזה סוגר את הפער: הוא קורא את המדידות
השמורות, מריץ עליהן את הכללים, ומראה במסך אחד אם הספים מחזיקים.

מה מחפשים בפלט:
  * תגית שלא נדלקת אף פעם — הסף גבוה מדי, או שהמדד לא נמדד בכלל
  * תגית שנדלקת כמעט על הכל — היא לא מבדילה בין טראקים ולכן אינה מדד
  * תגיות הגוון מדווחות בנפרד, כי `audio.TIMBRE_RANGES` מצהיר על עצמו
    כהערכה שממתינה לכיול. מספר נמוך שם יכול להיות סף שגוי *או* טווח שגוי,
    ואין דרך להבחין ביניהם מכאן.

הרצה:
    python tools/tag_report.py                 # המטמון המשותף (DB או /data)
    python tools/tag_report.py --source X.json # ייצוא מקומי
"""
import argparse
import collections
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import audio  # noqa: E402
import tags  # noqa: E402

# מתחת לזה "אף פעם" ומעליו "כמעט על הכל" — שתי הצורות שבהן תגית מפסיקה
# להיות מידע. אלה סימונים לעין אנושית ולא כישלון: מדגם של עשר מדידות
# יפעיל אותם על לא כלום.
NEVER = 0.0
ALWAYS = 0.90


def _load(source: "str | None") -> dict:
    if source:
        with open(source, encoding="utf-8") as handle:
            return json.load(handle)
    import storage
    return storage.load_bigness()


def _bar(share: float, width: int = 28) -> str:
    return "#" * int(round(share * width)) + "." * (width - int(round(share * width)))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", help="קובץ JSON של מדידות במקום המטמון")
    args = parser.parse_args()

    cache = _load(args.source)
    measured = {key: value for key, value in cache.items()
                if audio.measured(value)}
    if not measured:
        print(f"{len(cache)} רשומות, אף אחת מהן אינה מדידה תקפה. אין מה לדווח.")
        return 1

    # מדדי הגוון נספרים בנפרד: מדידה שנשמרה לפני שהם נוספו אינה יכולה
    # להדליק תגית גוון, וספירתה במכנה הייתה מציגה סף תקין ככישלון.
    with_timbre = [features for features in measured.values()
                   if features.get("centroid") is not None]

    counts = collections.Counter()
    untagged = 0
    for features in measured.values():
        found = tags.tags_for(features)
        counts.update(found)
        if not found:
            untagged += 1

    print(f"{len(cache)} רשומות במטמון · {len(measured)} מדידות תקפות · "
          f"{len(with_timbre)} מהן עם מדדי גוון")
    print()
    for group, names, total in (
            ("מכוילות (audio.WEIGHTS)", tags.CALIBRATED_TAGS, len(measured)),
            ("הערכה (audio.TIMBRE_RANGES)", tags.ESTIMATED_TAGS, len(with_timbre))):
        print(group)
        if not total:
            print("   אין מדידות בקבוצה הזו.")
            print()
            continue
        for name in names:
            share = counts[name] / total
            flag = ("  ← אף פעם" if share <= NEVER else
                    "  ← כמעט על הכל" if share >= ALWAYS else "")
            print(f"   {name:<11} {_bar(share)} {counts[name]:>4}/{total} "
                  f"{share * 100:>5.1f}%{flag}")
        print()

    print(f"בלי אף תגית: {untagged}/{len(measured)} "
          f"({untagged / len(measured) * 100:.1f}%)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
