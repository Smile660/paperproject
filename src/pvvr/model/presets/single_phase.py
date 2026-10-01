"""小型纯单相示例预设：10 kV、6 节点放射馈线，2 台单相光伏。

用于纯单相模式快速实验与测试（spec FR-1 内置预设之二）。
"""

_NODES = [
    ("1", 0.0, 0.0),
    ("2", 40.0, 15.0),
    ("3", 60.0, 25.0),
    ("4", 50.0, 20.0),
    ("5", 30.0, 10.0),
    ("6", 80.0, 30.0),
]

_LINES = [
    ("L1", "1", "2", 0.60, 0.35),
    ("L2", "2", "3", 0.55, 0.32),
    ("L3", "3", "4", 0.45, 0.28),
    ("L4", "2", "5", 0.70, 0.40),
    ("L5", "5", "6", 0.65, 0.38),
]

_LOAD_CURVE = [0.42, 0.40, 0.38, 0.37, 0.38, 0.42, 0.50, 0.60, 0.68, 0.72,
               0.76, 0.80, 0.82, 0.80, 0.76, 0.72, 0.70, 0.68, 0.66, 0.64,
               0.62, 0.56, 0.50, 0.46]
_PV_CURVE = [0.0, 0.0, 0.0, 0.0, 0.0, 0.05, 0.15, 0.35, 0.60, 0.80,
             0.92, 1.00, 1.00, 0.98, 0.90, 0.72, 0.45, 0.20, 0.05, 0.0,
             0.0, 0.0, 0.0, 0.0]


def build_dict() -> dict:
    nodes = []
    for nid, p, q in _NODES:
        nodes.append({
            "id": nid,
            "phases": ["A"],
            "name": "节点 %s" % nid,
            "x": None,
            "y": None,
            "load_kw": {"A": p} if p else {},
            "load_kvar": {"A": q} if q else {},
        })
    lines = []
    for lid, f, t, r, x in _LINES:
        lines.append({
            "id": lid,
            "from": f,
            "to": t,
            "phases": ["A"],
            "length_km": 1.0,
            "r_ohm_per_km": {"A": r},
            "x_ohm_per_km": {"A": x},
            "ampacity_a": 200.0,
            "line_type": "",
        })
    return {
        "schema_version": 1,
        "name": "小型纯单相示例",
        "base": {
            "v_base_kv": 10.0,
            "frequency_hz": 50.0,
            "s_base_kva": 1000.0,
            "slack": {"node": "1", "v_pu": 1.0},
            "v_min_pu": 0.95,
            "v_max_pu": 1.05,
        },
        "nodes": nodes,
        "lines": lines,
        "line_types": [],
        "pvs": [
            {"id": "PV1", "node": "4", "phases": ["A"], "capacity_kw": 250.0,
             "controllable": True},
            {"id": "PV2", "node": "6", "phases": ["A"], "capacity_kw": 200.0,
             "controllable": True},
        ],
        "curves": {"load": _LOAD_CURVE, "pv": _PV_CURVE},
        "comm_graph": {"edges": []},
        "algo": {},
    }
