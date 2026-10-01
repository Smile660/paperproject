"""内置预设注册表：preset dict 构建器。"""

from typing import Callable, Dict

from pvvr.model.presets import ieee33, ieee33_hp, single_phase

PRESETS: Dict[str, Callable[[], dict]] = {
    "ieee33": ieee33.build_dict,
    "ieee33_hp": ieee33_hp.build_dict,
    "single_phase": single_phase.build_dict,
}
