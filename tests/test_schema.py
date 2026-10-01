import json

import pytest

from pvvr.model import schema as sch


def test_roundtrip_save_load_save_equivalent():
    """验收 6：保存→加载→再保存内容等价。"""
    from pvvr.model.presets import PRESETS
    for name in PRESETS:
        p1 = sch.project_from_dict(PRESETS[name]())
        json1 = sch.project_to_json(p1)
        p2 = sch.project_from_json(json1)
        json2 = sch.project_to_json(p2)
        assert json.loads(json1) == json.loads(json2), name


def test_schema_version_mismatch_rejected():
    data = {"schema_version": 2, "name": "x", "base": {}}
    with pytest.raises(sch.SchemaError) as ei:
        sch.project_from_dict(data)
    assert any("schema_version" in e for e in ei.value.errors)


def test_missing_required_fields_reported_in_chinese():
    with pytest.raises(sch.SchemaError) as ei:
        sch.project_from_dict({"schema_version": 1, "name": "x"})
    errs = "；".join(ei.value.errors)
    assert "base" in errs and "nodes" in errs
    assert any("缺少必填字段" in e for e in ei.value.errors)


def test_numeric_and_phase_errors_located():
    data = sch.project_to_dict(sch.default_project())
    data["base"]["v_base_kv"] = -5
    data["nodes"][1]["phases"] = ["A", "D"]
    data["pvs"][0]["capacity_kw"] = -1
    with pytest.raises(sch.SchemaError) as ei:
        sch.project_from_dict(data)
    errs = "；".join(ei.value.errors)
    assert "base.v_base_kv" in errs
    assert "非法相别" in errs
    assert "pvs[0].capacity_kw" in errs


def test_curve_must_be_24_points():
    data = sch.project_to_dict(sch.default_project())
    data["curves"] = {"load": [0.5] * 23, "pv": [0.1] * 24}
    with pytest.raises(sch.SchemaError) as ei:
        sch.project_from_dict(data)
    assert any("24 个" in e for e in ei.value.errors)


def test_vmin_vmax_ordering():
    data = sch.project_to_dict(sch.default_project())
    data["base"]["v_min_pu"] = 1.05
    data["base"]["v_max_pu"] = 0.95
    with pytest.raises(sch.SchemaError) as ei:
        sch.project_from_dict(data)
    assert any("v_min_pu" in e for e in ei.value.errors)


def test_json_syntax_error_message():
    with pytest.raises(sch.SchemaError) as ei:
        sch.project_from_json("{ not json")
    assert "JSON 语法错误" in "；".join(ei.value.errors)
