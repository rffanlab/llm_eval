# Gufo＋XDNA2 NPU / Qwen3.8 Next Flash UD-Q4_K_XL

[实测报告](report.md) · [冻结协议](protocol.md) · [完整题目](tasks.json) · [原生计时及逐题结果](metrics-reviewed.json) · [完整回复与工具轨迹](results/) · [审读](editorial-review.json) · [最终产物复核](final-artifact-audit.json) · [限制与评分器问题](analysis-limitations.json)。

三条件同一社区二进制、同一权重；87正式单位均完成。普通任务优先GPU基线，NPU双bank是长输入读取性能候选。32K Prefill+6.3%但同量输出Decode−3.8%、完整等待−3.4%；三条件常规严格短题均10/14。

冻结protocol与freeze文件保留测前字节，测后结论见report与metrics；不改测前题面或评分。32K仅吞吐，真正长上下文每轮实际109186token。

复算：在本研究目录执行 `python recompute_metrics.py`，生成独立的metrics-recomputed.json；不发模型请求、不改原始成绩。日志仅保留计数行、维持原字节位置，删去私有路径；详见auxiliary-source-manifest.json。
