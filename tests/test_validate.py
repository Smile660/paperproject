from pvvr.model import schema as sch
from pvvr.model import validate as dom


def _ok_project():
    return sch.default_project()


def test_valid_project_passes():
    assert dom.validate_project(_ok_project()) == []


def test_duplicate_node_id():
    p = _ok_project()
    p.nodes.append(sch.Node(id="2", phases=["A", "B", "C"]))
    errs = dom.validate_project(p)
    assert any("节点编号重复「2」" in e for e in errs)


def test_line_endpoint_missing():
    p = _ok_project()
    p.lines[0].to_node = "99"
    errs = dom.validate_project(p)
    assert any("末端节点「99」不存在" in e for e in errs)


def test_line_phase_beyond_node_phase():
    p = _ok_project()
    p.nodes[1].phases = ["A"]                      # 节点 2 仅 A 相
    p.lines[0].phases = ["A", "B", "C"]            # 三相线路接不进
    errs = dom.validate_project(p)
    assert any("不含相 B" in e for e in errs)


def test_pv_must_be_single_or_three_phase():
    p = _ok_project()
    p.pvs[0].phases = ["A", "B"]                   # 两相不允许（spec FR-1）
    errs = dom.validate_project(p)
    assert any("单相" in e and "三相" in e for e in errs)


def test_loop_detected_and_listed():
    """验收 6 之环路部分：检出环路并列出参与线路与节点。"""
    p = _ok_project()
    p.nodes.append(sch.Node(id="3"))
    p.lines.append(sch.Line(  # 2-3
        id="L2", from_node="2", to_node="3", length_km=1.0,
        r_ohm_per_km={"A": 0.3}, x_ohm_per_km={"A": 0.3}))
    p.lines.append(sch.Line(  # 1-3 闭合环路 1-2-3-1
        id="L3", from_node="3", to_node="1", length_km=1.0,
        r_ohm_per_km={"A": 0.3}, x_ohm_per_km={"A": 0.3}))
    errs = dom.validate_project(p)
    loop_errs = [e for e in errs if "环路" in e]
    assert loop_errs, errs
    msg = loop_errs[0]
    assert "L3" in msg and "1" in msg and "2" in msg and "3" in msg


def test_disconnected_node_reported():
    p = _ok_project()
    p.nodes.append(sch.Node(id="9"))
    errs = dom.validate_project(p)
    assert any("不连通" in e and "9" in e for e in errs)


def test_slack_missing():
    p = _ok_project()
    p.base.slack.node = "100"
    errs = dom.validate_project(p)
    assert any("平衡节点「100」不存在" in e for e in errs)


def test_load_phase_beyond_node_phase():
    p = _ok_project()
    p.nodes[1].phases = ["A"]
    p.nodes[1].load_kw = {"A": 10.0, "B": 5.0}
    errs = dom.validate_project(p)
    assert any("有功负荷相别" in e for e in errs)


def test_line_impedance_phase_mismatch():
    p = _ok_project()
    p.lines[0].r_ohm_per_km = {"A": 0.3, "B": 0.3}   # 缺 C
    errs = dom.validate_project(p)
    assert any("电阻相别" in e for e in errs)


def test_comm_edge_unknown_agent():
    p = _ok_project()
    p.comm_graph.edges.append(sch.CommEdge(from_agent="PVX", to_agent="PV1"))
    errs = dom.validate_project(p)
    assert any("不是已知光伏编号" in e for e in errs)


def test_line_type_reference_missing():
    p = _ok_project()
    p.lines[0].line_type = "TYPE9"
    errs = dom.validate_project(p)
    assert any("线型「TYPE9」未定义" in e for e in errs)
