"""pvvr 命令行入口（spec FR-8）。

子命令：
  validate <project.json | --preset NAME>   校验项目（结构 + 领域），中文定位报错
  preset <NAME> [--out PATH]                导出内置预设为项目 JSON
  ui                                        启动 Web 界面（票据 07 交付）
  run <project.json> ...                    运行仿真（票据 02 交付）
"""

import argparse
import sys
from pathlib import Path
from typing import List, Optional

from pvvr import settings as app_settings
from pvvr.model import schema as sch
from pvvr.model import validate as vcheck
from pvvr.model.presets import PRESETS


def _lookup_preset(name):
    builder = PRESETS.get(name)
    if builder is None:
        print("未知预设「%s」，可用：%s" % (name, "、".join(sorted(PRESETS))))
    return builder


def _preset_project(name):
    """构建预设并解析；预设数据异常时打印中文错误并返回 None（不崩溃）。"""
    builder = _lookup_preset(name)
    if builder is None:
        return None
    try:
        return sch.project_from_dict(builder())
    except sch.SchemaError as exc:
        print("预设「%s」数据结构错误（内置预设不应发生）：" % name)
        for e in exc.errors:
            print("  - %s" % e)
        return None


def _load_project_text(text: str):
    """解析 + 领域校验；失败时打印中文错误并返回 None。"""
    try:
        project = sch.project_from_json(text)
    except sch.SchemaError as exc:
        print("结构校验未通过（%d 处）：" % len(exc.errors))
        for e in exc.errors:
            print("  - %s" % e)
        return None
    errors = vcheck.validate_project(project)
    if errors:
        print("领域校验未通过（%d 处）：" % len(errors))
        for e in errors:
            print("  - %s" % e)
        return None
    return project


def _cmd_validate(args) -> int:
    if args.preset:
        project = _preset_project(args.preset)
        if project is None:
            return 2 if args.preset not in PRESETS else 1
        name = "预设 %s" % args.preset
        print("校验通过：%s（节点 %d，线路 %d，光伏 %d）"
              % (name, len(project.nodes), len(project.lines), len(project.pvs)))
        return 0
    if not args.project:
        print("用法：pvvr validate <project.json> 或 --preset NAME")
        return 2
    path = Path(args.project)
    if not path.exists():
        print("文件不存在：%s" % path)
        return 2
    project = _load_project_text(path.read_text(encoding="utf-8"))
    if project is None:
        return 1
    print("校验通过：%s（节点 %d，线路 %d，光伏 %d）"
          % (path, len(project.nodes), len(project.lines), len(project.pvs)))
    return 0


def _cmd_preset(args) -> int:
    project = _preset_project(args.preset)
    if project is None:
        return 2 if args.preset not in PRESETS else 1
    errors = vcheck.validate_project(project)
    if errors:
        print("内置预设自身校验失败（不应发生）：")
        for e in errors:
            print("  - %s" % e)
        return 1
    out = Path(args.out) if args.out else Path("projects") / (args.preset + ".json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(sch.project_to_json(project), encoding="utf-8")
    print("已导出预设 %s → %s" % (args.preset, out))
    return 0


def _cmd_ui(args) -> int:
    try:
        from pvvr.ui.app import run_ui  # 票据 07 交付
    except ImportError:
        print("Web 界面尚未交付（票据 07）。当前可用：validate / preset")
        return 2
    conf = app_settings.load_settings()
    run_ui(host=conf["ui_host"], port=conf["ui_port"])
    return 0


def _cmd_compare(args) -> int:
    from pvvr.cli_compare import compare_command
    return compare_command(args)


def _cmd_run(args) -> int:
    try:
        from pvvr.cli_run import run_command  # 票据 02 交付
    except ImportError:
        print("仿真运行尚未交付（票据 02）。当前可用：validate / preset")
        return 2
    return run_command(args)


def _cmd_set_curve(args) -> int:
    """曲线 CSV 导入（FR-2）：替换项目统一曲线的 load 或 pv 一条。"""
    from pvvr.model import curves_io
    path = Path(args.project)
    if not path.exists():
        print("文件不存在：%s" % path)
        return 2
    try:
        values = curves_io.read_curve_csv(Path(args.csv))
    except curves_io.CurveCsvError as exc:
        print("曲线 CSV 读取失败：%s" % exc)
        return 1
    project = sch.project_from_json(path.read_text(encoding="utf-8"))
    if project.curves is None:
        from pvvr.model.schema import Curves
        project.curves = Curves(load=[1.0] * 24, pv=[1.0] * 24)
    setattr(project.curves, args.kind, values)
    path.write_text(sch.project_to_json(project), encoding="utf-8")
    print("已将 %s 曲线导入项目 %s（峰值 %.4f）" % (args.kind, path, max(values)))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="pvvr", description="分布式光伏电压调节仿真平台")
    sub = parser.add_subparsers(dest="command")

    p_val = sub.add_parser("validate", help="校验项目 JSON 或内置预设")
    p_val.add_argument("project", nargs="?", default=None, help="项目 JSON 路径")
    p_val.add_argument("--preset", default=None,
                       help="内置预设名（%s）" % "、".join(sorted(PRESETS)))
    p_val.set_defaults(func=_cmd_validate)

    p_pre = sub.add_parser("preset", help="导出内置预设为项目 JSON")
    p_pre.add_argument("preset", help="预设名")
    p_pre.add_argument("--out", default=None, help="输出路径（默认 projects/<name>.json）")
    p_pre.set_defaults(func=_cmd_preset)

    p_ui = sub.add_parser("ui", help="启动 Web 界面（票据 07）")
    p_ui.set_defaults(func=_cmd_ui)

    p_curve = sub.add_parser("set-curve", help="导入统一曲线 CSV（两列 hour,value）")
    p_curve.add_argument("project", help="项目 JSON 路径（就地更新）")
    p_curve.add_argument("--kind", choices=["load", "pv"], required=True,
                         help="替换哪条曲线")
    p_curve.add_argument("--csv", required=True, help="曲线 CSV 路径")
    p_curve.set_defaults(func=_cmd_set_curve)

    p_cmp = sub.add_parser("compare", help="一键对比：无控制/集中式/公平二分法")
    p_cmp.add_argument("project", help="项目 JSON 路径")
    p_cmp.add_argument("--out", default=None, help="输出目录（默认 settings.output_dir）")
    p_cmp.set_defaults(func=_cmd_compare)

    p_run = sub.add_parser("run", help="运行仿真")
    p_run.add_argument("project", help="项目 JSON 路径")
    p_run.add_argument("--mode", default="snapshot", choices=["snapshot", "24h"],
                       help="运行模式（默认 snapshot；24h 于票据 03 交付）")
    p_run.add_argument("--t", type=int, default=None, help="快照取值小时 0-23（默认额定负荷）")
    p_run.add_argument("--engine", default="opendss", choices=["opendss", "matlab"],
                       help="仿真引擎（默认 opendss；matlab 于票据 10 交付）")
    p_run.add_argument("--control", default="none", choices=["none", "fair"],
                       help="控制方式：none=无控制基线；fair=公平二分法（票据 04）")
    p_run.add_argument("--out", default=None, help="输出目录（默认 settings.output_dir）")
    p_run.set_defaults(func=_cmd_run)
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not getattr(args, "func", None):
        parser.print_help()
        return 0
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
