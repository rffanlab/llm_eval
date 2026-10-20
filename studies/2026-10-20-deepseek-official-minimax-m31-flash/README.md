# DeepSeek V4.1 Flash 1017 vs MiniMax M3.1 Flash / Flash Preview

## 为什么做

2026-10-19发布的MiniMax M3.1 Flash，是否补上此前Flash Preview在代码、工具和写作交付上的缺口？DeepSeek V4.1 Flash 1017在同一预算下又表现如何？本研究比较可检查的最终交付，不以官方榜单替代实测。

## 怎么做

当前两端均为官方API：DeepSeek `deepseek-flash`（官方10月17日更新映射至V4.1 Flash 1017）；MiniMax `MiniMax-M3.1-Flash`。MiniMax Preview是10月13日历史记录，不是本日重新调用。两端远程推理硬件、量化及负载未知；发请求和运行受限工具的调用机为Ryzen AI Max+395、128GB、Ubuntu 24.04。模型配置、参数差异见[环境](environment.json)与[渠道说明](official-channel-notes.md)。

- [冻结协议](protocol.md)、[26项SHA](freeze.json)、[逐题提示词和验收](task-cards.md)、[机器可读题库](tasks.json)。
- [四阶段连续长程](long-horizon/task.json)：持久工作区、需求变更、回归、一次可恢复工具故障及最终文件/报告。
- [100K+长上下文](long-context/README.md)：两道任务、各两轮，同份材料；实际输入DeepSeek约130K、MiniMax约127K token，全部8项正式请求均超过100000。长输入不替代多阶段长程。
- 每端22项正式材料：14个主测短题、2个D01 low诊断、2个完整长程、4个长上下文。DeepSeek官方22项新测；MiniMax22项复用当日原样记录，见[minimax-capture-provenance.json](minimax-capture-provenance.json)。另4项事后登记的low单次探索单列，不进入主分。
- 主测请求max，短题输出上限4096/8192，含思考；同名档位不保证同等思考量。两端均未按请求temperature=0固定温度，不能称严格等采样或默认档比较。
- 题目和预算先冻结；人工逐项启动、审读，不提供无人值守批量API入口。模型失败、截断、原始硬分保持。
- 代码通过独立功能断言；Agent动作、权限和严格最终JSON分别核对；写作是AI助手按事实、完整、清楚、可用四维0–5审读，>=16且硬项通过，不是人类盲审。

## 结果

|指标|DeepSeek V4.1 Flash 1017 官方API|MiniMax M3.1 Flash 正式版|MiniMax M3.1 Flash Preview 10月13日|
|---|---:|---:|---:|
|7类短题完整交付|11/14|8/14|9/14|
|四阶段严格完整交付|0/2|0/2|0/2|
|最终发布文件正确|1/2|1/2|1/2|
|LC01核心决策及证据正确（语义注释）|1/2|2/2|历史未测|
|LC02内容+编辑达标（语义注释）|1/2|0/2|历史未测|
|LC两题冻结原严格交付|0/4|0/4|历史未测|
|原生Prefill / Decode token/s|未知 / 未知|未知 / 未知|未知 / 未知|

在本轮官方API、max与固定预算下，综合推荐DeepSeek V4.1 Flash 1017用于有验收的小函数、少步工具任务、事实短讯及有人核对的档案整理。MiniMax M3.1 Flash正式版的LC01核心结果较稳定，low调度单次用更少输出token通过同一13项检查；本套主测没有证明其全面改善Preview。两者复杂决策稿及严格长程均未过，不能据此推荐无人接管完整项目。

完整逐题、逐阶段表格和结论见[文章](publication/wechat-article.md)。[summary.json](summary.json)为派生统计，[all-turn-timings.csv](all-turn-timings.csv)为逐调用时间和token；原生Prefill/Decode未公开，保持未知，不能以API等待倒算。API观察生成速率若有值，也不是引擎Decode。

## 不能省略的解释

1. [评测器限制](official-runner-review.json)：冻结长程runner在截断tool call后遗留未配对历史，导致部分后续阶段400/500；这些阶段未实际执行，不能当作模型能力失误。文件正确与严格全过程通过分别统计。
2. [词面等价注释源码](semantic_annotations.py)：LC的`P-V2`/`v2`、已知证据ID前的`DOC `及额外旧政策引用分别披露；语义注释不覆盖冻结原硬分。所有必要决策、金额和证据仍须正确；LC02另过编辑门槛。该注释在观察MiniMax结果后登记，非原始预注册分数。
3. [写作审读](editorial-review.json)、[最终文件独立核对](final-file-audit.json)、[最终准确抓取](final-capture-audit.json)分别保存，不从关键词命中推断可用文章。
4. [low探索](low-diagnostics-summary.json)每端每题仅1次；虽在调用前登记，问题选择来自已观察截断，不替换max主测，不证明最优档位。
5. MiniMax LC01第1轮曾与旧代理请求重叠约8秒；质量/token/实测等待保留，不用于串行速度胜负。日期、时段和云端负载无法严格控制。
6. 共同核心累计含失败；有400/500的未知usage，使用已知下限。tokenizer及交付项数不同，不能据此推算等质量成本或实际账单。

## 公开材料与复跑

原始回复和工具轨迹位于`results/`；`results/long/*/r*/snapshots`为各阶段工作区。历史Preview保持在[原研究](../2026-10-13-minimax-m31-vs-local-qwen)。本轮DeepSeek全为官方新测，OpenCode材料未混入这里。

冻结源不因发现限制改写；[复跑说明](reproduction.md)给出单案例入口。先读冻结版本、预算及限制，再自行决定是否复现旧行为。`aggregate.py`只读原始材料生成统计；它不会发起模型调用。

公众号富文本、旁白、无导流的B站文案、排版封面和技术核对保存在`publication/`。视频本体作为本地交付，未将大视频或私密声音参考上传到本库。数据表均为实测文件排版回放，不伪装成界面录像。
