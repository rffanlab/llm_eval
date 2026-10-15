# AI Max+395 / Qwen3.8 Next Flash / Strata参数调优

## 为什么测

固定上一轮的Unsloth UD-IQ4_XS权重，检查专家缓存、Prefill计算路径与思考档位能否减少等待并保持任务完成度。

## 怎么测

同一128GB Ryzen AI Max+395 / Radeon 8060S，Strata0.1.44.1，64K上下文。先冻结四组运行候选、两档思考及质量门槛，再做16个固定输出速度案例、12个思考校准案例、28个短题确认案例和4个四阶段长程episode，共60个正式独立案例。长程16个阶段另列，测量CSV共76行；16次暖机不计分。

- [完整协议](protocol.md) · [冻结摘要](freeze.json)
- [全部短题提示词与评分](task-cards.md) · [原始题面JSON](tasks.json)
- [长程题面、工具与验收](long-horizon/README.md)
- [固定权重、revision与分片SHA](profiles.json) · [实际环境、完整参数与分配](environments.json)
- [速度选参](screen-selection.json) · [思考选参](effort-selection.json) · [确认前锁定方案](validation-plan.json)
- [计时探针参数口径补充](reporting-clarifications.md)

主测b0/b2均medium，温度0.3、top-p0.95、top-k20，同轮同seed；思考与正文共用输出预算。速度探针温度0、关闭思考、512实际生成token。只验证64K与这些候选，不声称全局最优。

## 测试结果

本轮通用配置推荐保留原参数b0与medium：它的七类短题交付数没有输，长程基础功能也更稳。加速参数b2把七题整组等待缩短32.0%，适合有独立测试的小函数、受控调度和一次预留等明确任务；需要逐项验收。四阶段项目的首阶段出现新增功能错误，未通过事前不退化门槛，因此不能作为全面替换方案。复杂试用备忘录两套都不合格，连续项目两套都未完整通过，仍须检查事实、约束和阶段收尾。

同一轮7短题合计、长程整episode统计后，再跨两轮取中位。P/D为原生新输入/生成token分别除以原生计算秒数；缓存复用另列，完整等待包括API/工具，独立隐藏验收另计。缺计时保留未知。

| Qwen3.8 Next Flash / UD-IQ4_XS / Strata配置 | 短题交付 | 7题等待秒 | 7题P token/s | 7题D token/s | 长程交付 | 长程等待秒 | 长程P token/s | 长程D token/s |
|---|---|---|---|---|---|---|---|---|
| b0-medium | 10/14 | 248.77 | 179.80 | 49.72 | 0/2 | 527.03 | 273.62 | 48.00 |
| b2-medium | 10/14 | 169.23 | 254.22 | 62.37 | 0/2 | 514.25 | 505.87 | 61.95 |

### 逐题、逐阶段与完整证据

- [公众号文章](publication/02-wechat-article.md) · [带复制标题和富文本按钮的HTML](publication/03-wechat-richtext.html)
- [B站视频](publication/video.mp4) · [视频旁白全文](publication/video-script.md)
- [全部76行测量记录](measurements.csv) · [逐题与阶段汇总](summary.json)
- [四组候选逐轮速度](screen-cases.csv) · [正式资源采样](resource-summary.json) · [启动耗时](startup-timings.json)
- [SHA绑定的助手编辑审读](editorial-review.json) · [最终发布文件核对](final-release-audit.json)
- [逐调用准入核验](admission-audit.json) · [全部原始文件SHA](raw-manifest.json)

助手编辑审读未盲审，不等于真人采用验收。功能检查、阶段预算与完整交付分开；后续修复和最终文件正确不能覆盖前一阶段失败。每套2轮，小样本不足以证明统计等效或全天稳定。

## 参数与复跑

本研究选择Strata，固定同一量化；不混入不同权重/引擎的结果。配置以[environments.json](environments.json)的portable_engine_args与env为准。`<source>`、`<weights>`、`<mtp>`和`<pack>`替换为各自部署路径。固定二进制与运行库来源均有摘要；模型准备遵循[对应版本Strata官方文档](https://github.com/Niko1221/Strata/blob/v0.1.44.1/docs/STRIX_HALO.md)。

共同参数为ctx65536、int8 KV、resident KV32768、resident预算55GiB、spec4、spec-min-p0.5、单并发。b0 expert-cache9015 / prefill auto；b2 expert-cache16000 / prefill auto:16384，另启用以下环境变量：

```bash
export STRATA_PF_FUSED=1 STRATA_PF_GEMM=1 STRATA_HC_UPMIX=1
export STRATA_PA_FAST=1 STRATA_HIP_WMMA=1 STRATA_SELECT_WMMA=1
export STRATA_HC_Q8=1 STRATA_PF_SWITCH_MIN_T=4096
export STRATA_PREFILL_STREAM_MIN=128
```

只设置这些变量不足以复跑整个评测，还须保持权重、MTP、引擎、模型ID、上下文、采样与预算相同。先启动一套配置并确保只有一个模型运行；将本地服务的地址、key、model和profile经环境变量提供给runner，并设置`EVAL_GUARD_COMMAND`为自动空闲/单模型/内存门槛检查。该命令须返回JSON快照，拒绝时非零退出。

```bash
# 服务准备完成，密钥通过已有安全环境配置提供，不写入题面或记录。
export EVAL_BASE_URL=http://127.0.0.1:YOUR_PORT/v1
export EVAL_MODEL=Qwen/Qwen3.8-Flash-Next
export EVAL_PROFILE=b0-medium
export EVAL_SEED=2026101601
export EVAL_GUARD_COMMAND='["python3","your_guard.py"]'
python short_runner.py --provider local --task C01 --round 1 --output ./private-results
python long-horizon/runner.py --provider local --profile b0-medium --round 1 --output ./private-long-results
```

每次使用新输出目录，保留首次失败，不覆盖原始attempt。冻结校验按字节进行。个人Token Plan不能用于无人值守批量套题；逐case发起与检查。离线聚合可在原始记录与SHA绑定审读齐全后运行`aggregate_results.py --final`。
