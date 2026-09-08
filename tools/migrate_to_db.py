"""מיגרציה חד-פעמית: קבצי ה-JSON הקיימים -> Postgres.

הנתונים בפרודקשן נוצרו לפני שהייתה זהות, ולכן הם מרחב אחד. ההחלטה
(של בעל האפליקציה): **החשבון שלו יורש אותם.** מה שאישי עובר למשתמש
שנמסר ב-`--email`; מה שעובדתי — מדידות, קאש YouTube, מצעדים — עובר
למרחב המשותף ואינו שייך לאיש.

    DATABASE_URL=... python tools/migrate_to_db.py --email you@example.com

ברירת המחדל היא **הרצה יבשה**. בלי `--commit` שום דבר לא נכתב: ההרצה
הראשונה אמורה להיות מול עותק של הנתונים, לא מול הפרודקשן.
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import db  # noqa: E402
import storage  # noqa: E402


def _read(name: str, default):
    """קורא ישירות מהדיסק ולא דרך ה-facade: ה-facade כבר עלול להצביע
    ל-Postgres (שהרי `DATABASE_URL` מוגדר כשמריצים את זה), ואז המיגרציה
    הייתה מעתיקה את היעד לעצמו."""
    path = os.path.join(storage.DATA_DIR, name) if storage.DATA_DIR else ""
    if not path or not os.path.exists(path):
        return default
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data if type(data) is type(default) else default


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--email", required=True,
                        help="המשתמש שיירש את הפלייליסט, הדחיות והחסימות")
    parser.add_argument("--commit", action="store_true",
                        help="כתיבה בפועל. בלעדיו — הרצה יבשה בלבד")
    args = parser.parse_args()

    if not db.available():
        print("DATABASE_URL is not set (or psycopg is missing) — nothing to migrate into.")
        return 1

    personal = {
        "favorites": _read("favorites.json", {}),
        "rejections": _read("rejections.json", {}),
        "blacklist": _read("blacklist.json", []),
    }
    shared = {
        "measurements": _read("bigness.json", {}),
        "evidence": _read(storage.EVIDENCE_FILE, {}),
        "charts": _read(storage.IMPORTED_CHARTS, {}),
    }

    print(f"Source folder: {storage.DATA_DIR or '(none)'}")
    for name, items in {**personal, **shared}.items():
        print(f"  {name}: {len(items)}")

    if not args.commit:
        print("\nDry run — nothing was written. Re-run with --commit.")
        return 0

    uid = db.user_id(args.email.strip().lower())
    db.save_favorites(uid, personal["favorites"])
    db.save_rejections(uid, personal["rejections"])
    db.save_blacklist(uid, personal["blacklist"])
    db.save_bigness(shared["measurements"])
    db.save_evidence(shared["evidence"])
    db.save_charts(shared["charts"])
    print(f"\nMigrated into user {uid} ({args.email}).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
