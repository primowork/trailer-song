"""בדיקות לגנרטור המצעדים — על נתונים סינתטיים בלבד, בלי רשת ובלי הקובץ האמיתי."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                "tools"))

import build_charts


def chart(date: str, rows: list) -> dict:
    """rows = [(artist, song, position)] — peak/weeks לא בשימוש בצבירה."""
    return {"date": date,
            "data": [{"artist": a, "song": s, "this_week": p, "peak_position": p,
                      "weeks_on_chart": 1} for a, s, p in rows]}


def weeks(year: int, count: int, artist: str, song: str, position: int) -> list:
    return [chart(f"{year}-{month:02d}-07", [(artist, song, position)])
            for month in range(1, count + 1)]


# ---------- חלון הכניסה ----------

def test_a_viral_revival_decades_later_does_not_inflate_the_score():
    charts = weeks(1985, 6, "Kate Bush", "Running Up That Hill", 30)
    revived = charts + weeks(2022, 12, "Kate Bush", "Running Up That Hill", 3)

    original = build_charts.aggregate(charts)[("Kate Bush", "Running Up That Hill")]
    with_revival = build_charts.aggregate(revived)[("Kate Bush", "Running Up That Hill")]
    assert with_revival["weeks"] == original["weeks"]
    assert with_revival["year"] == 1985


def test_the_window_still_counts_the_songs_own_chart_run():
    charts = weeks(1977, 12, "Bee Gees", "Stayin' Alive", 1)
    charts += weeks(1978, 6, "Bee Gees", "Stayin' Alive", 20)
    entry = build_charts.aggregate(charts)[("Bee Gees", "Stayin' Alive")]
    assert entry["weeks"] == 18
    assert entry["number_one"] == 12


# ---------- מסנן עונתי ----------

def test_a_christmas_song_is_filtered_out():
    charts = weeks(1994, 12, "Mariah Carey", "All I Want For Christmas Is You", 1)
    charts += weeks(1994, 3, "Real Song", "Ordinary Hit", 40)
    picked = build_charts.pick(build_charts.aggregate(charts), 1990, 1999)
    assert [e["track"] for e in picked] == ["Ordinary Hit"]


# ---------- דירוג ----------

def test_a_number_one_outranks_a_longer_running_also_ran():
    charts = weeks(1977, 8, "Bee Gees", "Stayin' Alive", 1)
    charts += weeks(1977, 12, "Paul Davis", "I Go Crazy", 40)
    picked = build_charts.pick(build_charts.aggregate(charts), 1970, 1979)
    assert picked[0]["track"] == "Stayin' Alive"


def test_only_songs_that_debuted_in_the_decade_are_picked():
    charts = weeks(1969, 6, "Old", "Before", 1) + weeks(1971, 6, "New", "Inside", 5)
    picked = build_charts.pick(build_charts.aggregate(charts), 1970, 1979)
    assert [e["track"] for e in picked] == ["Inside"]


# ---------- תקרת האמן ----------

def test_an_artist_gets_at_most_two_songs_per_decade():
    charts = []
    for index in range(5):
        charts += weeks(1970, 10 - index, "Prolific", f"Hit {index}", 1)
    picked = build_charts.pick(build_charts.aggregate(charts), 1970, 1979)
    assert len(picked) == 2
    assert [e["track"] for e in picked] == ["Hit 0", "Hit 1"]


def test_the_cap_counts_featured_collaborations_under_the_lead_artist():
    charts = weeks(2004, 10, "Usher", "Yeah!", 1)
    charts += weeks(2004, 9, "Usher Featuring Lil Jon", "Burn", 1)
    charts += weeks(2004, 8, "Usher Featuring Alicia Keys", "My Boo", 1)
    picked = build_charts.pick(build_charts.aggregate(charts), 2000, 2009)
    assert len(picked) == 2


def test_the_featured_artist_is_trimmed_from_the_stored_name():
    """"Usher Featuring Lil Jon & Ludacris" הוא שאילתת קאברים גרועה."""
    assert build_charts.clean_artist("Usher Featuring Lil Jon & Ludacris") == "Usher"
    assert build_charts.clean_artist("Santana Feat. Rob Thomas") == "Santana"
    assert build_charts.clean_artist("Patti Austin A Duet With James Ingram") == "Patti Austin"


def test_a_band_name_survives_untouched():
    """אין דרך אמינה להבדיל בין הרכב לשיתוף פעולה, ולכן "&"/"and" לא נחתכים."""
    assert build_charts.clean_artist("Simon & Garfunkel") == "Simon & Garfunkel"
    assert build_charts.clean_artist("Kool & The Gang") == "Kool & The Gang"
    assert build_charts.clean_artist("Derek And The Dominos") == "Derek And The Dominos"


# ---------- הפלט ----------

def test_the_rendered_module_is_importable_python():
    rendered = build_charts.render([("70's", [{"artist": 'The "Who"', "track": "Won't Get Fooled",
                                               "year": 1971}])])
    namespace: dict = {}
    exec(compile(rendered, "chart_data.py", "exec"), namespace)
    assert namespace["DECADE_HITS"]["70's"][0]["artist"] == 'The "Who"'
