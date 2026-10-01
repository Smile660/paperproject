"""项目模型 → OpenDSS 脚本翻译（spec FR-3）。

约定：
- 节点/相映射 DSS 母线节点号：A→1、B→2、C→3；内部母线名 B<idx>（防用户 id 含非法字符）。
- 线路阻抗 = r/x(Ω/km) × 长度(km)，写入相域对角 Rmatrix/Xmatrix（Ω，忽略相间互感）。
- 负荷恒功率（model=1），Vminpu/Vmaxpu 放宽，低电压时不断开（电压安全按 max(V) 单侧评判）。
- 光伏用 Generator model=2（固定 PQ 注入、单位功率因数）：单相接指定相；三相为总额定、
  DSS 按相均分（即三相同步削减）。
- 平衡节点经近似理想 Vsource（Z=1e-6 Ω，压降 μV 级）接入，保证 slack 电压精确。
- 求解设置（Newton、容差、最大迭代）来自项目 algo（§5），两引擎一致（NFR-3）。
"""

from typing import Dict, List, Optional

from pvvr.model.schema import Project

_PHASE_TO_NODE = {"A": 1, "B": 2, "C": 3}


def _sanitize(name: str) -> str:
    return "".join(c if c.isalnum() else "_" for c in name)


class DssNaming:
    """schema id ↔ DSS 元件名 的双向映射。"""

    def __init__(self, project: Project):
        # DSS 内部母线名统一小写（AllNodeNames 返回小写）
        self.bus_of = {n.id: "b%d" % i for i, n in enumerate(project.nodes)}
        self.node_of_bus = {v: k for k, v in self.bus_of.items()}
        self.line_of = {ln.id: "Line.%s" % _sanitize(ln.id) for ln in project.lines}
        self.pv_of = {v.id: "Generator.%s" % _sanitize(v.id) for v in project.pvs}
        # 负荷元件名在 build_dss_text 生成时回填：(节点 id, 相) → 全名
        self.load_of = {}

    def bus_ref(self, node_id: str, phases: List[str]) -> str:
        return "%s.%s" % (self.bus_of[node_id],
                          ".".join(str(_PHASE_TO_NODE[p]) for p in phases))


def _matrix_diag(values: List[float]) -> str:
    n = len(values)
    rows = []
    for i in range(n):
        row = ["0"] * n
        row[i] = "%.10g" % values[i]
        rows.append(" ".join(row))
    return "(%s)" % " | ".join(rows)


def build_dss_text(project: Project,
                   pv_kw: Optional[Dict[str, float]] = None,
                   load_scale: float = 1.0,
                   naming: Optional[DssNaming] = None,
                   emit_solve: bool = True) -> str:
    """生成完整 .dss 文本。pv_kw 指定各光伏实际出力（kW，三相总额定）；
    未指定的光伏按额定满发。load_scale 为负荷整体缩放（统一曲线用）。
    emit_solve=False 供会话模式编译后逐次改参再求解。"""
    naming = naming or DssNaming(project)
    pv_kw = pv_kw or {}
    vll = project.base.v_base_kv
    slack = project.base.slack
    slack_node = next(n for n in project.nodes if n.id == slack.node)
    # 本引擎对 Vsource basekv 一律按线电压处理（含单相源，实测），故恒取 vll
    src_kv = vll

    # 注意：不向 DSS 写入频率（Set Frequency=50 在本引擎构建会把解归零，
    # 2026-10-01 实测）。模型阻抗为绝对 Ω、负荷恒功率，潮流解与频率无关，
    # 引擎按默认基准频率求解即等价于系统频率下的解；频率字段供 MATLAB 引擎与展示。
    L: List[str] = ["New Circuit.feeder basekv=%.10g pu=%.10g "
                    "R1=1e-6 X1=1e-6 R0=1e-6 X0=1e-6 bus1=%s"
                    % (src_kv, slack.v_pu,
                       naming.bus_ref(slack.node, slack_node.phases))]

    for ln in project.lines:
        r = [ln.r_ohm_per_km[p] * ln.length_km for p in ln.phases]
        x = [ln.x_ohm_per_km[p] * ln.length_km for p in ln.phases]
        L.append("New %s bus1=%s bus2=%s phases=%d Rmatrix=%s Xmatrix=%s normamps=%.10g"
                 % (naming.line_of[ln.id],
                    naming.bus_ref(ln.from_node, ln.phases),
                    naming.bus_ref(ln.to_node, ln.phases),
                    len(ln.phases), _matrix_diag(r), _matrix_diag(x),
                    ln.ampacity_a if ln.ampacity_a > 0 else 1e6))

    load_seq = 0
    for n in project.nodes:
        for ph in sorted(n.load_kw):
            pkw = n.load_kw.get(ph, 0.0) * load_scale
            qkvar = n.load_kvar.get(ph, 0.0) * load_scale
            if pkw <= 0 and qkvar <= 0:
                continue
            load_seq += 1
            full_name = "Load.L%05d_%s" % (load_seq, _sanitize(n.id))
            naming.load_of[(n.id, ph)] = full_name
            L.append("New %s bus1=%s.%d phases=1 kW=%.10g kvar=%.10g "
                     "model=1 conn=w Vminpu=0.05 Vmaxpu=2.0 status=fixed"
                     % (full_name, naming.bus_of[n.id],
                        _PHASE_TO_NODE[ph], pkw, qkvar))

    for v in project.pvs:
        kw = pv_kw.get(v.id, v.capacity_kw)
        if kw <= 0:
            continue
        L.append("New %s bus1=%s phases=%d kW=%.10g model=2 Vminpu=0.05 Vmaxpu=2.0"
                 % (naming.pv_of[v.id], naming.bus_ref(v.node, v.phases),
                    len(v.phases), kw))

    L.append("Set Mode=Snapshot")
    L.append("Set Algorithm=Newton")
    L.append("Set Tolerance=%.10g" % project.algo.pf_tol)
    L.append("Set Maxiterations=%d" % project.algo.pf_max_iter)
    if emit_solve:
        L.append("Solve")
    return "\n".join(L) + "\n"
