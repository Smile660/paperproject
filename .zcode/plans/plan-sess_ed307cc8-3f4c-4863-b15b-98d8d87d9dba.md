# 分布式光伏电压调节仿真平台 — 实施计划

## 采用的默认决策（你未及作答，均取推荐项，随时可换）
1. **界面**: NiceGUI 纯 Python Web 应用（浏览器打开、本地运行，无需 Node.js）
2. **算法分工**: 领航跟随二分法在 Python 实现，逐轮调用 OpenDSS 潮流；MATLAB(R2024b) 用于一键导出 .m 验证脚本 + 可选 `matlab -batch` 调用；软件不强依赖 MATLAB
3. **Python**: 代码同时兼容本机现有 3.8 与推荐的 3.12（R2024b Engine API 需 ≥3.9）；MATLAB 调用走 `matlab -batch` 子进程，任何 Python 版本可用
4. **"二分法"结构**: 外层二分搜索满足电压安全 [Vmin,Vmax] 的全局系数，内层领航跟随一致性（带符号通信图）更新各光伏无功指令；算法集中在 `control.py` 单文件，公式可按你论文直接替换
5. **调节手段**: 以光伏逆变器无功 Q 为主，数据模型预留有功削减扩展位

## 系统架构
数据流：JSON 网络模型 → `dss_writer` 生成 .dss → OpenDSS 求解潮流 → 提取各节点分相电压 → 控制器更新光伏 Q 指令 → 循环至收敛/电压达标 → 结果展示与导出。

```
src/pvvr/
├── model/
│   ├── schema.py          # 数据模型 + JSON 序列化（节点/线路/光伏/控制参数/通信图）
│   ├── presets/           # IEEE33节点、IEEE13节点预设 + 单相自定义示例
│   └── dss_writer.py      # JSON → OpenDSS .dss 文本（分相负荷/线路/发电机）
├── engine/
│   ├── powerflow.py       # opendssdirect 驱动潮流、按相提取电压
│   ├── control.py         # ★ 领航跟随一致性 + 外层二分（单文件可替换）
│   └── simulation.py      # 编排循环、收敛史记录、24h 时序模式
├── matlab/
│   ├── exporter.py        # 生成验证用 .m 脚本（网络+算法 MATLAB 镜像）
│   └── bridge.py          # matlab -batch 子进程；路径自动探测+可配置
├── ui/  (app.py, editor.py, topology_view.py, sim_page.py, settings.py)
└── cli.py                 # 命令行无界面运行：python -m pvvr run project.json
projects/                  # 用户项目 JSON
tests/
```

## 核心数据模型
- **节点**: 编号/名称/相别（三相 ABC 或单相）/分相负荷 P,Q /光伏{单相或三相、容量、功率因数范围、Q 上下限、是否参与控制}
- **线路**: 首末端/相别/长度/分相 R,X（或线型库引用）/载流量
- **网络**: 基准电压、频率、Vmin=0.95、Vmax=1.05、平衡节点电压
- **控制配置**: 领航节点电压参考、一致性增益、二分区间与精度、光伏间通信图（边+符号权重）、逆变器限幅
- 项目保存为 JSON；内置 IEEE33/IEEE13 预设与自定义示例

## OpenDSS 集成
`opendssdirect.py`（pip 安装即自带 OpenDSS 引擎，无需 COM 或独立安装）。三相不平衡潮流，逐节点逐相提取电压标幺值；单相/三相负荷与光伏分别用 phases=1/3 建模。

## 控制引擎（核心，可替换）
- 内层：领航跟随一致性——跟随者按带符号通信图交换电压偏差、迭代更新无功指令（含限幅）
- 外层：二分法搜索全局缩放系数/参考值，直至所有母线电压落入 [Vmin,Vmax]
- 支持：快照模式与 24h 时序模式（负荷/光伏出力曲线可配）

## 界面（NiceGUI）
1. **网络编辑器**：节点表/线路表增删改、光伏与通信图配置
2. **拓扑视图**：ECharts 网络图（networkx 布局），按电压着色热力图，分相查看
3. **仿真控制页**：一键运行、迭代过程动画、电压轨迹、无功指令、收敛曲线、越限判定
4. **设置页**：MATLAB 路径、电压限值、导出目录；结果导出 CSV/Excel、.dss/.m

## 实施步骤
1. 脚手架：依赖、目录、schema、IEEE33/IEEE13/示例预设
2. dss_writer + 潮流：IEEE33 基态与文献已知电压比对（最末端约 0.913pu）作回归测试
3. control.py：高渗透光伏过电压场景下把电压压回 [0.95,1.05]
4. 时序模式 + 历史记录
5. NiceGUI 四个页面
6. MATLAB 导出器与 bridge（R2024b 装好后即可用）
7. pytest 测试 + README + GLOSSARY.md 术语表

## 验证方式
- pytest：schema 往返、IEEE33 基态电压误差 <0.5%、控制后全网电压达标、通信图容错
- 手工验收：打开预设 → 配置光伏与通信图 → 运行 → 查看热力图与收敛曲线 → 导出 .m

## 风险备注
- nicegui 在 Python 3.8 需锁 <2.0（requirements 做环境标记，升 3.12 后解锁）
- 本机目前只检出 R2018b；MATLAB 功能做成可选，路径可配置，装好 R2024b 填路径即用