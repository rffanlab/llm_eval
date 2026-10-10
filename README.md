# llm_eval

最新已完成：[本地 AI Max+395：Qwen3.8 27B与Next Flash实测](studies/2026-10-10-qwen27b-vs-next-flash/README.md)。同一Gufo0.11.0，两边Q4_K_XL，分别配DFlash2与MTP；主测合格14/16对15/16，完整等待828.36秒对360.33秒。107个记录包含首正文、预填充、解码、缓存、思考开关与最长258028token实际输入，附逐题文章及视频发布资料。

前一期：[本地 AI Max+395：Gufo Q4_K_XL与Halogen工作、token及容量对照](studies/2026-10-10-gufo-vs-halogen/README.md)。同一重启环境的主测合格交付15/16对14/16，原始加载与接入失败保留；达到事前门槛后，现有服务切到Gufo并保留回滚。

上一期：[本地 AI Max+395＋USB4 RX7900XTX 的 Strata 工作与容量评测](studies/2026-10-09-strata-usb4-7900xtx/README.md)。

可公开复跑的工作能力评测：为什么测 → 怎么测 → 测试结果。

首期：本地 Ryzen AI Max+ 395 机器运行 Qwen3.8 Flash Next 与阿里云 Token Plan `qwen3.8-flash` 的工作能力对照。测试前规范见 [方法](studies/2026-10-07-local-vs-cloud/protocol.md)，完整题面与验收答案由 [题库生成器](suite/build_suite.py) 写入 `suite/tasks.json`。结果保留响应正文、用量、计时、工具轨迹和失败。

运行环境 Python 3.10+，标准库。无第三方安装需求。密钥只从环境读取。`python runner.py --help` 查看逐题运行方式；本仓库不提供 Token Plan 批量执行入口。生成代码只在受限制的独立进程中执行纯函数测试，拒绝导入、文件和网络调用。

题量有限，结论只针对被测任务与当次配置。云端与本地模型身份不能证明完全相同，差距不能直接解释为量化损失。

## 2026-10-07 实测已完成

10类题，32个主试验会话＋8个单独诊断。主试验本地代码和受限Agent任务通过；复杂写作仍需编辑验收。官方复杂调度原始3次均240秒超时，8192总预算诊断耗尽思考预算、正文为空。不能简化为哪一端全面胜出。

- [公众号文章：逐题任务、结果、差距与结论](studies/2026-10-07-local-vs-cloud/publication/wechat-article.md)
- [B站视频脚本](studies/2026-10-07-local-vs-cloud/publication/bilibili-script.md)
- [完整题库](suite/tasks.json) · [技术任务卡](studies/2026-10-07-local-vs-cloud/task-cards.md)
- [主试验汇总](studies/2026-10-07-local-vs-cloud/summary.json) · [原始记录](studies/2026-10-07-local-vs-cloud/results)
- [诊断计划](studies/2026-10-07-local-vs-cloud/diagnostic-plan.md) · [诊断结果](studies/2026-10-07-local-vs-cloud/diagnostic-summary.json)
- [配置与环境](studies/2026-10-07-local-vs-cloud/environment.json) · [编辑代理复核](studies/2026-10-07-local-vs-cloud/editor-review.json)
- [参数口径、题面歧义与评分器修正](studies/2026-10-07-local-vs-cloud/observations.md) · [明确裁定](studies/2026-10-07-local-vs-cloud/adjudications.json)
- [后续评测统一方法](METHODOLOGY.md)

主试验同名max_tokens语义不一致，不是等预算能力排名；总预算对齐诊断已单独存档。E01题面数组类型不够明确，本地语义正确、严格格式未过，不能称为事实检索错误。一个官方W02诊断的单换行段落被原评分器误扣分，原分保留，复核通过另列。所有超时缺失usage都视为未知，不能当零成本。

## 离线核对

```bash
python -m unittest discover -s tests
python summarize.py
python summarize_diagnostics.py
python audit_results.py
python check_public_archive.py
```

以上命令不调用模型API。主试验第一次冻结commit为`42cec2a`；随后追加诊断和公开复核，不覆盖历史输出。文章/视频不自动发布到社交平台。

## 2026-10-08：本地 AI Max+ 395，Halogen 升级与 Swift 1.5

同一台本地 Ryzen AI Max+ 395 机器，对比 Halogen 0.9.1/W4B、0.17.2/默认 v2 和 0.17.2/Swift 1.5。

- [冻结协议](studies/2026-10-08-halogen-three-way/protocol.md) · [完整提示词与验收](studies/2026-10-08-halogen-three-way/task-cards.md)
- [模型与版本来源](studies/2026-10-08-halogen-three-way/sources.json)
- [追加过度思考协议](studies/2026-10-08-halogen-three-way/overthinking-protocol.md) · [唯一答案短题](studies/2026-10-08-halogen-three-way/overthinking-tasks.json)
- [48 个主会话汇总](studies/2026-10-08-halogen-three-way/summary.json) · [操作记录与限制](studies/2026-10-08-halogen-three-way/observations.md)
- [4096 预算补充协议](studies/2026-10-08-halogen-three-way/overthinking-native-protocol.md) · [思考开关结果](studies/2026-10-08-halogen-three-way/thinking-native-summary.json)
- [公众号逐题文章](studies/2026-10-08-halogen-three-way/publication/wechat-article.md) · [可复制富文本页面](studies/2026-10-08-halogen-three-way/publication/wechat-richtext.html)
- [B站脚本](studies/2026-10-08-halogen-three-way/publication/bilibili-script.md) · [写作复核](studies/2026-10-08-halogen-three-way/editor-review.json) · [记录完整性审计](studies/2026-10-08-halogen-three-way/audit.json)

已完成10个独立题型、48个主会话；硬验收旧版15/16、新版13/16（含短评段落复核）、Swift10/16，按题型分别9/10、9/10、6/10。Swift调度器三次13/13，耗时中位35.60秒，新版64.71秒；严格JSON的Agent有代码框失败，团队决策写作三组均未达编辑门槛。固定512输出探针的解码中位数55.39/70.27/75.30 token/秒，不是首字或整项任务速度。

过度思考补充：1024原预算受新版正文预留策略影响，保留为接口诊断；追加登记4096预算的同三题、开关各两次，36次均答对。Swift简单题仍有额外思考开销。复杂调度关闭思考各一次13/13，不代表所有复杂工作。

短题通过 `overthinking_runner.py --native` 读取进程环境连接兼容接口。全档案139个记录会话、306044个已知总token，另一次取消调用用量未知。原始失败和段落复核分别存档；恢复后首条旧版请求的长预填充单列说明。实验后恢复原0.9.1服务，单元文件未改。
