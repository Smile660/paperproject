"""项目 JSON 模型：全量 schema、解析与序列化。

schema 在本文件一次定齐（票据 01 约定）：节点/线路/光伏/线型库/统一曲线/
通信图/网络参数/算法参数。后续票据只加行为，不改结构；结构变更需升
schema_version 并提供迁移。

单位约定（spec 附录/FR-1）：电压 pu 基准=额定线电压；功率 kW/kvar；
阻抗 Ω/km 相域对角（忽略相间互感）；长度 km；载流量 A；光伏容量 kW。
"""

import copy
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

PHASES = ("A", "B", "C")
SCHEMA_VERSION = 1


class SchemaError(Exception):
    """结构解析失败。errors 为「路径: 中文说明」列表，定位到字段/条目。"""

    def __init__(self, errors: List[str]):
        self.errors = errors
        super().__init__("；".join(errors))


# ---------------------------------------------------------------------------
# 解析工具：严格类型 + 中文定位报错
# ---------------------------------------------------------------------------

def _req(d: dict, key: str, path: str, errors: List[str]) -> Any:
    if key not in d:
        errors.append("%s: 缺少必填字段「%s」" % (path, key))
        return None
    return d[key]


def _str(value: Any, path: str, errors: List[str]) -> Optional[str]:
    if not isinstance(value, str) or not value.strip():
        errors.append("%s: 应为非空字符串，实际为 %r" % (path, value))
        return None
    return value


def _num(value: Any, path: str, errors: List[str],
         min_value: Optional[float] = None,
         max_value: Optional[float] = None) -> Optional[float]:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        errors.append("%s: 应为数值，实际为 %r" % (path, value))
        return None
    v = float(value)
    if min_value is not None and v < min_value:
        errors.append("%s: 应 ≥ %s，实际为 %s" % (path, min_value, v))
        return None
    if max_value is not None and v > max_value:
        errors.append("%s: 应 ≤ %s，实际为 %s" % (path, max_value, v))
        return None
    return v


def _bool(value: Any, path: str, errors: List[str]) -> Optional[bool]:
    if not isinstance(value, bool):
        errors.append("%s: 应为布尔值，实际为 %r" % (path, value))
        return None
    return value


def _phases(value: Any, path: str, errors: List[str],
            allow_empty: bool = False) -> Optional[List[str]]:
    if not isinstance(value, list) or not all(isinstance(p, str) for p in value):
        errors.append("%s: 相别应为字符串列表，实际为 %r" % (path, value))
        return None
    if not allow_empty and not value:
        errors.append("%s: 相别不能为空" % path)
        return None
    for p in value:
        if p not in PHASES:
            errors.append("%s: 非法相别「%s」（应为 A/B/C）" % (path, p))
    if len(set(value)) != len(value):
        errors.append("%s: 相别重复 %r" % (path, value))
        return None
    return list(value)


def _phase_map(value: Any, path: str, errors: List[str],
               min_value: float = 0.0) -> Optional[Dict[str, float]]:
    """分相数值表，如 {"A": 1.0, "B": 1.0, "C": 1.0}。键须为合法相别。"""
    if not isinstance(value, dict):
        errors.append("%s: 应为按相字典（A/B/C → 数值），实际为 %r" % (path, value))
        return None
    out: Dict[str, float] = {}
    for k, v in value.items():
        if k not in PHASES:
            errors.append("%s: 非法相别键「%s」（应为 A/B/C）" % (path, k))
            continue
        num = _num(v, "%s[%s]" % (path, k), errors, min_value=min_value)
        if num is not None:
            out[k] = num
    return out


# ---------------------------------------------------------------------------
# 数据类
# ---------------------------------------------------------------------------

@dataclass
class Slack:
    node: str
    v_pu: float = 1.0


@dataclass
class NetworkBase:
    v_base_kv: float = 12.66
    frequency_hz: float = 50.0
    s_base_kva: float = 1000.0
    slack: Slack = field(default_factory=lambda: Slack("1"))
    v_min_pu: float = 0.95
    v_max_pu: float = 1.05


@dataclass
class Node:
    id: str
    phases: List[str] = field(default_factory=lambda: list(PHASES))
    name: str = ""
    x: Optional[float] = None
    y: Optional[float] = None
    load_kw: Dict[str, float] = field(default_factory=dict)
    load_kvar: Dict[str, float] = field(default_factory=dict)


@dataclass
class LineType:
    id: str
    r_ohm_per_km: Dict[str, float] = field(default_factory=dict)
    x_ohm_per_km: Dict[str, float] = field(default_factory=dict)
    ampacity_a: float = 0.0


@dataclass
class Line:
    id: str
    from_node: str
    to_node: str
    phases: List[str] = field(default_factory=lambda: list(PHASES))
    length_km: float = 0.0
    r_ohm_per_km: Dict[str, float] = field(default_factory=dict)
    x_ohm_per_km: Dict[str, float] = field(default_factory=dict)
    ampacity_a: float = 0.0
    line_type: str = ""


@dataclass
class PV:
    id: str
    node: str
    phases: List[str] = field(default_factory=lambda: list(PHASES))
    capacity_kw: float = 0.0
    controllable: bool = True


@dataclass
class Curves:
    load: List[float] = field(default_factory=list)
    pv: List[float] = field(default_factory=list)


@dataclass
class CommEdge:
    from_agent: str
    to_agent: str
    weight: float = 1.0


@dataclass
class CommGraph:
    edges: List[CommEdge] = field(default_factory=list)


@dataclass
class AlgoParams:
    alpha: float = 1.0
    beta: float = 1.0
    gamma: float = 1.0
    delta: float = 0.0005
    max_iter: int = 60
    pf_tol: float = 1e-4
    pf_max_iter: int = 100


@dataclass
class Project:
    schema_version: int
    name: str
    base: NetworkBase
    nodes: List[Node]
    lines: List[Line]
    line_types: List[LineType] = field(default_factory=list)
    pvs: List[PV] = field(default_factory=list)
    curves: Optional[Curves] = None
    comm_graph: CommGraph = field(default_factory=CommGraph)
    algo: AlgoParams = field(default_factory=AlgoParams)


# ---------------------------------------------------------------------------
# from_dict（严格解析，收集全部错误）
# ---------------------------------------------------------------------------

def _parse_base(d: Any, errors: List[str]) -> NetworkBase:
    path = "base"
    if not isinstance(d, dict):
        errors.append("%s: 应为对象" % path)
        return NetworkBase()
    v = _num(_req(d, "v_base_kv", path, errors), path + ".v_base_kv", errors, min_value=0.01)
    f = _num(_req(d, "frequency_hz", path, errors), path + ".frequency_hz", errors, min_value=0.01)
    s = _num(_req(d, "s_base_kva", path, errors), path + ".s_base_kva", errors, min_value=0.01)
    vmin = _num(d.get("v_min_pu", 0.95), path + ".v_min_pu", errors, min_value=0.5, max_value=1.2)
    vmax = _num(d.get("v_max_pu", 1.05), path + ".v_max_pu", errors, min_value=0.5, max_value=1.2)
    slack = d.get("slack", {})
    if not isinstance(slack, dict):
        errors.append("base.slack: 应为对象")
        sl = Slack("")
    else:
        sl_node = _str(_req(slack, "node", "base.slack", errors), "base.slack.node", errors)
        sl_v = _num(slack.get("v_pu", 1.0), "base.slack.v_pu", errors, min_value=0.8, max_value=1.2)
        sl = Slack(sl_node or "", sl_v if sl_v is not None else 1.0)
    if vmin is not None and vmax is not None and vmin >= vmax:
        errors.append("base: v_min_pu（%s）应小于 v_max_pu（%s）" % (vmin, vmax))
    return NetworkBase(
        v_base_kv=v if v is not None else 12.66,
        frequency_hz=f if f is not None else 50.0,
        s_base_kva=s if s is not None else 1000.0,
        slack=sl,
        v_min_pu=vmin if vmin is not None else 0.95,
        v_max_pu=vmax if vmax is not None else 1.05,
    )


def _parse_node(d: Any, idx: int, errors: List[str]) -> Node:
    path = "nodes[%d]" % idx
    if not isinstance(d, dict):
        errors.append("%s: 应为对象" % path)
        return Node(id="")
    nid = _str(_req(d, "id", path, errors), path + ".id", errors) or ""
    ph = _phases(d.get("phases", list(PHASES)), path + ".phases", errors) or list(PHASES)
    name = d.get("name", "")
    if not isinstance(name, str):
        errors.append("%s.name: 应为字符串" % path)
        name = ""
    x = _num(d["x"], path + ".x", errors) if d.get("x") is not None else None
    y = _num(d["y"], path + ".y", errors) if d.get("y") is not None else None
    lkw = _phase_map(d.get("load_kw", {}), path + ".load_kw", errors) or {}
    lkvar = _phase_map(d.get("load_kvar", {}), path + ".load_kvar", errors) or {}
    return Node(id=nid, phases=ph, name=name, x=x, y=y, load_kw=lkw, load_kvar=lkvar)


def _parse_imp(d: Any, path: str, errors: List[str],
               required: bool) -> Tuple[Dict[str, float], Dict[str, float], float]:
    r = _phase_map(d.get("r_ohm_per_km"), path + ".r_ohm_per_km", errors,
                   min_value=0.0) if d.get("r_ohm_per_km") is not None else None
    x = _phase_map(d.get("x_ohm_per_km"), path + ".x_ohm_per_km", errors,
                   min_value=0.0) if d.get("x_ohm_per_km") is not None else None
    amp = _num(d.get("ampacity_a", 0.0), path + ".ampacity_a", errors, min_value=0.0)
    if required and r is None and x is None:
        errors.append("%s: 须给出 r_ohm_per_km / x_ohm_per_km 或引用 line_type" % path)
    return (r or {}, x or {}, amp if amp is not None else 0.0)


def _parse_line(d: Any, idx: int, errors: List[str]) -> Line:
    path = "lines[%d]" % idx
    if not isinstance(d, dict):
        errors.append("%s: 应为对象" % path)
        return Line(id="", from_node="", to_node="")
    lid = _str(_req(d, "id", path, errors), path + ".id", errors) or ""
    frm = _str(_req(d, "from", path, errors), path + ".from", errors) or ""
    to = _str(_req(d, "to", path, errors), path + ".to", errors) or ""
    ph = _phases(d.get("phases", list(PHASES)), path + ".phases", errors) or list(PHASES)
    length = _num(_req(d, "length_km", path, errors), path + ".length_km", errors,
                  min_value=1e-9)
    r, x, amp = _parse_imp(d, path, errors, required=True)
    lt = d.get("line_type", "")
    if lt and not isinstance(lt, str):
        errors.append("%s.line_type: 应为字符串" % path)
        lt = ""
    return Line(id=lid, from_node=frm, to_node=to, phases=ph,
                length_km=length if length is not None else 0.0,
                r_ohm_per_km=r, x_ohm_per_km=x,
                ampacity_a=amp, line_type=lt or "")


def _parse_line_type(d: Any, idx: int, errors: List[str]) -> LineType:
    path = "line_types[%d]" % idx
    if not isinstance(d, dict):
        errors.append("%s: 应为对象" % path)
        return LineType(id="")
    tid = _str(_req(d, "id", path, errors), path + ".id", errors) or ""
    r, x, amp = _parse_imp(d, path, errors, required=False)
    return LineType(id=tid, r_ohm_per_km=r, x_ohm_per_km=x,
                    ampacity_a=amp)


def _parse_pv(d: Any, idx: int, errors: List[str]) -> PV:
    path = "pvs[%d]" % idx
    if not isinstance(d, dict):
        errors.append("%s: 应为对象" % path)
        return PV(id="", node="")
    pid = _str(_req(d, "id", path, errors), path + ".id", errors) or ""
    node = _str(_req(d, "node", path, errors), path + ".node", errors) or ""
    ph = _phases(d.get("phases", list(PHASES)), path + ".phases", errors)
    cap = _num(_req(d, "capacity_kw", path, errors), path + ".capacity_kw", errors,
               min_value=0.0)
    ctrl = _bool(d.get("controllable", True), path + ".controllable", errors)
    return PV(id=pid, node=node, phases=ph or [],
              capacity_kw=cap if cap is not None else 0.0,
              controllable=ctrl if ctrl is not None else True)


def _parse_curves(d: Any, errors: List[str]) -> Curves:
    path = "curves"
    if not isinstance(d, dict):
        errors.append("%s: 应为对象" % path)
        return Curves()
    out = Curves()
    for key in ("load", "pv"):
        arr = d.get(key)
        if arr is None:
            continue
        p = "%s.%s" % (path, key)
        if not isinstance(arr, list) or not all(
                isinstance(v, (int, float)) and not isinstance(v, bool) for v in arr):
            errors.append("%s: 应为 24 个非负数值的列表" % p)
            continue
        if len(arr) != 24:
            errors.append("%s: 应为 24 个整点值，实际 %d 个" % (p, len(arr)))
            continue
        vals = [float(v) for v in arr]
        if any(v < 0 for v in vals):
            errors.append("%s: 存在负值（曲线值应 ≥ 0）" % p)
            continue
        setattr(out, "load" if key == "load" else "pv", vals)
    return out


def _parse_comm(d: Any, errors: List[str]) -> CommGraph:
    path = "comm_graph"
    if not isinstance(d, dict):
        errors.append("%s: 应为对象" % path)
        return CommGraph()
    edges = d.get("edges", [])
    if not isinstance(edges, list):
        errors.append("%s.edges: 应为列表" % path)
        return CommGraph()
    out = []
    for i, e in enumerate(edges):
        p = "%s.edges[%d]" % (path, i)
        if not isinstance(e, dict):
            errors.append("%s: 应为对象" % p)
            continue
        frm = _str(_req(e, "from", p, errors), p + ".from", errors) or ""
        to = _str(_req(e, "to", p, errors), p + ".to", errors) or ""
        w = _num(e.get("weight", 1.0), p + ".weight", errors)
        out.append(CommEdge(from_agent=frm, to_agent=to, weight=w if w is not None else 1.0))
    return CommGraph(edges=out)


def _parse_algo(d: Any, errors: List[str]) -> AlgoParams:
    path = "algo"
    if not isinstance(d, dict):
        errors.append("%s: 应为对象" % path)
        return AlgoParams()
    a = _num(d.get("alpha", 1.0), path + ".alpha", errors, min_value=0.0)
    b = _num(d.get("beta", 1.0), path + ".beta", errors, min_value=0.0)
    g = _num(d.get("gamma", 1.0), path + ".gamma", errors, min_value=0.0)
    delta = _num(d.get("delta", 0.0005), path + ".delta", errors, min_value=1e-9)
    mi = _num(d.get("max_iter", 60), path + ".max_iter", errors, min_value=1)
    pt = _num(d.get("pf_tol", 1e-4), path + ".pf_tol", errors, min_value=1e-12)
    pm = _num(d.get("pf_max_iter", 100), path + ".pf_max_iter", errors, min_value=1)
    return AlgoParams(
        alpha=a if a is not None else 1.0,
        beta=b if b is not None else 1.0,
        gamma=g if g is not None else 1.0,
        delta=delta if delta is not None else 0.0005,
        max_iter=int(mi) if mi is not None else 60,
        pf_tol=pt if pt is not None else 1e-4,
        pf_max_iter=int(pm) if pm is not None else 100,
    )


def project_from_dict(data: Any) -> Project:
    """把项目 dict 解析为 Project；任何结构错误抛 SchemaError（汇总全部）。"""
    errors: List[str] = []
    if not isinstance(data, dict):
        raise SchemaError(["项目根: 应为 JSON 对象"])
    ver = data.get("schema_version")
    if ver != SCHEMA_VERSION:
        errors.append("schema_version: 应为 %d，实际为 %r" % (SCHEMA_VERSION, ver))
    name = _str(_req(data, "name", "项目", errors), "name", errors) or ""
    base = _parse_base(_req(data, "base", "项目", errors) or {}, errors)
    nodes_raw = data.get("nodes")
    if not isinstance(nodes_raw, list) or not nodes_raw:
        errors.append("nodes: 应为非空列表")
        nodes_raw = []
    nodes = [_parse_node(d, i, errors) for i, d in enumerate(nodes_raw)]
    lines_raw = data.get("lines")
    if not isinstance(lines_raw, list):
        errors.append("lines: 应为列表")
        lines_raw = []
    lines = [_parse_line(d, i, errors) for i, d in enumerate(lines_raw)]
    lt_raw = data.get("line_types", [])
    if not isinstance(lt_raw, list):
        errors.append("line_types: 应为列表")
        lt_raw = []
    line_types = [_parse_line_type(d, i, errors) for i, d in enumerate(lt_raw)]
    pv_raw = data.get("pvs", [])
    if not isinstance(pv_raw, list):
        errors.append("pvs: 应为列表")
        pv_raw = []
    pvs = [_parse_pv(d, i, errors) for i, d in enumerate(pv_raw)]
    curves = _parse_curves(data.get("curves", {}), errors) if data.get("curves") else None
    comm = _parse_comm(data.get("comm_graph", {}), errors)
    algo = _parse_algo(data.get("algo", {}), errors)
    if errors:
        raise SchemaError(errors)
    return Project(schema_version=SCHEMA_VERSION, name=name, base=base, nodes=nodes,
                   lines=lines, line_types=line_types, pvs=pvs, curves=curves,
                   comm_graph=comm, algo=algo)


def project_from_json(text: str) -> Project:
    import json
    try:
        data = json.loads(text)
    except ValueError as exc:
        raise SchemaError(["JSON 语法错误: %s" % exc])
    return project_from_dict(data)


# ---------------------------------------------------------------------------
# to_dict（全字段显式写出，保证 保存→加载→再保存 内容等价）
# ---------------------------------------------------------------------------

def _dump_phase_map(m: Dict[str, float]) -> Dict[str, float]:
    return dict(m)


def project_to_dict(p: Project) -> dict:
    return {
        "schema_version": p.schema_version,
        "name": p.name,
        "base": {
            "v_base_kv": p.base.v_base_kv,
            "frequency_hz": p.base.frequency_hz,
            "s_base_kva": p.base.s_base_kva,
            "slack": {"node": p.base.slack.node, "v_pu": p.base.slack.v_pu},
            "v_min_pu": p.base.v_min_pu,
            "v_max_pu": p.base.v_max_pu,
        },
        "nodes": [
            {
                "id": n.id,
                "phases": list(n.phases),
                "name": n.name,
                "x": n.x,
                "y": n.y,
                "load_kw": _dump_phase_map(n.load_kw),
                "load_kvar": _dump_phase_map(n.load_kvar),
            }
            for n in p.nodes
        ],
        "lines": [
            {
                "id": ln.id,
                "from": ln.from_node,
                "to": ln.to_node,
                "phases": list(ln.phases),
                "length_km": ln.length_km,
                "r_ohm_per_km": _dump_phase_map(ln.r_ohm_per_km),
                "x_ohm_per_km": _dump_phase_map(ln.x_ohm_per_km),
                "ampacity_a": ln.ampacity_a,
                "line_type": ln.line_type,
            }
            for ln in p.lines
        ],
        "line_types": [
            {
                "id": t.id,
                "r_ohm_per_km": _dump_phase_map(t.r_ohm_per_km),
                "x_ohm_per_km": _dump_phase_map(t.x_ohm_per_km),
                "ampacity_a": t.ampacity_a,
            }
            for t in p.line_types
        ],
        "pvs": [
            {
                "id": v.id,
                "node": v.node,
                "phases": list(v.phases),
                "capacity_kw": v.capacity_kw,
                "controllable": v.controllable,
            }
            for v in p.pvs
        ],
        "curves": None if p.curves is None else {
            "load": list(p.curves.load),
            "pv": list(p.curves.pv),
        },
        "comm_graph": {
            "edges": [
                {"from": e.from_agent, "to": e.to_agent, "weight": e.weight}
                for e in p.comm_graph.edges
            ]
        },
        "algo": {
            "alpha": p.algo.alpha,
            "beta": p.algo.beta,
            "gamma": p.algo.gamma,
            "delta": p.algo.delta,
            "max_iter": p.algo.max_iter,
            "pf_tol": p.algo.pf_tol,
            "pf_max_iter": p.algo.pf_max_iter,
        },
    }


def project_to_json(p: Project, indent: int = 2) -> str:
    import json
    return json.dumps(project_to_dict(p), ensure_ascii=False, indent=indent)


def default_project() -> Project:
    """最小合法项目（单节点 + 单线路 + 两节点）。"""
    return Project(
        schema_version=SCHEMA_VERSION,
        name="新建项目",
        base=NetworkBase(),
        nodes=[Node(id="1"), Node(id="2")],
        lines=[Line(id="L1", from_node="1", to_node="2", length_km=1.0,
                    r_ohm_per_km={"A": 0.3, "B": 0.3, "C": 0.3},
                    x_ohm_per_km={"A": 0.35, "B": 0.35, "C": 0.35},
                    ampacity_a=400.0)],
        pvs=[PV(id="PV1", node="2", phases=["A"], capacity_kw=50.0)],
    )
