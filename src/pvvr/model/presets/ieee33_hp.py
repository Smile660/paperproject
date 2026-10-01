"""IEEE 33 + 高渗透光伏过电压场景预设（验收 2 / ET-3 / 演示用）。

在 ieee33 基础上于馈线远端布置三相光伏，正午大发时段形成反向潮流与
过电压，公平二分法控制可将其压回 Vmax 以内。
"""

from typing import Dict, List, Tuple

from pvvr.model.presets import ieee33

# 光伏布置：(节点, 额定容量 kW)——集中于三条分支末端（远端调压能力差）
_PV_PLACEMENT: List[Tuple[str, float]] = [
    ("17", 500.0), ("18", 600.0),
    ("21", 400.0), ("22", 500.0),
    ("24", 500.0), ("25", 600.0),
    ("32", 400.0), ("33", 500.0),
]


def build_dict() -> dict:
    data = ieee33.build_dict()
    data["name"] = "IEEE 33 + 高渗透光伏（过电压场景）"
    pvs = []
    for i, (node, cap) in enumerate(_PV_PLACEMENT, start=1):
        pvs.append({
            "id": "PV%d" % i,
            "node": node,
            "phases": ["A", "B", "C"],
            "capacity_kw": cap,
            "controllable": True,
        })
    data["pvs"] = pvs
    return data
