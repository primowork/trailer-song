"""מעביר את הנתונים שנצברו לפני ההתחברות אל חשבון אחד.

    python tools/adopt_data.py --email you@example.com          # יבש
    python tools/adopt_data.py --email you@example.com --commit

**למה זה נחוץ.** עד שההתחברות נדלקה, לכל המבקרים היה מרחב אחד: הקבצים
השטוחים ב-`DATA_DIR`. ברגע ש-`[auth]` מוגדר, `storage._personal()` מחזיר
True למשתמש מחובר, והקריאות שלו עוברות ל-`DATA_DIR/users/<slug>/` —
תיקייה חדשה וריקה. כלומר בלי הסקריפט הזה בעל האפליקציה מתחבר ורואה
פלייליסט **ריק**, בזמן שכל מבקר אנונימי ממשיך לראות את האוסף המלא שלו.
בדיוק הפוך ממה שההתחברות אמורה לעשות.

`tools/migrate_to_db.py` לא מטפל בזה: הוא יוצא מיד כשאין `DATABASE_URL`.
זה המקבילה שלו לבקאנד הקבצים.

**מעביר ולא מעתיק**, לפי החלטת המשתמש: אחרי ההעברה המרחב האנונימי ריק,
כלומר האוסף הופך פרטי. מה שמשותף בכוונה — מדידות, קאש YouTube, מצעדים
מיובאים, ומונה המכסה — **לא זז**.
"""
import argparse
import json
import os
import shutil
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import accounts  # noqa: E402
import storage  # noqa: E402

# אישי בלבד. השאר נשאר במרחב המשותף, וזו החלוקה שכבר מתועדת ב-`storage.py`.
PERSONAL = ("favorites.json", "rejections.json", "blacklist.json")


def _count(path: str) -> str:
    """כמה פריטים בקובץ, לדוח היבש. שגיאה אינה מפילה — זו הדפסה בלבד."""
    try:
        with open(path, encoding="utf-8") as handle:
            return str(len(json.load(handle)))
    except Exception as exc:
        return f"unreadable ({exc})"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--email", required=True,
                        help="המייל שאיתו תתחבר בגוגל — הוא שקובע את התיקייה")
    parser.add_argument("--commit", action="store_true",
                        help="העברה בפועל. בלעדיו — הרצה יבשה בלבד")
    args = parser.parse_args()

    email = args.email.strip().lower()
    if not storage.DATA_DIR:
        print("No writable data folder — nothing to adopt.")
        return 1

    # התיקייה מחושבת דרך `storage._slug` ולא בגיבוב מקומי. גיבוב שמחושב
    # פעמיים בשני מקומות הוא בדיוק איך שמיגרציה כותבת בהצלחה מלאה
    # לתיקייה שאיש לא קורא ממנה.
    subject = accounts.Subject("user", f"user:{email}", email)
    slug = storage._slug(subject)
    target_dir = os.path.join(storage.DATA_DIR, "users", slug)

    print(f"Data folder : {storage.DATA_DIR}")
    print(f"Account     : {email}")
    print(f"Goes to     : {target_dir}\n")

    moves, blocked = [], []
    for name in PERSONAL:
        source = os.path.join(storage.DATA_DIR, name)
        target = os.path.join(target_dir, name)
        if not os.path.exists(source):
            print(f"  {name:18} — not present, skipping")
            continue
        if os.path.exists(target) and os.path.getsize(target) > 2:
            # יעד קיים ולא ריק פירושו שהחשבון כבר שמר משהו. דריסה כאן
            # מוחקת נתונים אמיתיים, ולכן זו עצירה ולא אזהרה.
            blocked.append(name)
            print(f"  {name:18} — TARGET ALREADY HAS DATA, refusing")
            continue
        print(f"  {name:18} {_count(source):>6} items -> {slug}/")
        moves.append((source, target))

    shared = [n for n in ("bigness.json", storage.EVIDENCE_FILE,
                          storage.IMPORTED_CHARTS, storage.QUOTA_FILE)
              if os.path.exists(os.path.join(storage.DATA_DIR, n))]
    if shared:
        print(f"\nStaying shared (untouched): {', '.join(shared)}")

    if blocked:
        print(f"\nRefusing to overwrite: {', '.join(blocked)}. "
              "Move or delete those files first.")
        return 1
    if not moves:
        print("\nNothing to move.")
        return 0
    if not args.commit:
        print("\nDry run — nothing was moved. Re-run with --commit.")
        return 0

    os.makedirs(target_dir, exist_ok=True)
    for source, target in moves:
        shutil.move(source, target)
    print(f"\nMoved {len(moves)} file(s) into {slug}/. "
          "Anonymous visitors now see an empty app.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
