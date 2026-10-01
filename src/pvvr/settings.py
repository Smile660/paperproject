"""应用级设置（与项目 JSON 中的算法参数分离）：settings.json 于仓库根。

CLI 与 Web 同源读取（spec FR-8/设置页）。未知键保留不丢，缺键回填默认。
"""

import json
from pathlib import Path
from typing import Any, Dict

from pvvr.model.schema import SCHEMA_VERSION  # noqa: F401  （保持模块间版本一致策略）

DEFAULTS: Dict[str, Any] = {
    "default_engine": "opendss",     # opendss | matlab
    "matlab_path": "",               # MATLAB 可执行文件路径；空 = 未配置
    "output_dir": "results",
    "ui_port": 8080,
    "ui_host": "127.0.0.1",
}


def settings_path() -> Path:
    """settings.json 固定放仓库根（src/pvvr/settings.py 向上三级）。"""
    return Path(__file__).resolve().parent.parent.parent / "settings.json"


def load_settings() -> Dict[str, Any]:
    path = settings_path()
    data: Dict[str, Any] = {}
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except ValueError:
            data = {}
    merged = dict(DEFAULTS)
    if isinstance(data, dict):
        for k in DEFAULTS:
            if k in data and data[k] is not None:
                merged[k] = data[k]
    return merged


def save_settings(values: Dict[str, Any]) -> Dict[str, Any]:
    merged = load_settings()
    for k, v in values.items():
        if k in DEFAULTS:
            merged[k] = v
    path = settings_path()
    path.write_text(json.dumps(merged, ensure_ascii=False, indent=2), encoding="utf-8")
    return merged
