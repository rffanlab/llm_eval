# Strata v0.2.2独立复测：RX7900 XTX / Qwen3.8 Next Flash

2026-10-22。最新产品发行 **v0.2.2**，内置引擎/Control **0.1.47**。发行资产与10月21日首测相同，本次重新运行模型调用；不能把同包复测差异写成新增版本优化。

## 为什么做

检验更新后是否缩短实际工作等待，区分生成速度、完整交付及运行波动。另补真实输入超过100K token的跨段材料题。

## 怎么做

- Dell Precision5820、Xeon W-2133、128GB DDR4-2133、RX7900 XTX24GB，配置功耗上限265W。
- Ubuntu24.04.5、kernel7.0.0-38；Qwen3.8 Next Flash，Unsloth UD-Q4_K_XL，部署ID `Qwen/Qwen3.8-Flash-Next`。
- 主测：context65536，prefill auto实际8192，expert-cache auto，spec4/min-p0.5，int8 KV、kv-resident32768、reserve1500，medium，temperature0，单并发、单模型。
- 完整沿用20份冻结源文件：七短题×2、D01无思考×2、四阶段连续项目×2、三组固定512生成吞吐×3，共27项；另2兼容检查不计分。
- 原生Prefill只计新输入、缓存另列；Decode含思考生成。每轮先汇总调用计数/原生计算秒，再取跨轮中位。完整等待包括API、工具与正常衔接，排除模型装载与事后验收。
- 写作四维0—5、至少16/20且过硬项，AI非盲审；连续项目须每阶段功能、收尾及最终文件一起通过。小样本、顺序执行，未随机交错。
- 长上下文单独context131072、两轮实际API输入各109148，其他显式参数保持；自动缓存分配可变化。历史两组未测该材料，不并入核心总分。

## 结果

|指标|旧引擎0.1.44.1 10/21|Strata v0.2.2首测10/21|Strata v0.2.2复测10/22|
|---|---:|---:|---:|
|短题完整交付|11/14|11/14|11/14|
|严格长程完整交付|0/2|0/2|0/2|
|最终文件正确|2/2|2/2|2/2|
|核心累计等待 秒|2120.9|1842.0|1721.5|
|固定512生成短输入Decode token/s|45.2|50.3|49.1|
|固定512生成4K输入Decode token/s|43.9|47.9|48.4|
|固定512生成32K输入Decode token/s|44.3|47.2|48.3|

综合推荐Strata v0.2.2：本轮固定Decode比旧引擎快8.6%—10.1%，七短题等待少22.5%，交付数保持。基础函数、调度、事实短讯与受控库存工具2/2通过。Prefill基本未改善，复杂备忘录0/2，严格JSON仍可能加围栏，连续项目S1仍缺阶段收尾。首测与复测用同一包，不能把两次快慢当成版本能力差异。

100K补充：两轮规则、四单金额及审批路径均正确；输出引用带DOC前缀，裸ID评分匹配五项失败，严格12/17、0/2完整交付。题面没有明确去前缀示例，记录验收契约歧义；语义诊断不替换冻结成绩。等待中位183.9秒，Prefill848.8、Decode45.2 token/s，缓存0。

本轮主测约32.7分钟、100K补充另7.5分钟，无新增ECC、驱动故障或重启。开始前系统CE2/UE0，历史错误不清零。265W配置回读不等于瞬时保证，主测PPT最高297W、补充340W，不是插座功耗；不据此诊断历史黑屏原因。

## 复跑与证据

- [完整逐题报告](comparison-report.md)：每题紧接表格与结论。
- [逐项三组CSV](comparison-by-unit.csv)、[逐调用原生计时](all-turn-timings.csv)、[原生计数审计](native-counter-audit.json)。
- [冻结题面](task-cards.md)、[连续项目](long-horizon/task.json)、[原始回复与工具轨迹](results/)。
- [100K完整材料与冻结哈希](long-context/)、[两轮计时](context-summary.json)、[引用契约说明](context-grader-observations.json)。
- [原始文件哈希](raw-manifest.json)、[核心源冻结](freeze.json)、[历史引用哈希](baseline-references.json)。
- [协议](retest-protocol.md)、[发行资产](release-assets.json)、[部署身份](deployment-identity.json)、[硬件](hardware-identity.json)。
- [编辑审读](editorial-review.json)、[最终文件独立核对](final-artifact-audit.json)、[原评分误判说明](grader-limitations.json)。

核心题面来自既有冻结基线commit `3c2a1fa0fec08c3009ab494e8c1cddab3c934220`，沿用原评分与预算。运行器入口 `short_runner.py`、`long-horizon/runner.py`、`speed_runner.py`、`long-context/runner.py`，参数见相应协议及 `--help`。合成代码工具按项目评测沙箱约束执行，不将模型生成代码作为可信工具安装。
