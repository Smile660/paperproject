"""`pvvr compare` 子命令：一键三方式对比实验（spec FR-6）。"""

import time
from datetime import datetime
from pathlib import Path

from pvvr import settings as app_settings
from pvvr.cli_run import _load, _write_csv


def compare_command(args) -> int:
    from pvvr.engine.baselines import run_comparison
    from pvvr.engine.plot import (plot_curtailment_comparison,
                                  plot_mode_comparison)

    project = _load(args.project)
    started = time.perf_counter()
    comparison = run_comparison(project)
    elapsed = time.perf_counter() - started

    out_dir = Path(args.out) if args.out else Path(app_settings.load_settings()["output_dir"])
    run_id = "%s_%s_对比" % (datetime.now().strftime("%Y%m%d_%H%M%S"),
                             project.name or "run")
    run_dir = out_dir / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    _write_csv(run_dir / "metrics.csv",
               ["方式", "总削减电量/kWh", "峰值削减/kW", "峰值时刻/h",
                "最大电压/pu", "最小电压/pu", "外层迭代总数", "耗时/s", "全天安全"],
               [[m.name, "%.2f" % m.total_curtail_kwh, "%.2f" % m.peak_curtail_kw,
                 m.peak_hour if m.peak_hour is not None else "",
                 "%.4f" % m.max_v, "%.4f" % m.min_v, m.total_iterations,
                 "%.2f" % m.elapsed_s, "是" if m.all_safe else "否"]
                for m in comparison.metrics])
    # 逐方式削减明细（无控制恒为 0，仅导出两个控制方式）
    for records, prefix in ((comparison.central, "central"),
                            (comparison.fair.records, "fair")):
        _write_csv(run_dir / ("%s_curtailment.csv" % prefix),
                   ["hour", "pv", "curtail_kw"],
                   [[r.hour, pid, "%.6f" % c]
                    for r in records for pid, c in sorted(r.curtail.items())])
    plot_mode_comparison(comparison, run_dir / "compare_voltage.png",
                         v_max=project.base.v_max_pu)
    plot_curtailment_comparison(comparison, run_dir / "compare_curtailment.png")

    print("项目「%s」三方式对比完成（%.1f s）：" % (project.name, elapsed))
    for m in comparison.metrics:
        print("  %-8s 削减 %9.1f kWh | 峰值 %7.1f kW @%s时 | maxV %.4f | "
              "迭代 %3d | %s"
              % (m.name, m.total_curtail_kwh, m.peak_curtail_kw,
                 m.peak_hour if m.peak_hour is not None else "-",
                 m.max_v, m.total_iterations,
                 "全天安全" if m.all_safe else "存在越限"))
    print("结果已写入：%s" % run_dir)
    return 0
