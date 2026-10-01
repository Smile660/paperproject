"""断面生成：统一曲线 → 该小时的负荷缩放与光伏可用出力（spec FR-2）。

约定：负荷 P(t)/Q(t) = 负荷曲线值 × 各自峰值；光伏可用出力 = 光伏曲线值 ×
额定容量（曲线峰值 = 1）。项目未配置曲线时按峰值 1.0（额定）运行。
"""

from dataclasses import dataclass
from typing import Dict, Optional

from pvvr.model.schema import Project


@dataclass
class SnapshotSpec:
    hour: Optional[int]          # 断面对应整点（手填断面为 None）
    load_scale: float = 1.0      # 统一负荷曲线值
    pv_factor: float = 1.0       # 统一光伏曲线值


def spec_at_hour(project: Project, hour: int) -> SnapshotSpec:
    if not 0 <= hour <= 23:
        raise ValueError("小时须在 0–23，实际 %r" % hour)
    if project.curves is None:
        return SnapshotSpec(hour=hour, load_scale=1.0, pv_factor=1.0)
    return SnapshotSpec(hour=hour,
                        load_scale=float(project.curves.load[hour]),
                        pv_factor=float(project.curves.pv[hour]))


def spec_manual(load_scale: float = 1.0, pv_factor: float = 1.0) -> SnapshotSpec:
    """手填断面值（快照模式不经曲线）。"""
    if load_scale < 0 or pv_factor < 0:
        raise ValueError("断面缩放值不能为负")
    return SnapshotSpec(hour=None, load_scale=load_scale, pv_factor=pv_factor)


def pv_available(project: Project, spec: SnapshotSpec) -> Dict[str, float]:
    """各光伏当前断面可用出力（kW）＝额定容量 × 曲线值。"""
    return {v.id: v.capacity_kw * spec.pv_factor for v in project.pvs}
