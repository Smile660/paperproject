# 03: 统一曲线与 24h 时序仿真（无控制）

**What to build:** 统一曲线驱动断面生成：负荷/光伏各一条 24 点曲线（界面表格编辑留给 07，本票支持 CSV 两列导入与 JSON 内嵌），各节点按自身峰值缩放，光伏可用出力 = 额定容量 × 曲线缩放值；断面取整点阶梯值、不插值。`--mode 24h` 逐小时跑无控制潮流（即无控制基线的仿真内核），输出全程电压轨迹图（PNG，含 Vmin/Vmax 参考线、300 DPI、中文无乱码）与 CSV。快照模式可指定小时或手填断面值。

**Blocked by:** 02: OpenDSS 单断面潮流

**Status:** ready-for-agent

- [x] CSV（两列 hour, value，UTF-8）导入成功；负荷 P/Q 与光伏可用出力按峰值缩放计算正确
- [x] 24h 无控制运行输出 24 断面电压轨迹 PNG + CSV，中文标签无乱码、300 DPI
- [x] 快照模式可选某小时断面或手填值
- [x] 曲线为零的夜间断面光伏出力为 0（可用出力语义正确）

## Comments

- 2026-10-01 完成。matplotlib 预装 3.3.4（镜像无新版，requirements 用环境标记兼容 3.12）；中文字体候选序列（微软雅黑/黑体/Noto）；`set-curve` CLI 子命令就地更新项目曲线；24h 输出 summary.csv + voltages.csv + voltage_trajectory.png。66 项测试全绿。
