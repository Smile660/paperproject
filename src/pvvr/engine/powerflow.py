"""OpenDSS 潮流求解（spec FR-3）：单断面求解与结果结构。

结果结构与 MATLAB 引擎统一（NFR-3 前提）：全部节点分相电压 pu + 线路
分相负载率 + 收敛标志。不收敛抛 PowerflowError（中文诊断，FR-9）。
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import opendssdirect as dss

from pvvr.model.dss_writer import DssNaming, build_dss_text
from pvvr.model.schema import Project

_NODE_TO_PHASE = {1: "A", 2: "B", 3: "C"}


class PowerflowError(Exception):
    """潮流求解失败（不收敛 / 模型异常），message 为中文诊断。"""


@dataclass
class SnapshotResult:
    voltages_pu: Dict[Tuple[str, str], float] = field(default_factory=dict)
    line_loadings: Dict[str, Dict[str, float]] = field(default_factory=dict)
    converged: bool = False

    def max_v(self) -> Tuple[float, Tuple[str, str]]:
        key = max(self.voltages_pu, key=self.voltages_pu.get)
        return self.voltages_pu[key], key

    def min_v(self) -> Tuple[float, Tuple[str, str]]:
        key = min(self.voltages_pu, key=self.voltages_pu.get)
        return self.voltages_pu[key], key

    def violations(self, v_max: float) -> List[Tuple[str, str, float]]:
        """过电压越限清单（ADR-0001：只看上侧）。"""
        return [(n, p, v) for (n, p), v in sorted(self.voltages_pu.items())
                if v > v_max]

    def under_voltages(self, v_min: float) -> List[Tuple[str, str, float]]:
        """低电压清单：仅记录报告，不作控制目标。"""
        return [(n, p, v) for (n, p), v in sorted(self.voltages_pu.items())
                if v < v_min]


def _run_script(script: str) -> None:
    """编译执行 DSS 脚本。

    多行脚本直接经 Text.Command 会在矩阵语法处解析中断，须落盘临时
    .dss 后 compile（OpenDSS 标准用法）。
    """
    import os
    import tempfile
    fd, path = tempfile.mkstemp(suffix=".dss")
    os.close(fd)
    try:
        with open(path, "w", encoding="ascii") as f:
            f.write(script)
        dss.Text.Command('compile "%s"' % path.replace("\\", "/"))
    finally:
        try:
            os.remove(path)
        except OSError:
            pass


def _reset_engine() -> None:
    """清空引擎；首次调用（尚无电路）时 clear 报错，忽略即可。"""
    try:
        dss.Text.Command("clear")
    except Exception:
        pass


def _read_voltages(project: Project, naming: DssNaming
                   ) -> Dict[Tuple[str, str], float]:
    """按平台统一约定换算 pu：相电压 / (额定线电压/√3)。

    不用 AllBusMagPu：DSS 对单节点母线把 kVBase 当线电压直接用，
    纯单相/混接网络的 pu 会差 √3 倍（2026-10-01 实测）。
    """
    import math
    v_base_ln_v = project.base.v_base_kv * 1000.0 / math.sqrt(3.0)
    out: Dict[Tuple[str, str], float] = {}
    for bus in dss.Circuit.AllBusNames():
        dss.Circuit.SetActiveBus(bus)
        node_id = naming.node_of_bus.get(bus.lower())
        if node_id is None:
            continue
        nodes = dss.Bus.Nodes()
        vmags = dss.Bus.VMagAngle()[0::2]
        for node_idx, v in zip(nodes, vmags):
            phase = _NODE_TO_PHASE.get(int(node_idx))
            if phase is None:
                continue
            out[(node_id, phase)] = float(v) / v_base_ln_v
    return out


def _read_line_loadings(project: Project, naming: DssNaming
                        ) -> Dict[str, Dict[str, float]]:
    out: Dict[str, Dict[str, float]] = {}
    for ln in project.lines:
        if ln.ampacity_a <= 0:
            continue
        if not dss.Circuit.SetActiveElement(naming.line_of[ln.id]):
            continue
        currents = dss.CktElement.CurrentsMagAng()
        ncond = dss.CktElement.NumConductors()
        # 端子 1 的前 len(phases) 个导体（其余为中性）
        mags = [currents[2 * i] for i in range(min(len(ln.phases), ncond))]
        out[ln.id] = {p: m / ln.ampacity_a for p, m in zip(ln.phases, mags)}
    return out


def _did_converge() -> bool:
    """收敛查询薄封装（测试可替换）。"""
    return bool(dss.Solution.Converged())


def solve_snapshot(project: Project,
                   pv_kw: Optional[Dict[str, float]] = None,
                   load_scale: float = 1.0) -> SnapshotResult:
    """求解一个断面。pv_kw / load_scale 语义见 dss_writer.build_dss_text。"""
    naming = DssNaming(project)
    script = build_dss_text(project, pv_kw=pv_kw, load_scale=load_scale)
    _reset_engine()  # 重复求解前清理，避免元件重复定义告警中断
    _run_script(script)
    result = SnapshotResult()
    result.converged = _did_converge()
    if not result.converged:
        worst = ""
        try:
            vs = _read_voltages(project, naming)
            if vs:
                low_node, low_ph = min(vs, key=vs.get)
                worst = "电压最低处为节点 %s %s 相（%.4f pu）" % (
                    low_node, low_ph, vs[(low_node, low_ph)])
        except Exception:
            pass
        raise PowerflowError(
            "潮流不收敛（Newton 法，容差 %g，最大迭代 %d）。建议：降低该断面负荷"
            "或光伏出力、检查线路阻抗与长度是否过大。%s"
            % (project.algo.pf_tol, project.algo.pf_max_iter,
               ("最后迭代：" + worst) if worst else ""))
    result.voltages_pu = _read_voltages(project, naming)
    result.line_loadings = _read_line_loadings(project, naming)
    return result
