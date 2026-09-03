import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

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


def test_the_decades_together_cover_everything():
    decades = [label for label in classics.CATEGORIES if label.endswith("'s")]
    covered = {(e["artist"], e["track"])
               for label in decades for e in classics.CATEGORIES[label]}
    assert covered == {(e["artist"], e["track"]) for e in classics.ALL_CLASSICS}


def test_derived_categories_are_subsets_of_their_source():
    assert set(map(id, classics.CATEGORIES["🎤 פופ קלאסי"])) <= set(map(id, classics.POP_CLASSICS))
    assert set(map(id, classics.CATEGORIES["🎸 רוק קלאסי"])) <= set(map(id, classics.ROCK_CLASSICS))


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
