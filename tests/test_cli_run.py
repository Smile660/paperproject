import csv

from pvvr import cli


def test_run_snapshot_cli_ieee33(tmp_path, capsys, monkeypatch):
    """CLI 全链路：导出预设 → run --mode snapshot → CSV 落盘且含节点 18 电压。"""
    monkeypatch.chdir(tmp_path)
    assert cli.main(["preset", "ieee33", "--out", str(tmp_path / "p.json")]) == 0
    out = tmp_path / "results"
    rc = cli.main(["run", str(tmp_path / "p.json"), "--mode", "snapshot",
                   "--out", str(out)])
    assert rc == 0
    console = capsys.readouterr().out
    assert "快照潮流求解完成" in console
    run_dirs = list(out.iterdir())
    assert len(run_dirs) == 1
    volt_file = run_dirs[0] / "voltages.csv"
    assert volt_file.exists()
    rows = list(csv.reader(volt_file.open(encoding="utf-8-sig")))
    assert rows[0] == ["node", "phase", "v_pu"]
    node18 = [r for r in rows[1:] if r[0] == "18"]
    assert len(node18) == 3
    assert all(abs(float(r[2]) - 0.9131) < 0.005 for r in node18)
    assert (run_dirs[0] / "line_loading.csv").exists()


def test_run_unvalidated_project_rejected(tmp_path, capsys, monkeypatch):
    """领域校验失败（环路）→ 拒绝运行（验收 6）。"""
    monkeypatch.chdir(tmp_path)
    from pvvr.model import schema as sch
    p = sch.default_project()
    p.nodes.append(sch.Node(id="3"))
    p.lines.append(sch.Line(id="L2", from_node="2", to_node="3", length_km=1.0,
                            r_ohm_per_km={"A": 0.3}, x_ohm_per_km={"A": 0.3}))
    p.lines.append(sch.Line(id="L3", from_node="3", to_node="1", length_km=1.0,
                            r_ohm_per_km={"A": 0.3}, x_ohm_per_km={"A": 0.3}))
    f = tmp_path / "loop.json"
    f.write_text(sch.project_to_json(p), encoding="utf-8")
    import pytest
    with pytest.raises(SystemExit):
        cli.main(["run", str(f)])
    out = capsys.readouterr().out
    assert "环路" in out


def test_run_matlab_engine_stub(tmp_path, capsys):
    rc = cli.main(["run", "whatever.json", "--engine", "matlab"])
    assert rc == 2
    assert "票据 10" in capsys.readouterr().out


def test_run_24h_cli(tmp_path, capsys, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert cli.main(["preset", "single_phase", "--out", str(tmp_path / "p.json")]) == 0
    out = tmp_path / "r"
    rc = cli.main(["run", str(tmp_path / "p.json"), "--mode", "24h",
                   "--out", str(out)])
    assert rc == 0
    console = capsys.readouterr().out
    assert "24h 仿真完成" in console
    run_dir = next(out.iterdir())
    assert (run_dir / "summary.csv").exists()
    assert (run_dir / "voltages.csv").exists()
    assert (run_dir / "voltage_trajectory.png").stat().st_size > 10_000


def test_run_snapshot_at_hour_cli(tmp_path, capsys, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert cli.main(["preset", "single_phase", "--out", str(tmp_path / "p.json")]) == 0
    rc = cli.main(["run", str(tmp_path / "p.json"), "--t", "12",
                   "--out", str(tmp_path / "r12")])
    assert rc == 0
    assert "第 12 时断面" in capsys.readouterr().out


def test_run_fair_control_cli(tmp_path, capsys, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert cli.main(["preset", "ieee33_hp", "--out", str(tmp_path / "p.json")]) == 0
    rc = cli.main(["run", str(tmp_path / "p.json"), "--mode", "24h",
                   "--control", "fair", "--out", str(tmp_path / "r")])
    assert rc == 0
    console = capsys.readouterr().out
    assert "公平二分法控制完成" in console and "JFI" in console
    run_dir = next((tmp_path / "r").iterdir())
    for fname in ("curtailment.csv", "iterations.csv", "summary.csv",
                  "voltages.csv", "voltage_trajectory.png"):
        assert (run_dir / fname).exists(), fname


def test_set_curve_cli(tmp_path, capsys, monkeypatch):
    monkeypatch.chdir(tmp_path)
    import json
    proj = tmp_path / "p.json"
    assert cli.main(["preset", "single_phase", "--out", str(proj)]) == 0
    csvf = tmp_path / "pv.csv"
    csvf.write_text("hour,value\n" + "".join("%d,%.3f\n" % (h, 1.0 if h == 10 else 0.0)
                                             for h in range(24)), encoding="utf-8")
    rc = cli.main(["set-curve", str(proj), "--kind", "pv", "--csv", str(csvf)])
    assert rc == 0
    data = json.loads(proj.read_text(encoding="utf-8"))
    assert data["curves"]["pv"][10] == 1.0
    assert sum(data["curves"]["pv"]) == 1.0
    assert "已将 pv 曲线导入" in capsys.readouterr().out
