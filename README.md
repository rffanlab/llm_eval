# llm_eval

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

## 2026-10-08：Halogen 升级与 Swift 1.5（执行中）

同一台本地 Ryzen AI Max+ 395 机器，对比 Halogen 0.9.1/W4B、0.17.2/默认 v2 和 0.17.2/Swift 1.5。

- [冻结协议](studies/2026-10-08-halogen-three-way/protocol.md) · [完整提示词与验收](studies/2026-10-08-halogen-three-way/task-cards.md)
- [模型与版本来源](studies/2026-10-08-halogen-three-way/sources.json)
- [追加过度思考协议](studies/2026-10-08-halogen-three-way/overthinking-protocol.md) · [唯一答案短题](studies/2026-10-08-halogen-three-way/overthinking-tasks.json)
- [阶段数据，未完成不填成绩](studies/2026-10-08-halogen-three-way/summary.json) · [操作记录与限制](studies/2026-10-08-halogen-three-way/observations.md)

短题通过 `overthinking_runner.py` 读取进程环境连接兼容接口。当前结果仍在累积，文章与视频在全部配置完成后生成。
