"""领域校验：结构合法之外的电气/图论约束（spec FR-1/FR-5/FR-9）。

返回中文错误列表，每条定位到对象（节点/线路/光伏编号）。含环项目在此
被检出并列出参与环路的线路与节点（验收 6）。
"""

from typing import Dict, List

from pvvr.model.schema import LEADER_AGENT, Project


class _UnionFind:
    def __init__(self):
        self.parent: Dict[str, str] = {}

    def find(self, x: str) -> str:
        self.parent.setdefault(x, x)
        root = x
        while self.parent[root] != root:
            root = self.parent[root]
        while self.parent[x] != root:
            self.parent[x], x = root, self.parent[x]
        return root

    def union(self, a: str, b: str) -> bool:
        ra, rb = self.find(a), self.find(b)
        if ra == rb:
            return False
        self.parent[ra] = rb
        return True


def _find_cycles(p: Project) -> List[tuple]:
    """找出全部环路。返回 [(环上线路 id 列表, 环上节点 id 列表), ...]。

    做法：并查集先构成生成森林；每条并入失败的线路即闭合一条环，
    该线路两端在森林中的唯一路径 + 该线路本身即为完整环路。
    """
    uf = _UnionFind()
    forest_adj: Dict[str, List[tuple]] = {}
    extra: List[object] = []
    for ln in p.lines:
        if uf.union(ln.from_node, ln.to_node):
            forest_adj.setdefault(ln.from_node, []).append((ln.to_node, ln.id))
            forest_adj.setdefault(ln.to_node, []).append((ln.from_node, ln.id))
        else:
            extra.append(ln)
    cycles = []
    for ln in extra:
        # BFS 在森林中找 from→to 的唯一路径
        start, goal = ln.from_node, ln.to_node
        prev: Dict[str, tuple] = {start: (None, None)}
        queue = [start]
        while queue and goal not in prev:
            u = queue.pop(0)
            for v, lid in forest_adj.get(u, []):
                if v not in prev:
                    prev[v] = (u, lid)
                    queue.append(v)
        if goal not in prev:
            cycles.append(([ln.id], [start, goal]))
            continue
        path_nodes = [goal]
        path_lines = [ln.id]
        cur = goal
        while cur != start:
            cur, lid = prev[cur]
            path_nodes.append(cur)
            path_lines.append(lid)
        cycles.append((sorted(set(path_lines)), sorted(set(path_nodes))))
    return cycles


def _reachable_from_slack(p: Project) -> List[str]:
    adj: Dict[str, List[str]] = {n.id: [] for n in p.nodes}
    for ln in p.lines:
        adj.setdefault(ln.from_node, []).append(ln.to_node)
        adj.setdefault(ln.to_node, []).append(ln.from_node)
    seen = set()
    stack = [p.base.slack.node]
    while stack:
        u = stack.pop()
        if u in seen:
            continue
        seen.add(u)
        stack.extend(adj.get(u, []))
    return [n.id for n in p.nodes if n.id not in seen]


def validate_project(p: Project) -> List[str]:
    """全量领域校验。返回错误列表；空列表 = 通过。"""
    errors: List[str] = []
    nodes = {n.id: n for n in p.nodes}
    pvs = {v.id: v for v in p.pvs}
    line_types = {t.id: t for t in p.line_types}

    # 节点编号唯一
    seen: Dict[str, int] = {}
    for i, n in enumerate(p.nodes):
        if n.id in seen:
            errors.append("节点编号重复「%s」（nodes[%d] 与 nodes[%d]）" % (n.id, seen[n.id], i))
        else:
            seen[n.id] = i

    # 平衡节点存在
    if p.base.slack.node not in nodes:
        errors.append("平衡节点「%s」不存在（base.slack.node）" % p.base.slack.node)

    # 线路：端点存在、相别兼容、引用线型存在
    for i, ln in enumerate(p.lines):
        tag = "线路 %s" % (ln.id or "lines[%d]" % i)
        if ln.from_node not in nodes:
            errors.append("%s: 首端节点「%s」不存在" % (tag, ln.from_node))
        if ln.to_node not in nodes:
            errors.append("%s: 末端节点「%s」不存在" % (tag, ln.to_node))
        if ln.from_node in nodes and ln.to_node in nodes:
            for side, nid in (("首端", ln.from_node), ("末端", ln.to_node)):
                bad = set(ln.phases) - set(nodes[nid].phases)
                if bad:
                    errors.append("%s: %s节点「%s」不含相 %s（线路相别 %s 超出节点相别 %s）"
                                  % (tag, side, nid, "/".join(sorted(bad)),
                                     "".join(ln.phases), "".join(nodes[nid].phases)))
        if ln.line_type and ln.line_type not in line_types:
            errors.append("%s: 引用的线型「%s」未定义" % (tag, ln.line_type))
        if not ln.r_ohm_per_km and not ln.x_ohm_per_km and not ln.line_type:
            errors.append("%s: 未给出分相阻抗且未引用线型" % tag)
        for ph_key, spec_key in (("r_ohm_per_km", "电阻"), ("x_ohm_per_km", "电抗")):
            given = set(getattr(ln, ph_key).keys())
            if given and given != set(ln.phases):
                errors.append("%s: %s相别 %s 与线路相别 %s 不一致"
                              % (tag, spec_key, "/".join(sorted(given)), "".join(sorted(ln.phases))))

    # 光伏：节点存在、相别（单相或三相，spec FR-1）、相别兼容、编号唯一
    pv_seen: Dict[str, int] = {}
    for i, v in enumerate(p.pvs):
        tag = "光伏 %s" % (v.id or "pvs[%d]" % i)
        if v.id in pv_seen:
            errors.append("光伏编号重复「%s」（pvs[%d] 与 pvs[%d]）" % (v.id, pv_seen[v.id], i))
        else:
            pv_seen[v.id] = i
        if v.node not in nodes:
            errors.append("%s: 所在节点「%s」不存在" % (tag, v.node))
            continue
        if len(v.phases) not in (1, 3):
            errors.append("%s: 相别应为单相（A/B/C 之一）或三相，实际 %s" % (tag, v.phases))
        bad = set(v.phases) - set(nodes[v.node].phases)
        if bad:
            errors.append("%s: 节点「%s」不含相 %s" % (tag, v.node, "/".join(sorted(bad))))

    # 负荷相别兼容
    for n in p.nodes:
        for attr, label in (("load_kw", "有功负荷"), ("load_kvar", "无功负荷")):
            bad = set(getattr(n, attr).keys()) - set(n.phases)
            if bad:
                errors.append("节点「%s」: %s相别 %s 超出节点相别 %s"
                              % (n.id, label, "/".join(sorted(bad)), "".join(sorted(n.phases))))

    # 连通性（自平衡节点可达全部节点）
    unreachable = _reachable_from_slack(p)
    if unreachable:
        errors.append("网络不连通：以下节点自平衡节点不可达（悬空/孤岛）：%s"
                      % "、".join(unreachable))

    # 环路检测：列出每个环的完整线路与节点（FR-1/验收 6）
    cycles = _find_cycles(p)
    for i, (cyc_lines, cyc_nodes) in enumerate(cycles, start=1):
        errors.append("馈线须为放射状：环路 %d 由线路 %s 构成，涉及节点 %s"
                      % (i, "、".join(cyc_lines), "、".join(cyc_nodes)))

    # 通信图：端点应为光伏编号（领航者以保留名表示，v1 平台集中计算不强制挂接）
    for i, e in enumerate(p.comm_graph.edges):
        for side, aid in (("from", e.from_agent), ("to", e.to_agent)):
            if aid != LEADER_AGENT and aid not in pvs:
                errors.append("通信边 comm_graph.edges[%d].%s「%s」不是已知光伏编号"
                              % (i, side, aid))
    return errors
