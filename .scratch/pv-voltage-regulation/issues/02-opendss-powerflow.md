# 02: OpenDSS 单断面潮流（IEEE 33 基态 tracer）

**What to build:** 用户在 CLI 运行 `python -m pvvr run project.json --mode snapshot`，平台把网络模型翻译为 OpenDSS 模型（opendssdirect 内置引擎，无需独立安装），求解三相不平衡潮流，输出全部节点分相电压（pu）与线路负载率到控制台和 CSV。潮流求解设置（Newton、收敛容差、最大迭代）按 §5 统一配置，为双引擎一致性打底。IEEE 33 基态复现文献最低电压，成为项目的第一条回归测试。

**Blocked by:** 01: 项目骨架与网络模型

**Status:** ready-for-agent

- [ ] IEEE 33 基态最低电压 ≈0.913 pu（节点 18），与文献偏差 <0.5%（ET-1、验收 1）
- [ ] 输出全部节点分相电压（pu）与线路负载率 CSV
- [ ] 三相混接模型可求解：单相负荷/光伏正确指定 A/B/C 相
- [ ] 潮流不收敛时给中文诊断报错（FR-9），不崩溃退出
- [ ] 单断面潮流 IEEE 33 规模毫秒级完成（NFR-1）
