"""应用级设置（与项目 JSON 中的算法参数分离）：settings.json 于仓库根。

CLI 与 Web 同源读取（spec FR-8/设置页）。仅读写下方 DEFAULTS 声明的
已知键（含 algo_defaults 的已知子键）；文件中的未知键不会被保留。
"""

import json
from pathlib import Path
from typing import Any, Dict

DEFAULTS: Dict[str, Any] = {
    "default_engine": "opendss",     # opendss | matlab
    "matlab_path": "",               # MATLAB 可执行文件路径；空 = 未配置
    "output_dir": "results",
    "ui_port": 8080,
    "ui_host": "127.0.0.1",
    # §5 关键参数的设置级默认值（新建项目/项目未指定时的取值）
    "algo_defaults": {
        "v_min_pu": 0.95,
        "v_max_pu": 1.05,
        "alpha": 1.0,
        "beta": 1.0,
        "gamma": 1.0,
        "delta": 0.0005,
        "max_iter": 60,
        "pf_tol": 1e-4,
        "pf_max_iter": 100,
    },
}


def settings_path() -> Path:
    """settings.json 固定放仓库根（src/pvvr/settings.py 向上三级）。"""
    return Path(__file__).resolve().parent.parent.parent / "settings.json"


def _merge(base: Dict[str, Any], data: Dict[str, Any]) -> None:
    for k, default_v in base.items():
        if k not in data or data[k] is None:
            continue
        if isinstance(default_v, dict):
            if isinstance(data[k], dict):
                _merge(default_v, data[k])
        else:
            base[k] = data[k]


def load_settings() -> Dict[str, Any]:
    path = settings_path()
    data: Dict[str, Any] = {}
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except ValueError:
            data = {}
    if not isinstance(data, dict):
        data = {}
    merged = json.loads(json.dumps(DEFAULTS))  # 深拷贝默认值
    _merge(merged, data)
    return merged


def save_settings(values: Dict[str, Any]) -> Dict[str, Any]:
    merged = load_settings()
    _merge(merged, values)
    path = settings_path()
    path.write_text(json.dumps(merged, ensure_ascii=False, indent=2), encoding="utf-8")
    return merged
