"""`pvvr run` 子命令：无界面运行仿真（spec FR-8）。

票 02 交付：快照模式（额定负荷、光伏可用出力满发），输出控制台摘要 +
电压/线路负载率 CSV。票 03 扩展 24h；票 04 扩展控制闭环。
"""

import argparse
import time
from datetime import datetime
from pathlib import Path
from typing import List

from pvvr import settings as app_settings
from pvvr.model import schema as sch
from pvvr.model import validate as vcheck
from pvvr.model.presets import PRESETS


def _load(path_str: str) -> sch.Project:
    path = Path(path_str)
    if not path.exists():
        raise SystemExit("文件不存在：%s" % path)
    project = sch.project_from_json(path.read_text(encoding="utf-8"))
    errors = vcheck.validate_project(project)
    if errors:
        print("领域校验未通过（%d 处），已停止运行：" % len(errors))
        for e in errors:
            print("  - %s" % e)
        raise SystemExit(1)
    return project


def _write_csv(path: Path, header: List[str], rows: List[List[object]]) -> None:
    import csv
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(rows)


def _control_outputs(run_dir, day, project):
    """公平二分法运行的削减/迭代/摘要 CSV 与轨迹图（FR-4 输出项）。"""
    _write_csv(run_dir / "curtailment.csv",
               ["hour", "pv", "avail_kw", "curtail_kw", "output_kw", "weight",
                "saturated"],
               [[r.hour, pid, "%.6f" % r.avail[pid], "%.6f" % r.curtail.get(pid, 0.0),
                 "%.6f" % r.output.get(pid, 0.0),
                 "%.6f" % r.weights.get(pid, 0.0),
                 1 if pid in r.saturated else 0]
                for r in day.records for pid in sorted(r.avail)])
    _write_csv(run_dir / "iterations.csv",
               ["hour", "k", "lo", "hi", "C", "max_v"],
               [[r.hour, it["k"], "%.6f" % it["lo"], "%.6f" % it["hi"],
                 "%.6f" % it["C"], "%.6f" % it["max_v"]]
                for r in day.records for it in r.iterations])
    _write_csv(run_dir / "summary.csv",
               ["hour", "status", "C_star", "max_v", "min_v", "worst_node"],
               [[r.hour, r.status, "%.6f" % r.c_star,
                 "%.6f" % r.result.max_v()[0], "%.6f" % r.result.min_v()[0],
                 "%s%s" % r.worst_node] for r in day.records])
    _write_csv(run_dir / "voltages.csv",
               ["hour", "node", "phase", "v_pu"],
               [[r.hour, n, p, "%.6f" % v]
                for r in day.records
                for (n, p), v in sorted(r.result.voltages_pu.items())])
    from pvvr.engine.plot import plot_voltage_trajectory
    plot_voltage_trajectory(day, run_dir / "voltage_trajectory.png",
                            project.base.v_min_pu, project.base.v_max_pu,
                            title="24h 电压轨迹（公平二分法控制后）")


def run_command(args) -> int:
    if args.engine == "matlab":
        print("MATLAB 引擎尚未交付（票据 10）；当前请使用默认 OpenDSS 引擎。")
        return 2
    from pvvr.engine.powerflow import PowerflowError
    from pvvr.engine.simulation import run_day, run_hour

    project = _load(args.project)
    out_dir = Path(args.out) if args.out else Path(app_settings.load_settings()["output_dir"])
    run_id = "%s_%s" % (datetime.now().strftime("%Y%m%d_%H%M%S"), project.name or "run")
    run_dir = out_dir / run_id
    started = time.perf_counter()
    try:
        if args.control == "fair":
            from pvvr.engine.control import (control_day, control_snapshot_now)
            if args.mode == "24h":
                day = control_day(project)
                run_dir.mkdir(parents=True, exist_ok=True)
                _control_outputs(run_dir, day, project)
                elapsed = time.perf_counter() - started
                vmax = max(day.max_v_series())
                n_ctrl = sum(1 for r in day.records if r.status != "无需控制")
                print("项目「%s」24h 公平二分法控制完成（%.1f s）"
                      % (project.name, elapsed))
                print("  控制断面 %d/24；全天最高 %.4f pu（上限 %.3g）；JFI = %.4f"
                      % (n_ctrl, vmax, project.base.v_max_pu, day.jfi()))
                for r in day.records:
                    if r.status not in ("无需控制", "收敛"):
                        print("  注意：h=%s 状态「%s」" % (r.hour, r.status))
                print("结果已写入：%s" % run_dir)
                return 0
            rec = control_snapshot_now(project, hour=args.t)
            run_dir.mkdir(parents=True, exist_ok=True)
            _write_csv(run_dir / "curtailment.csv",
                       ["pv", "avail_kw", "curtail_kw", "output_kw", "weight",
                        "saturated"],
                       [[pid, "%.6f" % rec.avail[pid],
                         "%.6f" % rec.curtail.get(pid, 0.0),
                         "%.6f" % rec.output.get(pid, 0.0),
                         "%.6f" % rec.weights.get(pid, 0.0),
                         1 if pid in rec.saturated else 0]
                        for pid in sorted(rec.avail)])
            _write_csv(run_dir / "iterations.csv",
                       ["k", "lo", "hi", "C", "max_v"],
                       [[it["k"], "%.6f" % it["lo"], "%.6f" % it["hi"],
                         "%.6f" % it["C"], "%.6f" % it["max_v"]]
                        for it in rec.iterations])
            hour_tag = "第 %d 时断面" % args.t if args.t is not None else "额定断面"
            print("项目「%s」快照公平二分法控制完成（%s）" % (project.name, hour_tag))
            print("  状态「%s」；C* = %.2f kW；控制后 maxV = %.4f pu"
                  % (rec.status, rec.c_star, rec.result.max_v()[0]))
            print("结果已写入：%s" % run_dir)
            return 0
        if args.mode == "24h":
            day = run_day(project)
            elapsed = time.perf_counter() - started
            run_dir.mkdir(parents=True, exist_ok=True)
            _write_csv(run_dir / "summary.csv",
                       ["hour", "load_scale", "pv_factor", "max_v", "min_v",
                        "max_at", "min_at"],
                       [[r.hour, "%.6f" % r.spec.load_scale,
                         "%.6f" % r.spec.pv_factor,
                         "%.6f" % r.result.max_v()[0], "%.6f" % r.result.min_v()[0],
                         "%s%s" % r.result.max_v()[1], "%s%s" % r.result.min_v()[1]]
                        for r in day.records])
            _write_csv(run_dir / "voltages.csv",
                       ["hour", "node", "phase", "v_pu"],
                       [[r.hour, n, p, "%.6f" % v]
                        for r in day.records
                        for (n, p), v in sorted(r.result.voltages_pu.items())])
            from pvvr.engine.plot import plot_voltage_trajectory
            plot_voltage_trajectory(day, run_dir / "voltage_trajectory.png",
                                    project.base.v_min_pu, project.base.v_max_pu)
            vmax = max(day.max_v_series())
            vmin = min(day.min_v_series())
            over = sum(1 for r in day.records
                       if r.result.violations(project.base.v_max_pu))
            print("项目「%s」24h 仿真完成（24 断面，%.1f s）" % (project.name, elapsed))
            print("  全天最高 %.4f pu，最低 %.4f pu；过电压断面 %d/24" % (vmax, vmin, over))
            print("结果已写入：%s" % run_dir)
            return 0
        # 快照模式
        rec = run_hour(project, hour=args.t)
        result = rec.result
    except PowerflowError as exc:
        print("运行失败：%s" % exc)
        return 1
    elapsed = time.perf_counter() - started

    vmax, (nmax, pmax) = result.max_v()
    vmin, (nmin, pmin) = result.min_v()
    hour_tag = "第 %d 时断面" % args.t if args.t is not None else "额定断面"
    print("项目「%s」快照潮流求解完成（%s，%.1f ms）"
          % (project.name, hour_tag, elapsed * 1000.0))
    print("  最高电压 %.4f pu @ 节点 %s %s 相；最低电压 %.4f pu @ 节点 %s %s 相"
          % (vmax, nmax, pmax, vmin, nmin, pmin))
    viol = result.violations(project.base.v_max_pu)
    if viol:
        print("  过电压越限（> %.3g pu）：%d 处，最高处 %s %s 相 %.4f pu"
              % (project.base.v_max_pu, len(viol), viol[-1][0], viol[-1][1], viol[-1][2]))
    else:
        print("  无过电压越限（上限 %.3g pu）" % project.base.v_max_pu)
    under = result.under_voltages(project.base.v_min_pu)
    if under:
        print("  低电压记录（< %.3g pu，仅报告不控制）：%d 处，最低处 %s %s 相 %.4f pu"
              % (project.base.v_min_pu, len(under), under[0][0], under[0][1], under[0][2]))

    run_dir.mkdir(parents=True, exist_ok=True)
    volt_file = run_dir / "voltages.csv"
    _write_csv(volt_file, ["node", "phase", "v_pu"],
               [[n, p, "%.6f" % v] for (n, p), v in sorted(result.voltages_pu.items())])
    line_file = run_dir / "line_loading.csv"
    _write_csv(line_file, ["line", "phase", "loading"],
               [[lid, p, "%.4f" % r] for lid, phs in sorted(result.line_loadings.items())
                for p, r in sorted(phs.items())])
    print("结果已写入：%s" % run_dir)
    return 0
