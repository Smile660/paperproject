"""公平二分法电压调节（论文式 13–17、24–26；spec FR-4）。

NFR-4：公平系数 + 二分控制全部集中本文件（MATLAB 镜像同构），
替换公式不影响其余部分。论文已核对（spec §9）：

- 式 13  R_i = |S_vp,i|·P_cur,i / Σ_j |S_vp,j|·P_cur,j
        （S_vp,i：光伏 i 对当前越限最严重节点的有功灵敏度，平台以潮流
          摄动计算替代论文的量测估计；P_cur,i：当前可削减上限＝可用出力）
- 式 14  H_i = Σ_{τ<t} P_cur,i,τ / (Σ_{τ<t} P_ava,i,τ + ε)，截至 t−1 累积
- 式 15  C_i = exp(−γ·H_i) / Σ_j exp(−γ·H_j)
- 式 16  ω_i = R_i^α·C_i^β / Σ_j R_j^α·C_j^β
- 式 17  二分区间 [0, Σ可用出力]，越限→左端右移，安全→右端左移；
          收敛带 [Vmax−δ, Vmax] 命中即停（δ=algo.delta）
- Q-1：ω_i 每断面开始计算一次，二分过程中固定（spec §9 已确认）
- Q-2：H 每次运行从 0 重新累积，不跨运行持久化（spec §9 已确认）

控制目标仅过电压（ADR-0001）：max(V) ≤ Vmax；Vmin 越限只记录不控制。
"""

import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from pvvr.engine.powerflow import PowerflowSession, SnapshotResult
from pvvr.engine.snapshot import SnapshotSpec, pv_available, spec_at_hour
from pvvr.model.schema import Project

EPS_H = 1e-6  # 式 14 防零小正数


# ---------------------------------------------------------------------------
# 公平状态（式 14/15）
# ---------------------------------------------------------------------------

@dataclass
class FairnessState:
    """各光伏累计削减/可用电量（kWh，按断面时长 1h 累积）。"""

    cur_kwh: Dict[str, float] = field(default_factory=dict)
    av_kwh: Dict[str, float] = field(default_factory=dict)

    def h(self, pv_id: str) -> float:
        return self.cur_kwh.get(pv_id, 0.0) / (self.av_kwh.get(pv_id, 0.0) + EPS_H)

    def update(self, avail: Dict[str, float], curtail: Dict[str, float]) -> None:
        for pid, av in avail.items():
            self.av_kwh[pid] = self.av_kwh.get(pid, 0.0) + av
            self.cur_kwh[pid] = self.cur_kwh.get(pid, 0.0) + curtail.get(pid, 0.0)


def compensation_factors(state: FairnessState, pv_ids: List[str],
                         gamma: float) -> Dict[str, float]:
    """式 15：C_i = exp(−γH_i)/Σ exp(−γH_j)。"""
    exps = {pid: math.exp(-gamma * state.h(pid)) for pid in pv_ids}
    total = sum(exps.values())
    if total <= 0:
        return {pid: 1.0 / len(pv_ids) for pid in pv_ids}
    return {pid: e / total for pid, e in exps.items()}


# ---------------------------------------------------------------------------
# 公平责任权重（式 13/16）
# ---------------------------------------------------------------------------

def fairness_weights(sensitivity: Dict[str, float],
                     avail: Dict[str, float],
                     comp: Dict[str, float],
                     alpha: float, beta: float) -> Dict[str, float]:
    """式 16：ω_i = R_i^α·C_i^β / Σ…；R_i 按式 13 归一化。"""
    raw_r = {pid: abs(sensitivity.get(pid, 0.0)) * avail[pid] for pid in avail}
    sum_r = sum(raw_r.values())
    if sum_r <= 0:
        # 无灵敏度信息（如全零出力）→ R 均匀
        r = {pid: 1.0 / len(raw_r) for pid in raw_r}
    else:
        r = {pid: v / sum_r for pid, v in raw_r.items()}
    raw_w = {pid: (r[pid] ** alpha) * (comp[pid] ** beta) for pid in r}
    sum_w = sum(raw_w.values())
    if sum_w <= 0:
        return {pid: 1.0 / len(raw_w) for pid in raw_w}
    return {pid: v / sum_w for pid, v in raw_w.items()}


def allocate_curtailment(c: float, weights: Dict[str, float],
                         avail: Dict[str, float]
                         ) -> Tuple[Dict[str, float], Dict[str, float], List[str]]:
    """式 25 的分配与饱和钳位（FR-4 第 4 步）：削减_i = min(C·ω_i, 可用_i)。"""
    curtail = {}
    saturated = []
    for pid, av in avail.items():
        want = c * weights[pid]
        curtail[pid] = min(want, av)
        if want > av + 1e-9:
            saturated.append(pid)
    output = {pid: av - curtail[pid] for pid, av in avail.items()}
    return curtail, output, saturated

@dataclass
class ControlRecord:
    hour: Optional[int]
    status: str                      # 无需控制 | 收敛 | 未收敛(取保守侧) | 不可行
    c_star: float = 0.0              # 收敛的总削减量 kW
    weights: Dict[str, float] = field(default_factory=dict)
    avail: Dict[str, float] = field(default_factory=dict)
    curtail: Dict[str, float] = field(default_factory=dict)
    output: Dict[str, float] = field(default_factory=dict)
    saturated: List[str] = field(default_factory=list)
    worst_node: Tuple[str, str] = ("", "")          # 越限最严重节点（相）
    iterations: List[dict] = field(default_factory=list)
    result: Optional[SnapshotResult] = None         # 控制后潮流


# ---------------------------------------------------------------------------
# 控制器
# ---------------------------------------------------------------------------

class FairBisectionController:
    """逐断面执行公平二分法；跨断面携带公平状态 H（Q-2：运行内累积）。"""

    def __init__(self, project: Project, session: PowerflowSession):
        self.project = project
        self.session = session
        self.state = FairnessState()
        self.pv_ids = [v.id for v in project.pvs if v.controllable]

    # -- 式 13 的 S_vp：潮流摄动 ------------------------------------------
    def _sensitivities(self, avail: Dict[str, float],
                       base: SnapshotResult) -> Dict[str, float]:
        _, worst_key = base.max_v()
        sens: Dict[str, float] = {}
        for pid in self.pv_ids:
            delta = max(1.0, 0.01 * avail[pid])
            perturbed = dict(avail)
            perturbed[pid] = max(0.0, avail[pid] - delta)
            res = self.session.solve(pv_kw=perturbed)
            v_worst = res.voltages_pu.get(worst_key, 0.0)
            v_base = base.voltages_pu[worst_key]
            sens[pid] = (v_base - v_worst) / delta   # 削减降圧 → S > 0
        return sens

    def _allocate(self, c: float, weights: Dict[str, float],
                  avail: Dict[str, float]) -> Tuple[Dict[str, float], Dict[str, float], List[str]]:
        return allocate_curtailment(c, weights, avail)

    def control_snapshot(self, hour: Optional[int],
                         spec: SnapshotSpec) -> ControlRecord:
        p = self.project
        v_max = p.base.v_max_pu
        delta = p.algo.delta
        max_iter = p.algo.max_iter
        rec = ControlRecord(hour=hour, status="无需控制")

        avail_full = pv_available(p, spec)
        avail = {pid: avail_full[pid] for pid in self.pv_ids}
        rec.avail = dict(avail)

        # 基态：光伏按可用出力满发
        base = self.session.solve(pv_kw=avail_full, load_scale=spec.load_scale)
        vmax0, worst = base.max_v()
        rec.result = base
        rec.worst_node = worst
        if vmax0 <= v_max:
            self.state.update(avail, {pid: 0.0 for pid in self.pv_ids})
            return rec

        # 不可行判定：全额削减仍越限
        zero = self.session.solve(pv_kw={pid: 0.0 for pid in self.pv_ids},
                                  load_scale=spec.load_scale)
        if zero.max_v()[0] > v_max:
            rec.status = "不可行"
            rec.curtail = {pid: avail[pid] for pid in self.pv_ids}
            rec.output = {pid: 0.0 for pid in self.pv_ids}
            rec.result = zero
            self.state.update(avail, rec.curtail)
            return rec

        # 公平责任权重（Q-1：断面内固定）
        sens = self._sensitivities(avail, base)
        comp = compensation_factors(self.state, self.pv_ids, p.algo.gamma)
        weights = fairness_weights(sens, avail, comp, p.algo.alpha, p.algo.beta)
        rec.weights = weights

        # 二分（式 17 + 收敛带）
        total = sum(avail.values())
        lo, hi = 0.0, total          # lo：越限侧；hi：安全侧（zero 已证安全）
        best_safe = total
        hit = False
        for k in range(1, max_iter + 1):
            mid = 0.5 * (lo + hi)
            curtail, output, _sat = self._allocate(mid, weights, avail)
            res = self.session.solve(pv_kw=output, load_scale=spec.load_scale)
            v = res.max_v()[0]
            rec.iterations.append({"k": k, "lo": lo, "hi": hi, "C": mid, "max_v": v})
            if v > v_max:
                lo = mid
            elif v >= v_max - delta:
                rec.c_star = mid
                rec.status = "收敛"
                rec.curtail, rec.output, rec.saturated = self._allocate(
                    mid, weights, avail)
                rec.result = res
                hit = True
                break
            else:
                hi = mid
                best_safe = mid
        if not hit:
            rec.c_star = best_safe
            rec.status = "未收敛(取保守侧)"
            rec.curtail, rec.output, rec.saturated = self._allocate(
                best_safe, weights, avail)
            rec.result = self.session.solve(pv_kw=rec.output,
                                            load_scale=spec.load_scale)

        self.state.update(avail, rec.curtail)
        return rec


# ---------------------------------------------------------------------------
# 24h 控制与 JFI（式 24–26）
# ---------------------------------------------------------------------------

@dataclass
class ControlledDay:
    records: List[ControlRecord] = field(default_factory=list)
    project_name: str = ""

    def hour_series(self):
        return [r.hour for r in self.records]

    def max_v_series(self):
        return [r.result.max_v()[0] for r in self.records]

    def min_v_series(self):
        return [r.result.min_v()[0] for r in self.records]

    def jfi(self) -> Optional[float]:
        """Jain 公平指标（式 24–26）：r_i = Σ削减/Σ可用；JFI=(Σr)²/(N·Σr²)。"""
        if not self.records:
            return None
        cur = {}
        av = {}
        for rec in self.records:
            for pid, v in rec.curtail.items():
                cur[pid] = cur.get(pid, 0.0) + v
            for pid, v in rec.avail.items():
                av[pid] = av.get(pid, 0.0) + v
        ratios = [cur[pid] / (av[pid] + EPS_H) for pid in cur]
        n = len(ratios)
        if n == 0:
            return None
        sum_r = sum(ratios)
        sum_r2 = sum(x * x for x in ratios)
        if sum_r2 <= 0:
            return 1.0
        return (sum_r * sum_r) / (n * sum_r2)


def control_day(project: Project, session: Optional[PowerflowSession] = None
                ) -> ControlledDay:
    """典型日逐断面控制（H 跨断面按小时顺序累积）。"""
    session = session or PowerflowSession(project)
    ctrl = FairBisectionController(project, session)
    day = ControlledDay(project_name=project.name)
    for hour in range(24):
        spec = spec_at_hour(project, hour)
        day.records.append(ctrl.control_snapshot(hour, spec))
    return day


def control_snapshot_now(project: Project, hour: Optional[int] = None,
                         session: Optional[PowerflowSession] = None
                         ) -> ControlRecord:
    """单断面控制（快照模式；hour=None 按额定断面）。"""
    session = session or PowerflowSession(project)
    ctrl = FairBisectionController(project, session)
    if hour is not None:
        spec = spec_at_hour(project, hour)
    else:
        spec = SnapshotSpec(hour=None, load_scale=1.0, pv_factor=1.0)
    return ctrl.control_snapshot(hour, spec)
