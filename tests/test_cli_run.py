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
