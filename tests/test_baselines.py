import csv

import pytest

from pvvr.engine.baselines import (CentralizedController, centralized_day,
                                   run_comparison)
from pvvr.engine.powerflow import PowerflowSession
from pvvr.engine.snapshot import spec_at_hour
from pvvr.model import schema as sch
from pvvr.model.presets import PRESETS


def _hp():
    return sch.project_from_dict(PRESETS["ieee33_hp"]())


def test_centralized_converges_and_equal_ratio():
    """集中式基线：收敛后 maxV ≤ Vmax，且各光伏同比例削减（FR-6）。"""
    p = _hp()
    session = PowerflowSession(p)
    rec = CentralizedController(p, session).control_snapshot(
        12, spec_at_hour(p, 12))
    assert rec.status == "收敛"
    assert rec.result.max_v()[0] <= p.base.v_max_pu + 1e-9
    ratios = {pid: rec.output[pid] / rec.avail[pid] for pid in rec.avail
              if rec.avail[pid] > 0}
    assert max(ratios.values()) - min(ratios.values()) < 1e-9   # 等比例
    assert all(abs(rec.curtail[pid] - rec.avail[pid] * (1 - rec.k_star)) < 1e-6
               for pid in rec.avail)


def test_centralized_night_no_control():
    p = _hp()
    session = PowerflowSession(p)
    rec = CentralizedController(p, session).control_snapshot(
        0, spec_at_hour(p, 0))
    assert rec.status == "无需控制" and rec.k_star == 1.0


def test_no_control_full_output_all_day():
    """无控制基线：全天满发不调节，越限如实暴露（FR-6）。"""
    from pvvr.engine.simulation import run_day
    day = run_day(_hp())
    assert max(day.max_v_series()) > 1.05            # 越限暴露
    over_hours = sum(1 for v in day.max_v_series() if v > 1.05)
    assert over_hours >= 1


def test_run_comparison_metrics_selfconsistent():
    """对比指标表数值自洽：削减电量可由逐时削减复算（票 05 验收）。"""
    p = _hp()
    cmpres = run_comparison(p)
    names = [m.name for m in cmpres.metrics]
    assert names == ["无控制", "集中式基线", "公平二分法"]
    nano, central, fair = cmpres.metrics
    assert nano.total_curtail_kwh == 0.0
    assert nano.all_safe is False
    assert central.all_safe and fair.all_safe
    # 复算：集中式逐时削减合计 == 指标表
    recomputed = sum(sum(r.curtail.values()) for r in cmpres.central)
    assert central.total_curtail_kwh == pytest.approx(recomputed, rel=1e-9)
    recomputed_fair = sum(sum(r.curtail.values()) for r in cmpres.fair.records)
    assert fair.total_curtail_kwh == pytest.approx(recomputed_fair, rel=1e-9)
    # 公平法贴边（更接近 Vmax），总削减不多于集中式（灵敏度加权削减效率更高）
    assert fair.max_v >= central.max_v - 1e-9
    assert fair.total_curtail_kwh <= central.total_curtail_kwh + 1e-6


def test_centralized_day_records():
    p = _hp()
    records = centralized_day(p)
    assert len(records) == 24
    assert all(r.hour == i for i, r in enumerate(records))
    assert all(r.result is not None for r in records)


def test_compare_cli(tmp_path, capsys, monkeypatch):
    from pvvr import cli
    monkeypatch.chdir(tmp_path)
    assert cli.main(["preset", "ieee33_hp", "--out", str(tmp_path / "p.json")]) == 0
    rc = cli.main(["compare", str(tmp_path / "p.json"),
                   "--out", str(tmp_path / "r")])
    assert rc == 0
    console = capsys.readouterr().out
    assert "三方式对比完成" in console and "公平二分法" in console
    run_dir = next((tmp_path / "r").iterdir())
    for fname in ("metrics.csv", "central_curtailment.csv",
                  "fair_curtailment.csv", "compare_voltage.png",
                  "compare_curtailment.png"):
        assert (run_dir / fname).exists(), fname
    rows = list(csv.reader((run_dir / "metrics.csv").open(encoding="utf-8-sig")))
    assert rows[0][0] == "方式" and len(rows) == 4
