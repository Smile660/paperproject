# 双仿真引擎：OpenDSS 默认，MATLAB 可选（整体批跑）

用户要求仿真引擎可在 OpenDSS 与 MATLAB（R2024b）之间选择，且推荐 OpenDSS。架构上做引擎抽象层：OpenDSS 模式经 opendssdirect.py 逐断面逐迭代交互求解（控制闭环内实时反馈电压）；MATLAB 模式把网络模型、潮流、控制算法与 24h 时序整体生成为一个 .m 脚本，经 `matlab -batch` 单进程跑完后回读结果，用于交叉验证，不做逐迭代在线调用（进程启动开销不可接受）。MATLAB 不是运行依赖：未配置 MATLAB 时除引擎切换外全部功能可用。

## Consequences

控制算法需维护 Python 与 MATLAB 两份实现，结果一致性（同模型同算法电压偏差 ≤0.001 pu）列入验收标准。选择 `matlab -batch` 而非 Engine API，使得现有 Python 3.8 环境可直接运行；将来升级 Python 3.12 后可加 Engine API 在线模式。
