# 导演表（实际测评数据）

- 采用同任务三方数据对照表，画面均标DATA，不作为真实录屏。
- 开头展示32K探针实测差距，说明为什么换卡；首次短题结果约49秒。
- 每题、长程每阶段立即显示对比和结论，保留Prefill、Decode、完整等待、交付与token。
- 新配音全部Qwen3-TTS本人音色，1.0倍，无音乐和音效。
- 仅技术及抽样画面核验，未声称真人听审。

|场次|类型|主题|分表/摘录数量|证据|
|---|---|---|---|---|
|1|DATA|261W的7900 XTX，跑大模型值不值？|3|speed/prompt32k · 速度探针，不评长文理解|
|2|DATA|同一模型与量化，同版Strata|4|environment/ · 另两端基线f0def49|
|4|DATA|L1 · 严格JSON筛选|3|task-cards.md / tasks.json|
|5|DATA|L1 · 金额纯函数|3|task-cards.md / tasks.json|
|6|DATA|L1 · 有事实边界的短讯|3|task-cards.md / tasks.json|
|7|DATA|L2 · 查库存，只预留一次|3|task-cards.md / tasks.json|
|8|DATA|L3 · 资源约束调度|3|task-cards.md / tasks.json|
|9|DATA|L3 · 排障与权限边界|3|task-cards.md / tasks.json|
|10|DATA|L3 · 多约束决策备忘录|3|task-cards.md / tasks.json|
|11|DATA|S1 · 修复基础对账|3|long-horizon/ · LH01 v1.1.1 / 每阶段12次回复含收尾|
|12|DATA|S2 · 兼容变更与历史回归|3|long-horizon/ · LH01 v1.1.1 / 每阶段12次回复含收尾|
|13|DATA|S3 · 发布与故障恢复|3|long-horizon/ · LH01 v1.1.1 / 每阶段12次回复含收尾|
|14|DATA|S4 · 迟到退款与最终交付|3|long-horizon/ · LH01 v1.1.1 / 每阶段12次回复含收尾|
|15|DATA|文件做对了，流程仍没完整过关|2|long/ALL · 全部调用加总后算速度，不平均阶段速度|
|16|DATA|固定生成512 token，解码有多快？|2|speed/short512 · 三次中位 / 原生计算与API耗时分列|
|17|DATA|32K输入：7900 XTX这次最快|3|speed/prompt4k · 三次中位 / 原生计算与API耗时分列|
|18|DATA|简单筛选题，关闭思考少等多少？|3|main/D01 与 depth/D01 · 两轮中位|
|19|DATA|设置261W，实测最高270W|2|hardware-observation.json / hardware-telemetry.jsonl|
|20|DATA|这套工作题，综合推荐AI Max+395|2|summary.json / final-artifact-audit.json|
