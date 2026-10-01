# 10: MATLAB 引擎（.m 生成 + matlab -batch + 双引擎一致性）

**What to build:** 可选引擎落地（ADR-0002）：把网络模型、前推回代三相潮流、公平二分法算法镜像（含公平责任权重与 H 跨断面累积）、24h 循环整体生成为一个完整 .m 脚本，经 `matlab -batch` 单进程整体跑完后回读结果，与 OpenDSS 结果同结构落盘、同规格导出；潮流求解设置与 §5 保持一致。MATLAB 路径取自设置页（自动探测），未配置/版本不符时中文报错并给出建议；MATLAB 不是运行依赖——未配置时除引擎切换外全部功能不受影响。

**Blocked by:** 04: 公平二分法闭环控制

**Status:** ready-for-agent

- [ ] 生成的 .m 在 MATLAB R2024b 下 `matlab -batch` 跑完并回读四数据集，结构与 OpenDSS 结果一致
- [ ] ET-2：固定小模型同一算法，OpenDSS 与 MATLAB 电压偏差 ≤0.001 pu（验收 4）
- [ ] 算法镜像与 Python 实现语义一致：Q-1/Q-2 默认语义、α/β/γ、δ 同参数同结果（NFR-4 之 MATLAB 镜像）
- [ ] MATLAB 路径无效或版本不符时中文报错与建议，不崩溃（FR-9）
- [ ] 无 MATLAB 环境：OpenDSS 全流程（建模→仿真→控制→导出）不受影响（验收 5）
