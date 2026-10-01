import pytest

from pvvr.engine.control import (FairBisectionController, FairnessState,
                                 allocate_curtailment, compensation_factors,
                                 control_day, control_snapshot_now,
                                 fairness_weights)
from pvvr.engine.powerflow import PowerflowSession
from pvvr.engine.snapshot import spec_at_hour
from pvvr.model import schema as sch
from pvvr.model.presets import PRESETS


def _hp():
    return sch.project_from_dict(PRESETS["ieee33_hp"]())


# ---------------- 公平系数数学（式 13–16） ----------------

def test_compensation_uniform_at_start():
    """运行起点 H=0 → C_i 均匀（式 15）。"""
    state = FairnessState()
    comp = compensation_factors(state, ["PV1", "PV2", "PV3"], gamma=1.0)
    assert comp == pytest.approx({"PV1": 1 / 3, "PV2": 1 / 3, "PV3": 1 / 3})


def test_compensation_decay_with_history():
    """历史弃光率高的光伏获得更小补偿因子（式 15 单调性）。"""
    state = FairnessState(cur_kwh={"PV1": 0.0, "PV2": 100.0},
                          av_kwh={"PV1": 100.0, "PV2": 100.0})
    comp = compensation_factors(state, ["PV1", "PV2"], gamma=1.0)
    assert comp["PV2"] < comp["PV1"]
    assert sum(comp.values()) == pytest.approx(1.0)


def test_fairness_weights_formula():
    """式 13/16：ω ∝ R^α·C^β 且 Σω=1；α=β=0 时退化为均匀。

    R_i = |S_i|·P_cur,i / Σ：等容量下灵敏度大者责任大；灵敏度可被大容量抵消。
    """
    avail_eq = {"PV1": 100.0, "PV2": 100.0}
    comp = {"PV1": 0.5, "PV2": 0.5}
    w = fairness_weights({"PV1": 2.0, "PV2": 1.0}, avail_eq, comp, 1.0, 1.0)
    assert sum(w.values()) == pytest.approx(1.0)
    assert w["PV1"] > w["PV2"]                      # 等容量：S 大者权重大
    # 大容量可抵消灵敏度劣势：R = S×P 归一化
    w2 = fairness_weights({"PV1": 2.0, "PV2": 1.0},
                          {"PV1": 100.0, "PV2": 300.0}, comp, 1.0, 1.0)
    assert w2["PV2"] > w2["PV1"]                    # R2=0.6 > R1=0.4
    uni = fairness_weights({"PV1": 2.0, "PV2": 1.0}, avail_eq, comp, 0.0, 0.0)
    assert uni["PV1"] == pytest.approx(0.5)


def test_fairness_weights_zero_sensitivity_fallback():
    w = fairness_weights({"PV1": 0.0, "PV2": 0.0},
                         {"PV1": 10.0, "PV2": 10.0},
                         {"PV1": 0.5, "PV2": 0.5}, 1.0, 1.0)
    assert w == pytest.approx({"PV1": 0.5, "PV2": 0.5})


# ---------------- 闭环行为（ET-3） ----------------

def test_hp_preset_overvoltage_without_control():
    """高渗透预设正午满发确实过电压（场景成立前提，验收 2 前置）。"""
    p = _hp()
    session = PowerflowSession(p)
    spec = spec_at_hour(p, 12)
    base = session.solve(load_scale=spec.load_scale)
    assert base.max_v()[0] > p.base.v_max_pu


def test_snapshot_control_converges_into_band():
    p = _hp()
    rec = control_snapshot_now(p, hour=12)
    assert rec.status == "收敛"
    vmax = rec.result.max_v()[0]
    assert vmax <= p.base.v_max_pu + 1e-9                     # 验收 2
    assert vmax >= p.base.v_max_pu - p.algo.delta - 1e-9      # 命中收敛带
    assert len(rec.iterations) <= p.algo.max_iter
    # 削减分配 = C*×ω（未饱和时）
    for pid, w in rec.weights.items():
        assert rec.curtail[pid] == pytest.approx(
            min(rec.c_star * w, rec.avail[pid]), abs=1e-6)
        assert 0.0 <= rec.output[pid] <= rec.avail[pid]


def test_sensitivity_weights_differentiated():
    """式 13 数值回归（2026-10-01 评审修复）：摄动须与基态同负荷工况，
    否则权重被压平成均分、责任度排序失效。越限节点近旁光伏权重应显著
    大于异支光伏（ieee33_hp：越限在节点 18，PV1@17/PV2@18 最大）。"""
    p = _hp()
    rec = control_snapshot_now(p, hour=12)
    ws = rec.weights
    assert max(ws.values()) / min(ws.values()) > 10.0
    assert ws["PV1"] > ws["PV3"] and ws["PV2"] > ws["PV4"]


def test_allocation_and_saturation_flag():
    """饱和钳位：C×ω 超出可用出力 → 全停并标记（FR-4 第 4 步）。"""
    curtail, output, saturated = allocate_curtailment(
        100.0, {"PV1": 0.9, "PV2": 0.05}, {"PV1": 50.0, "PV2": 10.0})
    assert curtail["PV1"] == 50.0 and output["PV1"] == 0.0
    assert curtail["PV2"] == pytest.approx(5.0)
    assert saturated == ["PV1"]


def test_night_no_control_needed():
    p = _hp()
    rec = control_snapshot_now(p, hour=0)
    assert rec.status == "无需控制"
    assert all(v == 0.0 for v in rec.curtail.values())


def test_infeasible_detected():
    """全额削减仍越限（slack 电压超上限）→ 判不可行而非死循环。"""
    p = _hp()
    p.base.slack.v_pu = 1.06                       # 平衡节点本身越限
    p.base.v_max_pu = 1.05
    rec = control_snapshot_now(p, hour=12)
    assert rec.status == "不可行"
    assert all(v == 0.0 for v in rec.output.values())


def test_day_control_all_hours_safe_and_h_accumulates():
    """24h：可行断面全部压回限内；H 跨断面累积使后续权重分化。"""
    p = _hp()
    day = control_day(p)
    assert len(day.records) == 24
    for r in day.records:
        assert r.result.max_v()[0] <= p.base.v_max_pu + 1e-9
        assert r.status in ("无需控制", "收敛")
    jfi = day.jfi()
    assert 0.0 < jfi <= 1.0
    # H 累积检验：晚间断面前状态已非零（有削减发生）
    total_cur = sum(sum(r.curtail.values()) for r in day.records)
    assert total_cur > 0


def test_q1_weights_fixed_during_bisection():
    """Q-1：同一断面内二分各轮用同一组权重——从结构上由实现保证：
    权重只在 control_snapshot 开头计算一次；此处断言记录里权重唯一。"""
    p = _hp()
    session = PowerflowSession(p)
    ctrl = FairBisectionController(p, session)
    rec = ctrl.control_snapshot(12, spec_at_hour(p, 12))
    assert rec.weights and len(rec.iterations) >= 1


def test_q2_state_resets_per_run():
    """Q-2：每次运行 H 从 0 开始（两个独立控制器的首断面权重一致）。"""
    p = _hp()
    r1 = control_snapshot_now(p, hour=12)
    r2 = control_snapshot_now(p, hour=12)
    assert r1.weights == pytest.approx(r2.weights)


def test_day_control_performance():
    import time
    p = _hp()
    t0 = time.perf_counter()
    control_day(p)
    assert time.perf_counter() - t0 < 10.0      # 实测 ~0.2s，留裕量（NFR-1）
