import json

from pvvr import cli


def test_validate_preset_ieee33(capsys):
    assert cli.main(["validate", "--preset", "ieee33"]) == 0
    out = capsys.readouterr().out
    assert "校验通过" in out and "33" in out


def test_validate_preset_single_phase(capsys):
    assert cli.main(["validate", "--preset", "single_phase"]) == 0


def test_validate_structural_error_file(tmp_path, capsys):
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps({"schema_version": 1, "name": "x"}), encoding="utf-8")
    assert cli.main(["validate", str(bad)]) == 1
    out = capsys.readouterr().out
    assert "结构校验未通过" in out and "缺少必填字段" in out


def test_validate_loop_file(tmp_path, capsys):
    """验收 6 之环路部分（CLI 出口）：含环路项目被拒绝并列出环路元素。"""
    from pvvr.model import schema as sch
    p = sch.default_project()
    p.nodes.append(sch.Node(id="3"))
    p.lines.append(sch.Line(id="L2", from_node="2", to_node="3", length_km=1.0,
                            r_ohm_per_km={"A": 0.3}, x_ohm_per_km={"A": 0.3}))
    p.lines.append(sch.Line(id="L3", from_node="3", to_node="1", length_km=1.0,
                            r_ohm_per_km={"A": 0.3}, x_ohm_per_km={"A": 0.3}))
    f = tmp_path / "loop.json"
    f.write_text(sch.project_to_json(p), encoding="utf-8")
    assert cli.main(["validate", str(f)]) == 1
    out = capsys.readouterr().out
    assert "领域校验未通过" in out and "环路" in out and "L3" in out


def test_validate_missing_file(tmp_path, capsys):
    assert cli.main(["validate", str(tmp_path / "nope.json")]) == 2
    assert "文件不存在" in capsys.readouterr().out


def test_preset_export_and_revalidate(tmp_path, capsys, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert cli.main(["preset", "ieee33"]) == 0
    out_file = tmp_path / "projects" / "ieee33.json"
    assert out_file.exists()
    assert cli.main(["validate", str(out_file)]) == 0
    assert "校验通过" in capsys.readouterr().out


def test_unknown_preset(capsys):
    assert cli.main(["validate", "--preset", "nope"]) == 2
    assert "未知预设" in capsys.readouterr().out
