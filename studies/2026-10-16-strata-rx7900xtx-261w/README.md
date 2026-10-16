# Qwen3.8 Next Flash：7900 XTX 261W、4060 Ti与AI Max+395

2026-10-16，RX7900 XTX在驱动支持的最低功耗控制值261W下重新完成27项案例。两方参照为2026-10-15封存的同题记录，未混入上一轮中断的7900 XTX结果。

## 为什么测

128GB内存的Xeon工作站从RTX4060 Ti 16GB换成RX7900 XTX 24GB，实际代码、工具、写作与连续项目能省多少等待？与128GB本地Ryzen AI Max+395相比，哪些工作更适合哪台机器？

## 怎么测

- 三端均为Qwen3.8 Next Flash，`unsloth/Qwen3.8-Flash-Next-GGUF`的UD-Q4_K_XL，主权重111.3GB；同版Strata v0.1.44.1。
- 7类工作题各2轮，4阶段连续项目2轮，关闭思考的D01补测2轮，以及3档速度各3次，共27项案例。
- 题面、工具、预算、验收源码与历史基线一致；先核对冻结文件，再运行。
- Prefill仅计新计算输入；Decode按原生生成数。先合并一轮各调用的token与原生计算秒数，再取跨轮中位。完整任务等待另列。
- 代码采用独立功能验收；写作由评测代理进行四维编辑审读，未做盲审；最终文件正确与完整流程交付分别记录。
- 订单、客户代号、金额均为公开合成夹具，没有真实客户业务记录。

入口：[完整任务卡与提示词](task-cards.md)、[冻结清单](freeze.json)、[261W条件](power-condition-protocol.md)、[继承协议](extension-protocol.md)、[环境与权重](environment/)、[历史基线来源](baseline-references.json)。

## 结果

| 指标 | Qwen3.8 Next Flash / 4060 Ti | Qwen3.8 Next Flash / 7900 XTX 261W | Qwen3.8 Next Flash / AI Max+395 |
|---|---:|---:|---:|
| 短题完整交付 | 10/14 | 12/14 | 12/14 |
| 长程严格完整交付 | 0/2 | 0/2 | 0/2 |
| 长程最终文件正确 | 2/2 | 2/2 | 2/2 |
| 长程完整等待，中位秒 | 871.77 | 645.00 | 586.01 |
| 32K Prefill，token/s | 620.2 | 933.9 | 499.1 |
| 32K Decode，token/s | 31.7 | 44.0 | 42.0 |
| 32K API等待，中位秒 | 69.01 | 46.78 | 77.65 |

本轮日常工作综合推荐AI Max+395：成功短题和长程整项等待更短。7900 XTX的无缓存4K、32K输入计算最强，多个任务也比4060 Ti省等待。复杂备忘录三端均未交付；长程文件虽正确，阶段收尾仍会耗尽回复额度。

395的长程S4存在已保留的旧评分器关键词漏判，[语义说明](grading-clarification.json)不修改冻结原分；即便修正该项，S1阶段的收尾失败仍使整项不满足严格门槛。

## 功耗观察的边界

正式任务窗口约47.2分钟，含工具及任务间隔；1415条采样中的控制值始终为261W，但`power1_average`有7条高于它，最高270W。边缘最高59℃，热点78℃；新增ECC为0，未见新GPU驱动故障或重启。

没有测整机插座功耗，也未验证持续满载稳定性或此前黑屏的原因。详见[硬件观察](hardware-observation.json)及[采样记录](hardware-telemetry.jsonl)。

## 复核与展示

- [完整三方汇总](summary.json)、[解释性结论](findings.json)
- [逐题、逐阶段原生速度](native-speeds.csv)、[逐API调用计时](all-turn-timings.csv)
- [原始回复、工具轨迹与产物](results/)、[最终文件独立审查](final-artifact-audit.json)、[编辑审读](editorial-review.json)
- [公众号富文本页面](publication/wechat-richtext.html)、[文章文本](publication/wechat-article.md)

文章和视频中每题、长程每阶段均紧接结果与结论，包含原生Prefill/Decode、完整等待、交付与token。速度探针只评吞吐，不代表长文理解质量。新视频使用已授权的Qwen3-TTS本人音色，无音乐与音效；私密音色参考不在此仓库。
