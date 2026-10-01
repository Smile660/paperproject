"""24h 时序仿真（无控制基线内核，spec FR-2/FR-4 之运行方式）。

逐小时独立求解（无跨断面约束），光伏按可用出力满发（无控制）。
控制闭环（票 04）在此循环之上逐断面接入。
"""

from dataclasses import dataclass, field
from typing import Callable, List, Optional

from pvvr.engine.powerflow import SnapshotResult, solve_snapshot
from pvvr.engine.snapshot import SnapshotSpec, pv_available, spec_at_hour
from pvvr.model.schema import Project


@dataclass
class HourRecord:
    hour: Optional[int]
    spec: SnapshotSpec
    result: SnapshotResult
    pv_kw: dict = field(default_factory=dict)   # 各光伏实际出力（无控制=可用）


@dataclass
class DayResult:
    records: List[HourRecord] = field(default_factory=list)
    project_name: str = ""

    def hour_series(self):
        return [r.hour for r in self.records]

    def max_v_series(self):
        return [r.result.max_v()[0] for r in self.records]

    def min_v_series(self):
        return [r.result.min_v()[0] for r in self.records]


def run_hour(project: Project, hour: Optional[int] = None,
             load_scale: Optional[float] = None,
             pv_factor: Optional[float] = None,
             pv_kw: Optional[dict] = None,
             solver: Callable = solve_snapshot) -> HourRecord:
    """求解一个断面。

    hour 给定 → 按统一曲线取值；load_scale/pv_factor 给定 → 手填断面。
    pv_kw 可显式指定各光伏出力（票 04 控制用），缺省按可用出力满发。
    """
    if hour is not None:
        spec = spec_at_hour(project, hour)
        if load_scale is not None:
            spec.load_scale = load_scale
        if pv_factor is not None:
            spec.pv_factor = pv_factor
    elif load_scale is not None or pv_factor is not None:
        from pvvr.engine.snapshot import spec_manual
        spec = spec_manual(load_scale if load_scale is not None else 1.0,
                           pv_factor if pv_factor is not None else 1.0)
    else:
        spec = SnapshotSpec(hour=None, load_scale=1.0, pv_factor=1.0)
    actual = pv_kw if pv_kw is not None else pv_available(project, spec)
    result = solver(project, pv_kw=actual, load_scale=spec.load_scale)
    return HourRecord(hour=hour, spec=spec, result=result, pv_kw=dict(actual))


def run_day(project: Project, solver: Callable = solve_snapshot) -> DayResult:
    """典型日 24 断面逐小时仿真（无控制：光伏满发）。"""
    day = DayResult(project_name=project.name)
    for hour in range(24):
        day.records.append(run_hour(project, hour=hour, solver=solver))
    return day
