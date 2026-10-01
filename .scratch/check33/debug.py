"""调试：打印前 3 轮迭代的母线电压，定位 sweep 的问题。"""
import math
import check as C  # 复用负荷与线路表

kv = 12.66 / math.sqrt(3.0)
sbase_kva = 1000.0
zb = kv ** 2 * 1000.0 / sbase_kva

table = C.TABLE_B
n = 33
adj = {i: [] for i in range(1, n + 1)}
for f, t, r, x in table:
    adj[f].append((t, complex(r, x) / zb))

parent = {1: (None, 0j)}
order = []
stack = [1]
seen = {1}
while stack:
    u = stack.pop()
    order.append(u)
    for v, z in adj[u]:
        if v not in seen:
            seen.add(v)
            parent[v] = (u, z)
            stack.append(v)

s = {b: 0j for b in range(1, n + 1)}
for b, (p, q) in C.LOADS.items():
    s[b] = complex(p, q) / sbase_kva

v = {b: 1 + 0j for b in range(1, n + 1)}
print("zb =", zb, "ohm;  z12_pu =", 0.0922 / zb)
for it in range(1, 4):
    ibr = {b: (s[b] / v[b]).conjugate() for b in range(1, n + 1)}
    for u in reversed(order):
        if u == 1:
            continue
        p, _ = parent[u]
        ibr[p] += ibr[u]
    print("iter", it, "I12 =", ibr[1], " |I12| =", abs(ibr[1]),
          " I18 =", ibr[18], " |I18| =", abs(ibr[18]))
    for u in order[1:]:
        p, z = parent[u]
        v[u] = v[p] - z * ibr[u]
    print("   V2 =", abs(v[2]), " V6 =", abs(v[6]), " V18 =", abs(v[18]),
          " V33 =", abs(v[33]))
