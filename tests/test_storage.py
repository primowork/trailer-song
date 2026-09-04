import importlib
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _fresh_storage(tmp_path, monkeypatch):
    monkeypatch.setenv("TRAILER_SONG_DATA_DIR", str(tmp_path))
    import storage
    return importlib.reload(storage)


def test_data_dir_uses_env_var(tmp_path, monkeypatch):
    storage = _fresh_storage(tmp_path, monkeypatch)
    assert storage.DATA_DIR == str(tmp_path)


def test_blacklist_roundtrip(tmp_path, monkeypatch):
    storage = _fresh_storage(tmp_path, monkeypatch)
    assert storage.load_blacklist() == set()
    assert storage.save_blacklist({"2wei", "hidden citizens"})
    assert storage.load_blacklist() == {"2wei", "hidden citizens"}


def test_favorites_roundtrip(tmp_path, monkeypatch):
    storage = _fresh_storage(tmp_path, monkeypatch)
    assert storage.load_favorites() == {}
    saved = {"2wei|zombie": {"artist": "2WEI", "track": "Zombie", "added_at": 1.0}}
    assert storage.save_favorites(saved)
    assert storage.load_favorites() == saved


def test_corrupt_favorites_file_returns_empty(tmp_path, monkeypatch):
    storage = _fresh_storage(tmp_path, monkeypatch)
    (tmp_path / "favorites.json").write_text("{ not json")
    assert storage.load_favorites() == {}
    assert storage.warnings


def test_corrupt_file_returns_default_without_raising(tmp_path, monkeypatch):
    storage = _fresh_storage(tmp_path, monkeypatch)
    (tmp_path / "blacklist.json").write_text("{ not json")
    assert storage.load_blacklist() == set()
    assert storage.warnings


def test_unwritable_dir_does_not_raise(tmp_path, monkeypatch):
    """הבאג שהפיל את האפליקציה: כתיבה ל-/data ללא הרשאה."""
    storage = _fresh_storage(tmp_path, monkeypatch)
    storage.DATA_DIR = "/proc/definitely-not-writable"
    assert storage.save_blacklist({"x"}) is False  # מחזיר False, לא זורק


def test_cache_key_is_case_insensitive(tmp_path, monkeypatch):
    storage = _fresh_storage(tmp_path, monkeypatch)
    assert storage.cache_key(" 2WEI ", "Survivor") == storage.cache_key("2wei", "survivor")


def test_a_valid_file_of_the_wrong_shape_falls_back(tmp_path, monkeypatch):
    """JSON פגום כבר טופל; מה שלא טופל היה קובץ *תקין* עם מבנה אחר — רשימה
    במקום מילון — שעבר את json.load ונפל רק בתוך הרינדור, בכל טעינה."""
    storage = _fresh_storage(tmp_path, monkeypatch)
    (tmp_path / "favorites.json").write_text('["not", "a", "dict"]')
    (tmp_path / "rejections.json").write_text('"a string"')
    (tmp_path / "blacklist.json").write_text('{"a": 1}')

    assert storage.load_favorites() == {}
    assert storage.load_rejections() == {}
    assert storage.load_blacklist() == set()
    assert storage.warnings
