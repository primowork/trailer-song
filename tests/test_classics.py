import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import classics


def test_lists_are_reasonably_sized():
    # ~200 כל אחת, לא בהכרח בדיוק — זו רשימה אצורה, לא ספירה מדויקת
    assert 150 <= len(classics.POP_CLASSICS) <= 250
    assert 150 <= len(classics.ROCK_CLASSICS) <= 250


def test_entries_have_the_expected_shape():
    for entry in (*classics.POP_CLASSICS, *classics.ROCK_CLASSICS):
        assert entry["artist"].strip()
        assert entry["track"].strip()
        assert 1950 <= entry["year"] <= 2020


def test_no_duplicate_song_within_a_list():
    for name, entries in (("pop", classics.POP_CLASSICS), ("rock", classics.ROCK_CLASSICS)):
        seen = set()
        for entry in entries:
            key = (entry["artist"].lower(), entry["track"].lower())
            assert key not in seen, f"duplicate in {name}: {key}"
            seen.add(key)


def test_spans_the_full_range_of_decades():
    for entries in (classics.POP_CLASSICS, classics.ROCK_CLASSICS):
        years = [e["year"] for e in entries]
        assert min(years) < 1960
        assert max(years) >= 2019
