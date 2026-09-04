import collections
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import chart_data
import classics

GENRE_LISTS = (classics.POP_CLASSICS, classics.ROCK_CLASSICS, classics.BLUES_CLASSICS)


def test_lists_are_reasonably_sized():
    # רשימה אצורה, לא ספירה מדויקת — הבדיקה היא על סדר הגודל
    assert 150 <= len(classics.POP_CLASSICS) <= 250
    assert 150 <= len(classics.ROCK_CLASSICS) <= 250
    assert 80 <= len(classics.BLUES_CLASSICS) <= 200


def test_entries_have_the_expected_shape():
    for entry in classics.ALL_CLASSICS:
        assert entry["artist"].strip()
        assert entry["track"].strip()
        assert 1950 <= entry["year"] <= 2020


def test_no_duplicate_song_anywhere():
    """גם בתוך רשימה וגם בין רשימות: אותו שיר פעמיים הוא מפתח widget כפול."""
    seen = set()
    for entry in classics.ALL_CLASSICS:
        key = (entry["artist"].lower(), entry["track"].lower())
        assert key not in seen, f"duplicate: {key}"
        seen.add(key)


def test_each_genre_list_spans_the_full_range_of_decades():
    for entries in GENRE_LISTS:
        years = [e["year"] for e in entries]
        assert min(years) < 1960
        assert max(years) >= 2019


# ---------- קטגוריות ----------

def test_every_category_has_entries():
    for name, entries in classics.CATEGORIES.items():
        assert entries, f"קטגוריה ריקה: {name}"


def test_a_decade_category_contains_only_that_decade():
    for label, first in (("50's", 1950), ("80's", 1980), ("2000's", 2000)):
        years = [e["year"] for e in classics.CATEGORIES[label]]
        assert min(years) >= first
        assert max(years) <= first + 9


def test_every_decade_comes_from_the_chart_data():
    """העשורים 60–2010 הם נתוני מצעד, לא הרשימות האצורות."""
    for label in ("60's", "70's", "80's", "90's", "2000's", "2010's"):
        assert classics.CATEGORIES[label] is chart_data.DECADE_HITS[label]


def test_the_fifties_bridge_the_gap_before_the_hot_100():
    """ה-Hot 100 מתחיל באוגוסט 1958 — לפני כן רק הרשימות האצורות."""
    years = [e["year"] for e in classics.CATEGORIES["50's"]]
    assert min(years) < 1958, "חסרות השנים שלפני תחילת המצעד"
    assert max(years) >= 1958, "חסרים נתוני המצעד עצמו"


def test_derived_categories_are_subsets_of_their_source():
    assert set(map(id, classics.CATEGORIES["🎤 פופ קלאסי"])) <= set(map(id, classics.POP_CLASSICS))
    assert set(map(id, classics.CATEGORIES["🎸 רוק קלאסי"])) <= set(map(id, classics.ROCK_CLASSICS))


# ---------- תקרת חזרתיות ----------

def test_no_artist_repeats_more_than_twice_in_any_category():
    """התלונה שהובילה לשינוי: 53%–64% מהשירים היו של אמנים חוזרים."""
    for name, entries in classics.CATEGORIES.items():
        counts = collections.Counter(e["artist"].casefold() for e in entries)
        artist, most = counts.most_common(1)[0]
        assert most <= 2, f"{name}: {artist} מופיע {most} פעמים"


def test_cap_by_artist_keeps_the_first_entries_in_order():
    sample = ({"artist": "A", "track": "1", "year": 1970},
              {"artist": "B", "track": "2", "year": 1971},
              {"artist": "a", "track": "3", "year": 1972},
              {"artist": "A", "track": "4", "year": 1973})
    kept = classics.cap_by_artist(sample, limit=2)
    assert [e["track"] for e in kept] == ["1", "2", "3"]


def test_cap_by_artist_is_a_display_filter_not_a_deletion():
    """השיר נשאר בקוד — רק לא נדחס לאותה קטגוריה."""
    capped = {(e["artist"], e["track"]) for e in classics.CATEGORIES["🎸 רוק"]}
    everything = {(e["artist"], e["track"]) for e in classics.ROCK_CLASSICS}
    assert capped < everything


def test_no_song_appears_twice_inside_one_category():
    for name, entries in classics.CATEGORIES.items():
        keys = [(e["artist"].casefold(), e["track"].casefold()) for e in entries]
        assert len(keys) == len(set(keys)), f"כפילות בקטגוריה {name}"


def test_oldies_is_fifties_and_sixties_across_all_genres():
    years = [e["year"] for e in classics.CATEGORIES["📻 אולדיס"]]
    assert max(years) <= 1969
    # ומכל שלושת הז'אנרים, לא רק מאחד
    artists = {e["artist"] for e in classics.CATEGORIES["📻 אולדיס"]}
    assert artists & {e["artist"] for e in classics.BLUES_CLASSICS}
    assert artists & {e["artist"] for e in classics.POP_CLASSICS}


def test_in_years_is_inclusive_on_both_ends():
    sample = ({"artist": "a", "track": "t", "year": 1970},
              {"artist": "b", "track": "u", "year": 1979},
              {"artist": "c", "track": "v", "year": 1980})
    assert len(classics.in_years(sample, 1970, 1979)) == 2


# ---------- בריכת ההגרלה ----------

def test_the_famous_pool_is_a_reasonable_size():
    pool = classics.famous_pool()
    assert 400 <= len(pool) <= 900


def test_the_famous_pool_has_no_duplicates():
    keys = [(e["artist"].casefold(), e["track"].casefold()) for e in classics.famous_pool()]
    assert len(keys) == len(set(keys))


def test_famous_pool_entries_have_the_expected_shape():
    for entry in classics.famous_pool():
        assert entry["artist"].strip()
        assert entry["track"].strip()
        assert 1950 <= entry["year"] <= 2020


def test_the_famous_pool_takes_only_the_top_of_each_decade():
    """הרשימות ב-`chart_data` מדורגות לפי המצעד, ולכן "הראשונים" = המוכרים."""
    pool = {(e["artist"], e["track"]) for e in classics.famous_pool()}
    for decade in chart_data.DECADE_HITS.values():
        head = decade[:classics.FAMOUS_PER_DECADE]
        tail = decade[classics.FAMOUS_PER_DECADE:]
        assert all((e["artist"], e["track"]) in pool for e in head)
        # הזנב יכול להופיע רק אם הוא ממילא ברשימות האצורות
        curated = {(e["artist"], e["track"])
                   for e in classics.POP_CLASSICS + classics.ROCK_CLASSICS}
        assert all((e["artist"], e["track"]) not in pool
                   for e in tail if (e["artist"], e["track"]) not in curated)


def test_blues_is_not_a_source_for_the_pool():
    """הבקשה היא שיר שסביר שיש לו קאבר. שיר בלוז שגם היה להיט במצעד נשאר —
    מה שנפסל הוא הרשימה כמקור."""
    pool = {(e["artist"], e["track"]) for e in classics.famous_pool()}
    charted = {(e["artist"], e["track"])
               for decade in chart_data.DECADE_HITS.values() for e in decade}
    curated = {(e["artist"], e["track"])
               for e in classics.POP_CLASSICS + classics.ROCK_CLASSICS}
    blues_only = [(e["artist"], e["track"]) for e in classics.BLUES_CLASSICS
                  if (e["artist"], e["track"]) not in charted | curated]
    assert blues_only, "הבדיקה חסרת משמעות אם כל הבלוז ממילא מופיע במקומות אחרים"
    assert not [k for k in blues_only if k in pool]


def test_every_song_in_the_dice_pool_can_match_its_own_title():
    """כפתור ההגרלה מחפש לפי הכותרת שהוא הגריל. שיר שאינו עובר את רצפת
    הרלוונטיות מול עצמו מחזיר רשימה ריקה — וזה בדיוק מה שקרה ל-31 שירים
    עם סוגריים בשם אחרי שהרצפה עלתה ל-90."""
    import search

    unmatched = [entry for entry in classics.famous_pool()
                 if search.relevance({"artist": entry["artist"], "track": entry["track"]},
                                     entry["track"]) < search.RELEVANCE_FLOOR]
    assert not unmatched, [(e["artist"], e["track"]) for e in unmatched[:5]]
