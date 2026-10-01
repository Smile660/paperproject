import json

from pvvr import settings as st


def test_defaults_when_no_file(tmp_path, monkeypatch):
    monkeypatch.setattr(st, "settings_path", lambda: tmp_path / "settings.json")
    conf = st.load_settings()
    assert conf["default_engine"] == "opendss"
    assert conf["ui_port"] == 8080
    assert conf["matlab_path"] == ""


def test_save_then_load_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setattr(st, "settings_path", lambda: tmp_path / "settings.json")
    st.save_settings({"matlab_path": r"D:\MATLAB\R2024b\bin\matlab.exe",
                      "ui_port": 9000})
    conf = st.load_settings()
    assert conf["matlab_path"].endswith("matlab.exe")
    assert conf["ui_port"] == 9000
    assert conf["default_engine"] == "opendss"    # 未改动键保留默认


def test_unknown_keys_preserved_not_merged(tmp_path, monkeypatch):
    path = tmp_path / "settings.json"
    monkeypatch.setattr(st, "settings_path", lambda: path)
    path.write_text(json.dumps({"ui_port": 8081, "junk": "keep-me"}),
                    encoding="utf-8")
    conf = st.load_settings()
    assert conf["ui_port"] == 8081
    assert "junk" not in conf                        # 未知键不进入配置视图


def test_corrupt_file_falls_back_to_defaults(tmp_path, monkeypatch):
    path = tmp_path / "settings.json"
    monkeypatch.setattr(st, "settings_path", lambda: path)
    path.write_text("{ broken", encoding="utf-8")
    assert st.load_settings() == st.DEFAULTS


def test_algo_defaults_nested_merge(tmp_path, monkeypatch):
    """票据要求 §5 参数默认值进设置持久化：嵌套 algo_defaults 部分更新生效。"""
    monkeypatch.setattr(st, "settings_path", lambda: tmp_path / "settings.json")
    st.save_settings({"algo_defaults": {"delta": 0.001, "max_iter": 40}})
    conf = st.load_settings()
    assert conf["algo_defaults"]["delta"] == 0.001
    assert conf["algo_defaults"]["max_iter"] == 40
    assert conf["algo_defaults"]["alpha"] == 1.0          # 未改子键保留默认
    # 只改子键不动外层其他设置
    assert conf["default_engine"] == "opendss"
