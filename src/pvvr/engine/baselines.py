"""对比基线（spec FR-6）：无控制 / 集中式（等比例 k 二分）/ 公平二分法。

集中式基线：不经公平责任权重，直接在 k ∈ [0,1] 上二分全局削减系数，
各光伏出力 = k × 可用出力（等比例），收敛带与公平法一致
（[Vmax−δ, Vmax]，spec FR-6/GLOSSARY「集中式基线」）。
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional

from pvvr.engine.control import ControlledDay, control_day
from pvvr.engine.powerflow import PowerflowSession, SnapshotResult
from pvvr.engine.simulation import DayResult, run_day
from pvvr.engine.snapshot import SnapshotSpec, pv_available, spec_at_hour
from pvvr.model.schema import Project


@dataclass
class CentralRecord:
    hour: Optional[int]
    status: str                  # 无需控制 | 收敛 | 未收敛(取保守侧) | 不可行
    k_star: float = 1.0
    curtail: Dict[str, float] = field(default_factory=dict)
    output: Dict[str, float] = field(default_factory=dict)
    avail: Dict[str, float] = field(default_factory=dict)
    iterations: List[dict] = field(default_factory=list)
    result: Optional[SnapshotResult] = None


class CentralizedController:
    """集中式基线：等比例削减，二分搜全局系数 k。"""

    def __init__(self, project: Project, session: PowerflowSession):
        self.project = project
        self.session = session

    def control_snapshot(self, hour: Optional[int],
                         spec: SnapshotSpec) -> CentralRecord:
        p = self.project
        v_max = p.base.v_max_pu
        delta = p.algo.delta
        rec = CentralRecord(hour=hour, status="无需控制")
        avail_full = pv_available(p, spec)
        rec.avail = dict(avail_full)
        pv_ids = list(avail_full)

        def outputs_at(k: float) -> Dict[str, float]:
            return {pid: avail_full[pid] * k for pid in pv_ids}

        base = self.session.solve(pv_kw=avail_full, load_scale=spec.load_scale)
        rec.result = base
        if base.max_v()[0] <= v_max:
            rec.k_star = 1.0
            rec.output = dict(avail_full)
            return rec

        zero = self.session.solve(pv_kw=outputs_at(0.0),
                                  load_scale=spec.load_scale)
        if zero.max_v()[0] > v_max:
            rec.status = "不可行"
            rec.k_star = 0.0
            rec.output = outputs_at(0.0)
            rec.result = zero
            return rec

        lo, hi = 0.0, 1.0            # lo：越限侧；hi：安全侧
        best_safe = 0.0
        hit = False
        for k in range(1, p.algo.max_iter + 1):
            mid = 0.5 * (lo + hi)
            res = self.session.solve(pv_kw=outputs_at(mid),
                                     load_scale=spec.load_scale)
            v = res.max_v()[0]
            rec.iterations.append({"k_iter": k, "lo": lo, "hi": hi,
                                   "k": mid, "max_v": v})
            if v > v_max:
                lo = mid
            elif v >= v_max - delta:
                rec.k_star, rec.status, rec.result = mid, "收敛", res
                hit = True
                break
            else:
                hi = mid
                best_safe = mid
        if not hit:
            rec.k_star = best_safe
            rec.status = "未收敛(取保守侧)"
            rec.result = self.session.solve(pv_kw=outputs_at(best_safe),
                                            load_scale=spec.load_scale)
        rec.output = outputs_at(rec.k_star)
        rec.curtail = {pid: avail_full[pid] - rec.output[pid] for pid in pv_ids}
        return rec


def centralized_day(project: Project,
                    session: Optional[PowerflowSession] = None) -> List[CentralRecord]:
    session = session or PowerflowSession(project)
    ctrl = CentralizedController(project, session)
    return [ctrl.control_snapshot(h, spec_at_hour(project, h)) for h in range(24)]


# ---------------------------------------------------------------------------
# 三方式一键对比与指标表
# ---------------------------------------------------------------------------

@dataclass
class ModeMetrics:
    name: str
    total_curtail_kwh: float
    peak_curtail_kw: float
    peak_hour: Optional[int]
    max_v: float
    min_v: float
    total_iterations: int
    elapsed_s: float
    all_safe: bool                 # 全天 maxV ≤ Vmax


@dataclass
class ComparisonResult:
    project_name: str
    nano: DayResult
    central: List[CentralRecord]
    fair: ControlledDay
    metrics: List[ModeMetrics]


def _metrics_from_records(name, records, elapsed, v_max, curtail_of, hour_of):
    total = sum(sum(curtail_of(r).values()) for r in records)
    peaks = [(sum(curtail_of(r).values()), hour_of(r)) for r in records]
    peak_kw, peak_hour = max(peaks) if peaks else (0.0, None)
    return ModeMetrics(
        name=name,
        total_curtail_kwh=total,
        peak_curtail_kw=peak_kw,
        peak_hour=peak_hour,
        max_v=max(r.result.max_v()[0] for r in records),
        min_v=min(r.result.min_v()[0] for r in records),
        total_iterations=sum(len(getattr(r, "iterations", []) or []) for r in records),
        elapsed_s=elapsed,
        all_safe=all(r.result.max_v()[0] <= v_max for r in records),
    )


def run_comparison(project: Project) -> ComparisonResult:
    """一键运行：无控制 → 集中式 → 公平二分法，同一项目同一曲线。"""
    import time
    v_max = project.base.v_max_pu

    t0 = time.perf_counter()
    nano = run_day(project)
    t_nano = time.perf_counter() - t0

    session = PowerflowSession(project)
    t0 = time.perf_counter()
    central = centralized_day(project, session)
    t_central = time.perf_counter() - t0

    t0 = time.perf_counter()
    fair = control_day(project)
    t_fair = time.perf_counter() - t0

    metrics = [
        _metrics_from_records("无控制", nano.records, t_nano, v_max,
                              lambda r: {}, lambda r: r.hour),
        _metrics_from_records("集中式基线", central, t_central, v_max,
                              lambda r: r.curtail, lambda r: r.hour),
        _metrics_from_records("公平二分法", fair.records, t_fair, v_max,
                              lambda r: r.curtail, lambda r: r.hour),
    ]
    return ComparisonResult(project.name, nano, central, fair, metrics)
