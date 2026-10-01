from pvvr.model import schema as sch
from pvvr.model import validate as dom
from pvvr.model.presets import PRESETS
from pvvr.model.presets import ieee33


def test_both_presets_pass_full_validation():
    for name, builder in PRESETS.items():
        p = sch.project_from_dict(builder())
        errs = dom.validate_project(p)
        assert errs == [], "%s: %s" % (name, errs)


def test_ieee33_shape():
    p = sch.project_from_dict(ieee33.build_dict())
    assert len(p.nodes) == 33
    assert len(p.lines) == 32
    assert p.base.slack.node == "1"
    assert p.base.v_base_kv == 12.66


def test_ieee33_load_totals_match_baran_wu():
    """三相总负荷 = 3715 kW / 2300 kvar（Baran & Wu 原始数据）。"""
    p = sch.project_from_dict(ieee33.build_dict())
    total_p = sum(sum(n.load_kw.values()) for n in p.nodes)
    total_q = sum(sum(n.load_kvar.values()) for n in p.nodes)
    assert abs(total_p - 3715.0) < 1e-6
    assert abs(total_q - 2300.0) < 1e-6


def test_ieee33_per_phase_load_is_one_third():
    p = sch.project_from_dict(ieee33.build_dict())
    node30 = {n.id: n for n in p.nodes}["30"]        # 200 + j600 kvar 关键母线
    assert abs(node30.load_kw["A"] - 200.0 / 3.0) < 1e-9
    assert abs(node30.load_kvar["C"] - 600.0 / 3.0) < 1e-9


def test_ieee33_line_spot_checks():
    """抽查线路阻抗与 MATPOWER case33bw 一致。"""
    p = sch.project_from_dict(ieee33.build_dict())
    lines = {ln.id: ln for ln in p.lines}
    l1 = lines["L01"]
    assert l1.from_node == "1" and l1.to_node == "2"
    assert abs(l1.r_ohm_per_km["A"] - 0.0922) < 1e-12
    assert abs(l1.x_ohm_per_km["C"] - 0.0470) < 1e-12
    l32 = lines["L32"]
    assert l32.from_node == "32" and l32.to_node == "33"
    assert abs(l32.x_ohm_per_km["A"] - 0.5302) < 1e-12
    # 30-31（L30）：200/600 kvar 负荷所在支路
    l30 = lines["L30"]
    assert l30.from_node == "30" and l30.to_node == "31"


def test_single_phase_preset_shape():
    p = sch.project_from_dict(PRESETS["single_phase"]())
    assert all(n.phases == ["A"] for n in p.nodes)
    assert len(p.pvs) == 2
    assert all(v.phases == ["A"] for v in p.pvs)


def test_curves_24_points_peak_one():
    for name in PRESETS:
        p = sch.project_from_dict(PRESETS[name]())
        assert p.curves is not None
        assert len(p.curves.load) == 24 and len(p.curves.pv) == 24
        assert abs(max(p.curves.pv) - 1.0) < 1e-9
