"""הטסטים שקובעים אם הלמידה באמת לומדת.

לא "האם הפונקציה רצה" אלא "האם היא מסיקה את הדבר הנכון": האם היא מזהה
באיזה מימד המשתמש עקבי, האם היא מבדילה בין תכונה נדירה שנאהבה לתכונה
שנפוצה ממילא, והאם לייק בודד אינו מספיק כדי לנעול את הדירוג.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import taste


def features(loudness=0.19, low_end=1.9, onset_rate=2.1, dynamic_span=3.7):
    return {"loudness": loudness, "low_end": low_end,
            "onset_rate": onset_rate, "dynamic_span": dynamic_span}


def song(artist="2WEI", track="Zombie (Epic Trailer Version)", genre="Soundtrack",
         **extra):
    return {"artist": artist, "track": track, "genre": genre,
            "album": "", "year": "2018", **extra}


def liked(track_fields=None, feature_fields=None):
    return {**song(**(track_fields or {})), "features": features(**(feature_fields or {}))}


# ---------- גילוי המימד שחשוב למשתמש ----------

def test_a_dimension_the_user_is_consistent_about_gets_more_weight():
    """בס זהה בכל הלייקים, קצב מפוזר — הבס הוא שמגדיר את הטעם."""
    favorites = [
        liked(feature_fields={"low_end": 2.6, "onset_rate": 0.9}),
        liked(feature_fields={"low_end": 2.6, "onset_rate": 2.2}),
        liked(feature_fields={"low_end": 2.6, "onset_rate": 3.4}),
        liked(feature_fields={"low_end": 2.6, "onset_rate": 1.5}),
    ]
    learned = taste.profile(favorites)
    assert learned["dimension_weights"]["low_end"] > learned["dimension_weights"]["onset_rate"]


def test_the_learned_centre_sits_where_the_likes_are():
    favorites = [liked(feature_fields={"low_end": 2.9}) for _ in range(4)]
    learned = taste.profile(favorites)
    # 2.9 בטווח 0.8..3.0 הוא כמעט הקצה העליון
    assert learned["mean"]["low_end"] > 0.9


def test_a_track_that_sounds_like_the_likes_beats_one_that_does_not():
    favorites = [liked(feature_fields={"low_end": 2.8, "loudness": 0.28})
                 for _ in range(6)]
    learned = taste.profile(favorites)

    similar = taste.match(song(), features(low_end=2.8, loudness=0.28), learned)
    different = taste.match(song(), features(low_end=0.9, loudness=0.09), learned)
    assert similar > different


# ---------- ניגוד מול הרקע ----------

def test_a_genre_that_is_common_in_the_background_teaches_nothing():
    """אם כל התוצאות ממילא Soundtrack, לייק על Soundtrack אינו אות."""
    favorites = [liked({"genre": "Soundtrack"}) for _ in range(5)]
    background = [song(genre="Soundtrack") for _ in range(20)]
    learned = taste.profile(favorites, background)
    assert learned["lift"]["genre:soundtrack"] < 0.2


def test_a_rare_genre_that_is_liked_is_a_strong_signal():
    favorites = [liked({"genre": "Metal"}) for _ in range(5)]
    background = [song(genre="Soundtrack") for _ in range(19)] + [song(genre="Metal")]
    learned = taste.profile(favorites, background)
    assert learned["lift"]["genre:metal"] > 0.5
    # והוא גם מדורג מעל הז'אנר הנפוץ
    assert learned["lift"]["genre:metal"] > learned["lift"].get("genre:soundtrack", 0)


def test_a_rare_liked_genre_lifts_matching_tracks_above_others():
    favorites = [liked({"genre": "Metal", "artist": f"Band {i}"}) for i in range(6)]
    background = [song(genre="Soundtrack", artist=f"Other {i}") for i in range(20)]
    learned = taste.profile(favorites, background)

    metal = taste.match(song(genre="Metal", artist="New Band"), None, learned)
    soundtrack = taste.match(song(genre="Soundtrack", artist="New Band"), None, learned)
    assert metal > soundtrack


# ---------- בטיחות מדגם קטן ----------

def test_one_like_barely_moves_the_ranking():
    single = taste.profile([liked()])
    many = taste.profile([liked() for _ in range(20)])
    assert single["confidence"] < 0.25
    assert many["confidence"] > 0.75

    track, measured = song(), features()
    assert taste.match(track, measured, single) < taste.match(track, measured, many)


def test_no_favorites_means_no_influence_at_all():
    learned = taste.profile([])
    assert learned["count"] == 0
    assert taste.match(song(), features(), learned) == 0.0
    assert taste.bonus(song(), features(), learned) == 0


def test_the_bonus_is_capped():
    favorites = [liked() for _ in range(50)]
    learned = taste.profile(favorites)
    assert taste.bonus(song(), features(), learned) <= taste.MAX_TASTE_BONUS


# ---------- טראק שטרם נמדד ----------

def test_an_unmeasured_track_is_not_buried_under_measured_ones():
    """'לא נמדד' אינו 'לא מתאים' — אחרת כל מה שהמדידה טרם הגיעה אליו נעלם."""
    favorites = [liked(feature_fields={"low_end": 2.8}) for _ in range(6)]
    learned = taste.profile(favorites)

    unmeasured = taste.match(song(), None, learned)
    badly_matching = taste.match(song(), features(low_end=0.85, loudness=0.08,
                                                  onset_rate=0.8, dynamic_span=1.5),
                                 learned)
    assert unmeasured > badly_matching


def test_favorites_without_measurements_still_learn_categoricals():
    favorites = [{**song(genre="Metal"), "features": None} for _ in range(5)]
    background = [song(genre="Soundtrack") for _ in range(20)]
    learned = taste.profile(favorites, background)
    assert learned["lift"]["genre:metal"] > 0.5
    assert taste.match(song(genre="Metal"), None, learned) > 0


# ---------- ותק ----------

def test_a_recent_like_outweighs_an_old_one():
    now = 1_000_000_000.0
    old = 86400 * taste.RECENCY_HALFLIFE_DAYS * 4
    favorites = [
        {**liked({"genre": "Metal"}), "added_at": now - old},
        {**liked({"genre": "Choir"}), "added_at": now},
    ]
    learned = taste.profile(favorites, now=now)
    assert learned["lift"]["genre:choir"] > learned["lift"]["genre:metal"]


# ---------- הסבר קריא ----------

def test_describe_names_the_dimension_the_user_is_consistent_about():
    favorites = [liked(feature_fields={"low_end": 2.9, "onset_rate": 0.9 + i * 0.8})
                 for i in range(4)]
    text = taste.describe(taste.profile(favorites))
    assert "בס חזק" in text
    assert "4" in text


def test_describe_without_favorites_is_empty():
    assert taste.describe(taste.profile([])) == ""


# ---------- 👎 דוגמאות שליליות ----------

def test_a_dimension_that_separates_likes_from_rejects_outweighs_a_consistent_one():
    """הלב של הלמידה מדחיות.

    המשתמש עקבי לחלוטין בעוצמה — אבל גם הדחויים עקביים באותה עוצמה, ולכן
    היא לא מלמדת כלום. הבס הוא היחיד שמפריד, גם אם הוא פחות עקבי.
    """
    favorites = [liked(feature_fields={"loudness": 0.19, "low_end": 2.4 + i * 0.2})
                 for i in range(4)]
    rejections = [liked(feature_fields={"loudness": 0.19, "low_end": 0.9 + i * 0.2})
                  for i in range(4)]
    learned = taste.profile(favorites, rejections=rejections)
    assert learned["dimension_weights"]["low_end"] > learned["dimension_weights"]["loudness"]


def test_a_track_near_the_rejected_centre_is_pushed_down():
    favorites = [liked(feature_fields={"low_end": 2.8}) for _ in range(5)]
    rejections = [liked(feature_fields={"low_end": 0.9}) for _ in range(5)]
    sounds_rejected = features(low_end=0.9)
    # אמן שאינו מוכר לפרופיל, אחרת בונוס האמן השמור מערפל את מה שנבדק כאן:
    # ההפרדה לפי *צליל*
    probe = song(artist="Unknown Artist")

    without = taste.profile(favorites)
    with_rejections = taste.profile(favorites, rejections=rejections)

    # הדחיות מגדילות את הביטחון (יותר דוגמאות), ולכן ההשוואה היא על ההפרדה
    # ולא על הערך המוחלט: כמה הדחוי נמוך ביחס לאהוב
    def separation(learned):
        return (taste.match(probe, sounds_rejected, learned)
                / taste.match(probe, features(low_end=2.8), learned))

    assert separation(with_rejections) < separation(without)
    assert separation(with_rejections) < 0.5


def test_a_rejected_genre_gets_negative_lift():
    favorites = [liked({"genre": "Metal"}) for _ in range(4)]
    rejections = [liked({"genre": "Classical"}) for _ in range(4)]
    learned = taste.profile(favorites, rejections=rejections)
    assert learned["lift"]["genre:classical"] < 0
    assert learned["lift"]["genre:metal"] > 0


def test_rejections_sharpen_a_signal_the_background_alone_would_miss():
    """שני הז'אנרים נפוצים ברקע במידה שווה — רק הדחיות מפרידות ביניהם."""
    favorites = [liked({"genre": "Choir"}) for _ in range(4)]
    rejections = [liked({"genre": "Piano"}) for _ in range(4)]
    background = ([song(genre="Choir") for _ in range(10)]
                  + [song(genre="Piano") for _ in range(10)])

    without = taste.profile(favorites, background)
    with_rejections = taste.profile(favorites, background, rejections=rejections)
    assert with_rejections["lift"]["genre:choir"] > without["lift"]["genre:choir"]


def test_rejections_alone_still_count_toward_confidence():
    only_likes = taste.profile([liked() for _ in range(3)])
    with_rejections = taste.profile([liked() for _ in range(3)],
                                    rejections=[liked() for _ in range(5)])
    assert with_rejections["confidence"] > only_likes["confidence"]


def test_describe_names_what_is_avoided():
    favorites = [liked({"genre": "Metal"}) for _ in range(4)]
    rejections = [liked({"genre": "Classical"}) for _ in range(4)]
    text = taste.describe(taste.profile(favorites, rejections=rejections))
    assert "דחיות" in text
    assert "נמנע מ" in text and "Classical" in text


# ---------- מדדי גוון ----------

def timbral(centroid=0.10, flatness=0.05, air=0.03, presence=0.12, flux=0.20, **energy):
    return {**features(**energy), "centroid": centroid, "flatness": flatness,
            "air": air, "presence": presence, "flux": flux}


def test_timbre_separates_tracks_that_energy_alone_cannot():
    """הבדיקה שקובעת מול הביקורת: אותה עוצמה בדיוק, גוון הפוך.

    ארבעת מדדי העוצמה זהים לחלוטין בשלושת הטראקים — braam אפל, מקהלה בהירה.
    בלי מדדי הגוון המודל היה נותן לשניהם בדיוק אותו ציון.
    """
    dark = {"centroid": 0.04, "flatness": 0.02, "air": 0.005, "presence": 0.04, "flux": 0.08}
    bright = {"centroid": 0.16, "flatness": 0.03, "air": 0.08, "presence": 0.26, "flux": 0.10}

    favorites = [{**song(), "features": {**features(), **dark}} for _ in range(6)]
    learned = taste.profile(favorites)

    like_dark = taste.match(song(), {**features(), **dark}, learned)
    like_bright = taste.match(song(), {**features(), **bright}, learned)
    assert like_dark > like_bright

    # ולראיה שזה הגוון ולא העוצמה: המדדים האנרגטיים זהים בשניהם
    assert {k: v for k, v in features().items()} == {
        k: v for k, v in {**features(), **bright}.items() if k in features()}


def test_a_timbre_dimension_can_dominate_the_profile():
    """אם המשתמש עקבי בבהירות ומפוזר בכל השאר, הבהירות היא הטעם."""
    favorites = [
        {**song(), "features": timbral(centroid=0.15, flux=0.10 + i * 0.08,
                                       loudness=0.12 + i * 0.04)}
        for i in range(4)
    ]
    learned = taste.profile(favorites)
    assert learned["dimension_weights"]["centroid"] > learned["dimension_weights"]["flux"]
    assert learned["dimension_weights"]["centroid"] > learned["dimension_weights"]["loudness"]


def test_old_measurements_without_timbre_still_work():
    """מדידות שנשמרו לפני שהגוון נוסף אינן נזרקות — הן פשוט מתארות פחות."""
    favorites = [liked(feature_fields={"low_end": 2.8}) for _ in range(5)]
    learned = taste.profile(favorites)
    assert set(learned["mean"]) == set(taste.audio.WEIGHTS)

    # וטראק חדש *עם* גוון עדיין נמדד מולם, על החיתוך
    score = taste.match(song(), timbral(low_end=2.8), learned)
    assert 0 < score <= 1


def test_a_new_measurement_is_compared_fairly_against_an_old_profile():
    """טראק שנמדד בפחות מימדים לא מקבל יתרון מלאכותי מסכום קצר יותר."""
    favorites = [{**song(), "features": timbral(centroid=0.15)} for _ in range(6)]
    learned = taste.profile(favorites)

    matching_full = taste.match(song(), timbral(centroid=0.15), learned)
    matching_old = taste.match(song(), features(), learned)   # בלי מדדי גוון
    # הישן מושווה רק על מה שיש לו, ולכן אינו מנצח את המלא שתואם לחלוטין
    assert matching_full >= matching_old


def test_describe_can_name_a_timbre_trait():
    favorites = [{**song(), "features": timbral(centroid=0.17,
                                                loudness=0.10 + i * 0.05,
                                                low_end=1.0 + i * 0.6)}
                 for i in range(4)]
    text = taste.describe(taste.profile(favorites))
    assert "בהיר" in text


# ---------- אמן שכבר שמור בפלייליסט ----------

def test_a_saved_artist_lifts_their_other_songs_too():
    """הבקשה המפורשת: אמן ששמור מקבל עדיפות גם על קאבר לשיר אחר לגמרי."""
    favorites = [liked({"artist": "Violet Orlandi", "track": "Zombie"}),
                 liked({"artist": "Violet Orlandi", "track": "Creep"}),
                 liked({"artist": "Violet Orlandi", "track": "Toxicity"})]
    learned = taste.profile(favorites)

    # שיר אחר לגמרי, אותו אמן
    known = taste.match(song(artist="Violet Orlandi", track="Something Else"),
                        features(), learned)
    stranger = taste.match(song(artist="Nobody At All", track="Something Else"),
                           features(), learned)
    assert known > stranger


def test_the_artist_boost_survives_a_track_that_otherwise_matches_poorly():
    """דווקא כאן הוא נדרש: הצליל לא מתאים, אבל האמן שמור."""
    favorites = [liked({"artist": "Violet Orlandi", "track": f"Song {i}"},
                       {"low_end": 2.8}) for i in range(4)]
    learned = taste.profile(favorites)
    off_style = features(low_end=0.85, loudness=0.08, onset_rate=0.8, dynamic_span=1.6)

    known = taste.match(song(artist="Violet Orlandi", genre="Pop"), off_style, learned)
    stranger = taste.match(song(artist="Nobody At All", genre="Pop"), off_style, learned)
    assert known > stranger * 1.15


def test_the_artist_boost_cannot_push_past_one():
    favorites = [liked() for _ in range(40)]
    learned = taste.profile(favorites)
    assert taste.match(song(), features(), learned) <= 1.0
    assert taste.bonus(song(), features(), learned) <= taste.MAX_TASTE_BONUS


def test_a_corrupt_timestamp_does_not_break_the_profile():
    """`added_at` מגיע מ-favorites.json שעל הדיסק, והפרופיל נבנה בכל rerun —
    ערך אחד שאינו מספר היה מפיל את האפליקציה בכל טעינה, בלי דרך לתקן
    מתוך הממשק."""
    entries = [{"artist": "2WEI", "track": "Zombie", "features": None,
                "added_at": "לא מספר"},
               {"artist": "Hidden Citizens", "track": "Alive", "features": None,
                "added_at": None}]
    learned = taste.profile(entries)
    assert learned["count"] == 2
    assert isinstance(taste.describe(learned), str)
