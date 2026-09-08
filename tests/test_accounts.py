"""זהות, הפרדה בין משתמשים, ומכסה.

הכל רץ על בקאנד הקבצים ובלי `[auth]` — כלומר בדיוק בתנאים של הפיתוח
המקומי. זו הנקודה: ההפרדה חייבת להיות נכונה גם בלי מסד נתונים.
"""
import datetime as _dt

import pytest
import importlib
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import accounts  # noqa: E402


def _fresh_storage(tmp_path, monkeypatch):
    monkeypatch.setenv("TRAILER_SONG_DATA_DIR", str(tmp_path))
    monkeypatch.delenv("DATABASE_URL", raising=False)
    import storage
    return importlib.reload(storage)


ALICE = accounts.Subject("user", "user:alice@example.com", "alice@example.com")
BOB = accounts.Subject("user", "user:bob@example.com", "bob@example.com")
GUEST = accounts.Subject("anon", "anon:deadbeef")


def test_two_users_do_not_see_each_others_playlist(tmp_path, monkeypatch):
    storage = _fresh_storage(tmp_path, monkeypatch)
    storage.save_favorites({"2wei|zombie": {"artist": "2WEI"}}, ALICE)
    assert storage.load_favorites(BOB) == {}
    assert "2wei|zombie" in storage.load_favorites(ALICE)


def test_rejections_and_blacklist_are_personal_too(tmp_path, monkeypatch):
    storage = _fresh_storage(tmp_path, monkeypatch)
    storage.save_rejections({"x|y": {"artist": "X"}}, ALICE)
    storage.save_blacklist({"hidden citizens"}, ALICE)
    assert storage.load_rejections(BOB) == {}
    assert storage.load_blacklist(BOB) == set()
    assert storage.load_blacklist(ALICE) == {"hidden citizens"}


def test_measurements_are_shared_between_users(tmp_path, monkeypatch):
    """המדידה היא תכונה של הטראק, לא של מי ששמע אותו. אילו הייתה אישית,
    כל משתמש היה מודד מחדש בדפדפן שלו בדיוק את אותם טראקים."""
    storage = _fresh_storage(tmp_path, monkeypatch)
    storage.save_bigness({"2wei|zombie": {"score": 82}})
    assert storage.load_bigness()["2wei|zombie"]["score"] == 82


def test_an_anonymous_subject_uses_the_shared_space(tmp_path, monkeypatch):
    """אנונימי אינו מקבל מרחב משלו: הוא ממילא לא יכול לשמור כשהתחברות
    מוגדרת, ומרחב לכל ביקור היה מייצר תיקיות זבל."""
    storage = _fresh_storage(tmp_path, monkeypatch)
    storage.save_favorites({"a|b": {}})
    assert storage.load_favorites(GUEST) == {"a|b": {}}


def test_the_bucket_drains_refills_and_stops_at_the_ceiling():
    now = _dt.datetime(2026, 1, 10, tzinfo=_dt.timezone.utc)
    assert accounts.refill(4.0, now - _dt.timedelta(days=3), now) == 7.0
    assert accounts.refill(9.0, now - _dt.timedelta(days=365), now) == accounts.QUOTA_CAPACITY
    assert accounts.refill(0.0, now, now) == 0.0
    # שעון שקפץ אחורה לא מזכה אף אחד
    assert accounts.refill(2.0, now + _dt.timedelta(days=5), now) == 2.0


def test_spending_stops_at_zero_and_does_not_reset_the_clock(tmp_path, monkeypatch):
    storage = _fresh_storage(tmp_path, monkeypatch)
    for _ in range(int(accounts.QUOTA_CAPACITY)):
        assert accounts.spend(GUEST) is True
    assert accounts.spend(GUEST) is False

    # הדחייה לא כתבה: `updated_at` נשאר של ההוצאה האחרונה, ולכן המילוי
    # ממשיך להיצבר גם כשממשיכים ללחוץ
    tokens, when = storage.load_quota(GUEST.key)
    assert tokens == pytest.approx(0.0, abs=1e-4)
    accounts.spend(GUEST)
    assert storage.load_quota(GUEST.key)[1] == when


def test_logging_in_does_not_hand_out_a_fresh_allowance(tmp_path, monkeypatch):
    """אחרת "התחבר" היה הדרך המהירה ביותר לאפס את המכסה."""
    storage = _fresh_storage(tmp_path, monkeypatch)
    now = _dt.datetime.now(_dt.timezone.utc)
    storage.save_quota(GUEST.key, 1.0, now)
    accounts.absorb_anonymous(ALICE, GUEST.key)
    assert accounts.remaining(ALICE) == pytest.approx(1.0, abs=1e-3)


def test_a_subject_without_auth_configured_is_anonymous_and_does_not_raise():
    """בלי `[auth]`, `st.user.is_logged_in` זורק AttributeError — וזה מה
    שהיה שובר כל הרצה מקומית וכל טסט בלי ה-try/except."""
    assert accounts.login_available() is False
    subject = accounts.current_subject()
    assert subject.kind == "anon"
    assert subject.key.startswith("anon:")
    assert subject.is_logged_in is False
