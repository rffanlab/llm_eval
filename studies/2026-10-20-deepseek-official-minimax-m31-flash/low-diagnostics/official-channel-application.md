# 本研究中的官方接口应用说明

`protocol.md`与`runner.py`保持本目录`freeze.json`登记的原字节；协议中的“DeepSeek/OpenCode”是先前探索方案的渠道措辞。当前研究实际使用DeepSeek官方`deepseek-flash`，MiniMax使用官方`MiniMax-M3.1-Flash`，没有继承任何OpenCode的低思考回复。两端各执行C03、LC01一次low，共4个探索结果。

选这两题的动机来自已经观察到的max截断，包括旧代理与MiniMax的结果，属于事后选择问题、调用前登记；不能称为完全事前规划的确认性实验。当前官方请求的输出上限8192、思考low、题面和评分均按原冻结源；LC01使用预定R3材料，两端实际输入分别130203、127280 token。

本次官方探索登记文件的冻结时间为2026-10-20 17:53:28（UTC+8），在官方新增low请求之前。所有原硬分保持；DOC前缀、政策文档标识与额外旧政策引用的解释见研究根目录`semantic_annotations.py`。完整结果、耗时与生成/缓存token见`../low-diagnostics-summary.json`及`../low-diagnostics-turn-timings.csv`。Prefill/Decode没有原生计时，未知。
