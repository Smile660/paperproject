"""图表输出：matplotlib、PNG 300 DPI、中文标签（spec FR-7）。"""

from pathlib import Path
from typing import Iterable, List, Optional

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

from pvvr.engine.simulation import DayResult  # noqa: E402

_FONT_CANDIDATES = ["Microsoft YaHei", "SimHei", "Noto Sans CJK SC", "WenQuanYi Micro Hei"]


def setup_chinese_font() -> None:
    """显式配置中文字体，避免方框乱码；找不到时退回默认并保持其余可用。"""
    from matplotlib import font_manager
    available = {f.name for f in font_manager.fontManager.ttflist}
    for name in _FONT_CANDIDATES:
        if name in available:
            matplotlib.rcParams["font.sans-serif"] = [name]
            break
    matplotlib.rcParams["axes.unicode_minus"] = False


def plot_voltage_trajectory(day: DayResult, path: Path,
                            v_min: float, v_max: float,
                            title: str = "24h 电压轨迹（无控制）") -> Path:
    """24h 全网最大/最小电压轨迹 + Vmin/Vmax 参考线。"""
    setup_chinese_font()
    hours = day.hour_series()
    vmax = day.max_v_series()
    vmin = day.min_v_series()
    fig, ax = plt.subplots(figsize=(10, 5))
    ax.plot(hours, vmax, color="#d62728", marker="o", ms=3, label="全网最大电压")
    ax.plot(hours, vmin, color="#1f77b4", marker="o", ms=3, label="全网最小电压")
    ax.axhline(v_max, color="#d62728", ls="--", lw=1, label="电压上限 Vmax")
    ax.axhline(v_min, color="#1f77b4", ls="--", lw=1, label="电压下限 Vmin（仅记录）")
    ax.set_xlabel("时刻 / h")
    ax.set_ylabel("电压 / pu")
    ax.set_title(title)
    ax.set_xticks(range(0, 24, 2))
    ax.set_xlim(-0.5, 23.5)
    ax.legend(loc="best", fontsize=9)
    ax.grid(alpha=0.3)
    fig.tight_layout()
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(str(path), dpi=300)
    plt.close(fig)
    return path
