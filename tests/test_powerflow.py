import time

import pytest

from pvvr.engine.powerflow import PowerflowError, solve_snapshot
from pvvr.model import schema as sch
from pvvr.model.presets import PRESETS


def _ieee33():
    return sch.project_from_dict(PRESETS["ieee33"]())


def _single():
    return sch.project_from_dict(PRESETS["single_phase"]())


def test_et1_ieee33_base_case():
    """ET-1：最低电压 0.913 pu（节点 18），偏差 <0.5%；三相平衡复制正确。"""
    r = solve_snapshot(_ieee33())
    assert r.converged
    vmin, (nmin, _) = r.min_v()
    assert abs(vmin - 0.9131) < 0.9131 * 0.005
    assert nmin == "18"
    va, vb, vc = (r.voltages_pu[("18", p)] for p in "ABC")
    assert abs(va - vb) < 1e-3 and abs(vb - vc) < 1e-3
    assert abs(r.voltages_pu[("1", "A")] - 1.0) < 1e-6


def test_single_phase_preset_solves():
    r = solve_snapshot(_single())
    assert r.converged
    assert abs(r.voltages_pu[("1", "A")] - 1.0) < 1e-6   # 平衡节点 1.0 pu
    assert all(0.9 < v < 1.1 for v in r.voltages_pu.values())
    # 光伏满发抬升并网点电压
    assert r.voltages_pu[("4", "A")] > 1.0


def _mixed_project():
    """三相主干 + A 相支线 + 单相负荷（三相混接最小例）。"""
    return sch.Project(
        schema_version=1,
        name="混接测试",
        base=sch.NetworkBase(v_base_kv=12.66),
        nodes=[
            sch.Node(id="1"),
            sch.Node(id="2"),
            sch.Node(id="3", phases=["A"], load_kw={"A": 200.0},
                     load_kvar={"A": 100.0}),
        ],
        lines=[
            sch.Line(id="L1", from_node="1", to_node="2", length_km=1.0,
                     r_ohm_per_km={"A": 0.3, "B": 0.3, "C": 0.3},
                     x_ohm_per_km={"A": 0.35, "B": 0.35, "C": 0.35},
                     ampacity_a=400.0),
            sch.Line(id="L2", from_node="2", to_node="3", phases=["A"],
                     length_km=2.0,
                     r_ohm_per_km={"A": 0.5}, x_ohm_per_km={"A": 0.4},
                     ampacity_a=200.0),
        ],
    )


def test_three_phase_mixed_unbalanced():
    """单相负荷只影响所在相：A 相电压低于 B/C 相（FR-1 三相混接）。"""
    p = _mixed_project()
    r = solve_snapshot(p)
    assert r.converged
    v2a = r.voltages_pu[("2", "A")]
    v2b = r.voltages_pu[("2", "B")]
    assert v2a < v2b - 1e-4, (v2a, v2b)
    assert r.voltages_pu[("3", "A")] < v2a


def test_pv_curtailment_lowers_voltage():
    """削减光伏有功 → 电压不升（控制闭环的单调性前提，票 04 依赖）。"""
    p = _single()
    full = solve_snapshot(p)
    curtailed = solve_snapshot(p, pv_kw={"PV1": 0.0, "PV2": 0.0})
    assert curtailed.max_v()[0] < full.max_v()[0]
    assert full.max_v()[0] > 1.0


def test_load_scale_effect():
    p = _ieee33()
    light = solve_snapshot(p, load_scale=0.5)
    rated = solve_snapshot(p, load_scale=1.0)
    assert light.min_v()[0] > rated.min_v()[0]


def test_performance_ieee33():
    t0 = time.perf_counter()
    r = solve_snapshot(_ieee33())
    assert r.converged
    assert time.perf_counter() - t0 < 2.0   # 实测 ~30ms，留裕量


def test_non_convergence_chinese_diagnostic(monkeypatch):
    from pvvr.engine import powerflow as pf
    monkeypatch.setattr(pf, "_did_converge", lambda: False)
    with pytest.raises(PowerflowError) as ei:
        solve_snapshot(_ieee33())
    msg = str(ei.value)
    assert "潮流不收敛" in msg and "建议" in msg


def test_line_loading_read():
    r = solve_snapshot(_ieee33())
    assert set(r.line_loadings) == {"L%02d" % i for i in range(1, 33)}
    l01 = r.line_loadings["L01"]
    assert set(l01) == {"A", "B", "C"}
    assert all(0.0 < v < 1.0 for v in l01.values())
    # 平衡网三相近似相等
    assert max(l01.values()) - min(l01.values()) < 0.01
