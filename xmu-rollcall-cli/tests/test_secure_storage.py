import importlib
import json
import requests


def reload_storage(monkeypatch, tmp_path):
    monkeypatch.setenv("XMU_ROLLCALL_CONFIG_DIR", str(tmp_path))
    import xmu_rollcall.secure_store as secure_store
    import xmu_rollcall.config as config
    import xmu_rollcall.utils as utils

    importlib.reload(secure_store)
    importlib.reload(config)
    importlib.reload(utils)
    return config, utils


def test_accounts_are_migrated_to_encrypted_sqlite(monkeypatch, tmp_path):
    legacy_config = {
        "accounts": [
            {"id": 1, "name": "Alice", "username": "alice_no", "password": "secret_pw"}
        ],
        "current_account_id": 1,
    }
    (tmp_path / "config.json").write_text(json.dumps(legacy_config), encoding="utf-8")

    config, _utils = reload_storage(monkeypatch, tmp_path)
    loaded = config.load_config()

    assert loaded["accounts"][0]["username"] == "alice_no"
    assert loaded["accounts"][0]["password"] == "secret_pw"

    config_text = (tmp_path / "config.json").read_text(encoding="utf-8")
    assert "alice_no" not in config_text
    assert "secret_pw" not in config_text
    assert json.loads(config_text) == {"current_account_id": 1}

    db_bytes = (tmp_path / "secure_store.sqlite3").read_bytes()
    assert b"alice_no" not in db_bytes
    assert b"secret_pw" not in db_bytes
    assert (tmp_path / "secret.key").exists()


def test_sessions_are_saved_encrypted_in_sqlite(monkeypatch, tmp_path):
    config, utils = reload_storage(monkeypatch, tmp_path)
    cfg = {"accounts": [], "current_account_id": None}
    account_id = config.add_account(cfg, "bob_no", "bob_pw", "Bob")
    config.save_config(cfg)

    session = requests.Session()
    session.cookies.set("sessionid", "cookie_secret")
    utils.save_session(session, account_id)

    assert not (tmp_path / f"{account_id}.json").exists()
    db_bytes = (tmp_path / "secure_store.sqlite3").read_bytes()
    assert b"cookie_secret" not in db_bytes

    restored = requests.Session()
    assert utils.load_session(restored, account_id) is True
    assert restored.cookies.get("sessionid") == "cookie_secret"


def test_rollcall_settings_are_persisted_with_encrypted_accounts(monkeypatch, tmp_path):
    config, _utils = reload_storage(monkeypatch, tmp_path)
    cfg = {"accounts": [], "current_account_id": None}
    account_id = config.add_account(cfg, "dave_no", "dave_pw", "Dave")
    account = config.get_account_by_id(cfg, account_id)
    config.set_rollcall_settings(account, {"wait_before_answer": "10"})
    config.save_config(cfg)

    reloaded = config.load_config()
    reloaded_account = config.get_current_account(reloaded)

    assert config.get_rollcall_settings(reloaded_account)["wait_before_answer"] == 10
    config_text = (tmp_path / "config.json").read_text(encoding="utf-8")
    assert "dave_no" not in config_text
    assert "dave_pw" not in config_text


def test_legacy_session_json_is_migrated_and_removed(monkeypatch, tmp_path):
    config, utils = reload_storage(monkeypatch, tmp_path)
    cfg = {"accounts": [], "current_account_id": None}
    account_id = config.add_account(cfg, "carol_no", "carol_pw", "Carol")
    config.save_config(cfg)
    legacy_path = tmp_path / f"{account_id}.json"
    legacy_path.write_text(json.dumps({"sessionid": "legacy_cookie"}), encoding="utf-8")

    restored = requests.Session()
    assert utils.load_session(restored, account_id) is True

    assert restored.cookies.get("sessionid") == "legacy_cookie"
    assert not legacy_path.exists()
    assert b"legacy_cookie" not in (tmp_path / "secure_store.sqlite3").read_bytes()
