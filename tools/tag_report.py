"""כיול התגים מול מדידות אמיתיות.

    python tools/tag_report.py [נתיב ל-bigness.json]

הבדיקה היחידה שיש לתגים. מדפיס לכל תג כמה אחוז מהגרסאות שנמדדו נושאות
אותו, וגם כמה גרסאות לא קיבלו אף תג.

**מה נחשב תקין:** תג בטווח שמבדיל בין שורות — לא 0% (כלל שאי אפשר
לספק) ולא כמעט 100% (כלל שאינו מבחין בין כלום). ההערה ליד `WEIGHTS`
ב-`audio.py` מתעדת בדיוק את הכשל השני, בגרסה קודמת של אותה מערכת ניקוד:
"מדד שכולם מקבלים עליו ניקוד מלא אינו מדד".
"""
import json
import os
import sys
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import audio  # noqa: E402
import storage  # noqa: E402
import tags as tags_module  # noqa: E402


def main() -> int:
    path = sys.argv[1] if len(sys.argv) > 1 else os.path.join(storage.DATA_DIR or "", "bigness.json")
    if not path or not os.path.exists(path):
        print(f"No measurements at {path or '(no data folder)'}")
        return 1

    with open(path, encoding="utf-8") as handle:
        cache = json.load(handle)

    measured = [features for features in cache.values() if audio.measured(features)]
    if not measured:
        print(f"{path}: no usable measurements in {len(cache)} records.")
        return 1

    # התפלגות ערכים זהים היא בעצמה ממצא: קובץ מדידות שכולו אותו טראק
    # הוא נתוני בדיקה, ואי אפשר לכייל מולו שום דבר.
    distinct = len({json.dumps(f, sort_keys=True) for f in measured})
    print(f"{path}\n{len(measured)} measured versions, {distinct} distinct\n")
    if distinct < 10:
        print("!! Too few distinct measurements to calibrate against. "
              "This looks like test data, not a real cache.\n")

    counts = Counter()
    untagged = 0
    for features in measured:
        found = tags_module.derive(features)
        if not found:
            untagged += 1
        counts.update(found)

    print(f"{'tag':12} {'n':>5} {'share':>7}")
    for name in tags_module.VOCABULARY:
        n = counts[name]
        share = n / len(measured)
        flag = ""
        if share == 0:
            flag = "  <- never fires"
        elif share > 0.80:
            flag = "  <- fires on almost everything"
        print(f"{name:12} {n:>5} {share:>6.0%}{flag}")
    print(f"\n{untagged} of {len(measured)} versions ({untagged / len(measured):.0%}) got no tag at all.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
