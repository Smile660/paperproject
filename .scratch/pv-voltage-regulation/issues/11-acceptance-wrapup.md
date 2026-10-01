# 11: 验收收尾（README / 双版本 / 可复现 / 验收 1–8 核对）

**What to build:** 发布前整备：README 快速开始（安装依赖 → 启动 Web/CLI → 跑通演示场景）；requirements 固定版本并在 Python 3.8 与 3.12 干净环境分别验证安装运行；可复现性验证（同一项目同一参数重复运行，数值与导出文件完全一致）；对照 spec 验收标准 1–8 逐条核对并留存核对记录；ET-1/ET-2/ET-3 全绿。

**Blocked by:** 08: 拓扑热力图页与仿真结果页 · 09: 算法展示页与设置页 · 10: MATLAB 引擎

**Status:** ready-for-agent

- [ ] spec 验收标准 1–8 逐条核对通过，核对记录落盘（spec 同目录或 results）
- [ ] ET-1 / ET-2 / ET-3 全绿（pytest 一键运行）
- [ ] Python 3.8 与 3.12 干净环境按 README 从零安装并跑通演示场景（NFR-2/7）
- [ ] 同输入两次运行，导出文件完全一致（NFR-6）
- [ ] README 步骤可被实验室其他成员照做跑通（中文）
