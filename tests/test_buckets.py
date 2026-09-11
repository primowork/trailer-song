"""חלוקת התוצאות לקטגוריות.

הטסטים בונים מדידות מתוך הטווחים המתועדים ב-`audio.py` ולא ממספרי קסם,
כדי ששינוי בטווחים יגיע לכאן במקום להשאיר טסט ירוק על הנחה ישנה.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import audio  # noqa: E402
import buckets  # noqa: E402

RANGES = {name: (floor, full) for name, (_, floor, full) in audio.WEIGHTS.items()}
RANGES.update(audio.TIMBRE_RANGES)


def _features(**levels) -> dict:
    values = {name: floor + 0.45 * (full - floor)
              for name, (floor, full) in RANGES.items()}
    for name, level in levels.items():
        floor, full = RANGES[name]
        values[name] = floor + level * (full - floor)
    return values


def _track(title, genre="", album="", artist="Some Band"):
    return {"artist": artist, "track": title, "album": album, "genre": genre,
            "uid": f"itunes-{title}"}


def test_each_category_is_reachable():
    """קטגוריה שאי אפשר להגיע אליה היא כותרת שלא תופיע לעולם."""
    expected = {
        buckets.ACAPPELLA: (_track("Yellow (A Cappella)"), None),
        buckets.TRAILER: (_track("Yellow (Epic Trailer Version)"), None),
        buckets.INSTRUMENTAL: (_track("Yellow (Karaoke)"), None),
        buckets.CLASSICAL: (_track("Yellow for String Quartet"), None),
        buckets.ROCK: (_track("Yellow (Metal Cover)"), None),
        buckets.TRANCE: (_track("Yellow (Trance Remix)"), None),
        buckets.INTIMATE: (_track("Yellow"),
                           _features(loudness=0.05, low_end=0.05, onset_rate=0.05)),
        # איטי אבל לא שקט: זו בדיוק ההפרדה בין שתי הקטגוריות
        buckets.CALM: (_track("Yellow"),
                       _features(onset_rate=0.05, loudness=0.9, low_end=0.9,
                                 dynamic_span=0.9)),
        buckets.OTHER: (_track("Yellow"), None),
    }
    assert set(expected) == set(buckets.ORDER), "קטגוריה בלי בדיקה שמגיעים אליה"
    for name, (track, features) in expected.items():
        assert buckets.bucket_of(track, features) == name


def test_a_title_that_merely_contains_a_marker_is_not_a_match():
    """הבאג שנמדד: `\\brock` תופס את **Rocket Man**, כי "Rocket" מתחיל
    בגבול מילה. העיגון בסוף הוא מה שמפריד ביניהם."""
    assert buckets.bucket_of(_track("Rocket Man")) == buckets.OTHER
    assert buckets.bucket_of(_track("Heartstrings")) == buckets.OTHER
    assert buckets.bucket_of(_track("Yellow (Rock Cover)")) == buckets.ROCK


def test_the_genre_only_reaches_categories_that_have_one():
    """ז'אנר מגיע מ-iTunes בלבד; Deezer מחזיר מחרוזת ריקה."""
    assert buckets.bucket_of(_track("Yellow", genre="Hard Rock")) == buckets.ROCK
    assert buckets.bucket_of(_track("Yellow", genre="Classical")) == buckets.CLASSICAL
    assert buckets.bucket_of(_track("Yellow", genre="Dance")) == buckets.TRANCE
    # אותה גרסה בדיוק מ-Deezer, בלי ז'אנר, נופלת לשארית ולא נעלמת
    assert buckets.bucket_of(_track("Yellow", genre="")) == buckets.OTHER


def test_a_cover_lands_in_exactly_one_category():
    """גרסה שמופיעה בכמה מקומות גורמת לסכום להיות גדול ממספר התוצאות."""
    tracks = [_track("Yellow (Epic Metal Cover)"),
              _track("Yellow (Epic A Cappella)"),
              _track("Yellow (Instrumental)", genre="Rock")]
    grouped = buckets.group(tracks)
    assert sum(len(rows) for _, rows in grouped) == len(tracks)
    # עדיפות: אקפלה לפני טריילר, וטריילר לפני רוק ואינסטרומנטלי
    assert buckets.bucket_of(tracks[0]) == buckets.TRAILER
    assert buckets.bucket_of(tracks[1]) == buckets.ACAPPELLA
    assert buckets.bucket_of(tracks[2]) == buckets.INSTRUMENTAL


def test_a_quiet_cover_agrees_with_the_meter_beside_it():
    """התלונה עצמה: שורה שהמד שלה נמוך נקראת שקטה לכל מי שמסתכל, ובכל זאת
    נפלה ל"כל השאר". הקטגוריה נשענת עכשיו על אותו מספר שהמד מצייר."""
    quiet = _features(loudness=0.1, low_end=0.1, onset_rate=0.2, dynamic_span=0.2)
    assert audio.bigness(quiet) < audio.MID_VERSION_THRESHOLD
    assert buckets.bucket_of(_track("Yellow"), quiet) == buckets.INTIMATE


def test_a_slow_but_big_cover_is_calm_and_not_intimate():
    """"רגוע" הוא איטי, "עדין" הוא שקט — ולכן גרסה איטית וגדולה היא רגועה."""
    slow_and_big = _features(onset_rate=0.05, loudness=0.9, low_end=0.9,
                             dynamic_span=0.9)
    assert audio.bigness(slow_and_big) >= audio.MID_VERSION_THRESHOLD
    assert buckets.bucket_of(_track("Yellow"), slow_and_big) == buckets.CALM


def test_a_compressed_dnb_cover_does_not_read_as_calm():
    """הבאג שדווח: קאבר דראם אנד בייס אגרסיבי במיוחד נפל ל-Calm. המאסטרינג
    הדחוס שלו משטח את ה-RMS כמעט לקו ישר, ולכן `onset_rate` (שסופר קפיצות
    עוצמה) כמעט ולא נדלק — למרות שהטראק צפוף ומתקפי ככל שיהיה. `flux`
    (תוכן ספקטרלי משתנה, לא עוצמה) הוא מה שאמור לתפוס אותו במקום —
    ראו את ההערה המלאה ב-`tags._rules`."""
    fooled_onset = _features(onset_rate=0.10, dynamic_span=0.10,
                             loudness=0.70, flux=0.90)
    assert buckets.bucket_of(_track("Yellow"), fooled_onset) != buckets.CALM


def test_a_loud_fast_cover_is_neither_calm_nor_intimate():
    loud = _features(onset_rate=0.9, loudness=0.9)
    assert buckets.bucket_of(_track("Yellow"), loud) == buckets.OTHER


def test_grouping_keeps_the_order_it_was_given_and_drops_empty_categories():
    """החלוקה לא ממיינת מחדש: המיון כבר הוחל ב-`ordered_display`."""
    tracks = [_track("A (Rock Cover)"), _track("B (Rock Cover)"),
              _track("C (A Cappella)")]
    grouped = buckets.group(tracks)
    names = [name for name, _ in grouped]
    assert names == [buckets.ACAPPELLA, buckets.ROCK], "קטגוריה ריקה הוצגה"
    assert [t["track"] for t in dict(grouped)[buckets.ROCK]] == ["A (Rock Cover)",
                                                                "B (Rock Cover)"]


def test_an_unmeasured_cover_does_not_guess_at_calm_or_intimate():
    assert buckets.bucket_of(_track("Yellow"), None) == buckets.OTHER
    assert buckets.bucket_of(_track("Yellow"), {}) == buckets.OTHER
    assert buckets.bucket_of(_track("Yellow"), {"error": "cors"}) == buckets.OTHER


# ---------- תיקוני משתמשים ל"Wrong category?" ----------

def _row(artist, title, album="", genre=""):
    return {"artist": artist, "track": title, "album": album, "genre": genre}


SOUNDTRACK = _row("Ronnie Minder", "Lollipop",
                    album="Kane (Original Motion Picture Soundtrack)")


def _correction(track, category):
    track_key, album_key, artist_key = buckets.correction_keys(track)
    return {"track_key": track_key, "album_key": album_key,
            "artist_key": artist_key, "category": category}


def test_the_rules_alone_call_a_soundtrack_a_trailer():
    """הכשל שהתיקון קיים בשבילו: שיר פופ רגיל בפסקול נקרא 'טריילר' רק
    בגלל שם האלבום."""
    assert buckets.bucket_of(SOUNDTRACK) == buckets.TRAILER


def test_a_correction_beats_the_rules():
    index = buckets.correction_index([_correction(SOUNDTRACK, buckets.OTHER)])
    assert buckets.bucket_of(SOUNDTRACK, None, index) == buckets.OTHER


def test_a_correction_follows_the_track_into_another_search():
    """זו הלמידה שנתבקשה: הדיווח נעשה פעם אחת וחל על כל חיפוש אחר כך.

    אותה גרסה חוזרת עם uid אחר ומחנות אחרת, ולכן ההתאמה היא לפי זהות
    תוכן (`search.track_key`) ולא לפי מזהה החנות.
    """
    index = buckets.correction_index([_correction(SOUNDTRACK, buckets.OTHER)])
    same_song_other_store = _row("ronnie minder", "Lollipop  ",
                                   album="Something Else")
    assert buckets.bucket_of(same_song_other_store, None, index) == buckets.OTHER


def test_one_correction_does_not_move_the_whole_album():
    """הכללה מטראק בודד לאלבום שלם על סמך קליק אחד היא ניחוש."""
    index = buckets.correction_index([_correction(SOUNDTRACK, buckets.OTHER)])
    sibling = _row("Ronnie Minder", "Another Cue",
                     album="Kane (Original Motion Picture Soundtrack)")
    assert buckets.bucket_of(sibling, None, index) == buckets.TRAILER


def test_enough_matching_corrections_move_the_album():
    records = [
        _correction(SOUNDTRACK, buckets.OTHER),
        _correction(_row("Ronnie Minder", "Another Cue",
                           album="Kane (Original Motion Picture Soundtrack)"),
                    buckets.OTHER),
    ]
    index = buckets.correction_index(records)
    third = _row("Ronnie Minder", "A Third Cue",
                   album="Kane (Original Motion Picture Soundtrack)")
    assert buckets.bucket_of(third, None, index) == buckets.OTHER


def test_two_users_who_disagree_teach_nothing():
    """עדות מעורבת פירושה 'לא יודעים', והנפילה לאחור היא החוקים —
    שהם לפחות עקביים. רוב על שניים הוא משתמש אחד שטעה."""
    records = [
        _correction(SOUNDTRACK, buckets.OTHER),
        _correction(_row("Ronnie Minder", "Another Cue",
                           album="Kane (Original Motion Picture Soundtrack)"),
                    buckets.ROCK),
    ]
    index = buckets.correction_index(records)
    third = _row("Ronnie Minder", "A Third Cue",
                   album="Kane (Original Motion Picture Soundtrack)")
    assert buckets.bucket_of(third, None, index) == buckets.TRAILER
    # ומה שתוקן במפורש עדיין מתוקן
    assert buckets.bucket_of(SOUNDTRACK, None, index) == buckets.OTHER


def test_an_artist_needs_a_higher_bar_than_an_album():
    """אלבום הוא הפקה אחת; אמן הוא גוף עבודה שלם."""
    albums = ["First Score", "Second Score", "Third Score"]
    records = [_correction(_row("Ronnie Minder", f"Cue {i}", album=album,
                                  genre="Rock"), buckets.CLASSICAL)
               for i, album in enumerate(albums)]
    assert len(records) == buckets.ARTIST_AGREEMENT

    fewer = buckets.correction_index(records[:-1])
    elsewhere = _row("Ronnie Minder", "Unrelated", album="Fourth Score",
                       genre="Rock")
    assert buckets.bucket_of(elsewhere, None, fewer) == buckets.ROCK

    enough = buckets.correction_index(records)
    assert buckets.bucket_of(elsewhere, None, enough) == buckets.CLASSICAL


def test_the_same_album_name_under_another_artist_is_untouched():
    """"Greatest Hits" הוא שם של מאות אלבומים שונים."""
    records = [_correction(_row("Ronnie Minder", f"Cue {i}",
                                  album="Greatest Hits", genre="Rock"),
                           buckets.CLASSICAL) for i in range(2)]
    index = buckets.correction_index(records)
    other_artist = _row("Somebody Else", "Cue 9", album="Greatest Hits",
                          genre="Rock")
    assert buckets.bucket_of(other_artist, None, index) == buckets.ROCK


def test_a_category_that_is_not_in_the_list_is_ignored():
    """הרשומות מגיעות מאחסון משותף ואינן נתון מהימן."""
    index = buckets.correction_index([_correction(SOUNDTRACK, "Klezmer")])
    assert buckets.bucket_of(SOUNDTRACK, None, index) == buckets.TRAILER


def test_counts_and_group_see_the_correction_too():
    """בלי זה השורה זזה בתפריט אבל לא בכפתורי הסינון שמעל התוצאות."""
    tracks = [{**SOUNDTRACK, "uid": "a"}]
    index = buckets.correction_index([_correction(SOUNDTRACK, buckets.OTHER)])
    assert buckets.counts(tracks, {}, index) == {buckets.OTHER: 1}
    assert [name for name, _ in buckets.group(tracks, {}, index)] == [buckets.OTHER]
