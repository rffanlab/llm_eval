# Strata v0.1.44.1：Qwen3.8 Next Flash 在 RTX4060 Ti 与 AI Max+395 上的对照

实测日期：2026-10-15。两端主权重均为 `unsloth/Qwen3.8-Flash-Next-GGUF` 的 `UD-Q4_K_XL`，revision `38bb39ee97821de2c9009abb7e93950eec396e66`，四片共 111,334,654,784 字节。MTP、tokenizer 与主权重的逐文件指纹已比对；具体配置见 `environment/`。

## 为什么做

128GB 内存搭配 RTX4060 Ti 16GB 的老工作站，能否用最新版 Strata 完成与 Ryzen AI Max+395 相同的代码、工具和写作工作？除了生成速度，还比较完整等待、过度思考和连续项目的交付情况。两台整机的 CPU、内存与链路均不同，本研究不单独归因于显卡。

## 怎么做

- [冻结协议](protocol.md)：环境、任务预算、质量门槛与历史对照边界。
- [完整题面](task-cards.md)及[机器可读题面](tasks.json)：7类工作任务，每端2轮。
- [长程任务](long-horizon/task.json)：同一工作区与历史连续完成4个相互依赖的阶段，每端2次独立会话。
- [独立功能/Agent验收](short-suite/)与[长程验收](long-horizon/grade.py)：隐藏验收不回馈给被测模型。
- [速度输入](speed-prompts.json)：短输入512输出、约4K/32K输入，每端各3次；不计工作质量分。
- [来源冻结](freeze.json)：首次调用前保存的快照，`inference_started: false`描述保存时刻，不是当前进度。新增的汇总、审读与报告文件不属于冻结题面。
- [两端环境和身份](environment/)：主权重、MTP、tokenizer、引擎、编译工具链和配置。4060 Ti 驱动桌面，首次加载前固定预留1500MiB显存；共同上下文65536、int8 KV、spec4、串行1。

### 复跑入口

在对应主机先部署上述固定版本与文件，确认只有一套模型。设置 `EVAL_BASE_URL` 为本机 OpenAI 兼容 `/v1` 地址，`EVAL_MODEL=Qwen/Qwen3.8-Flash-Next`，`EVAL_API_KEY` 从环境注入，`EVAL_PROFILE` 为结果标签。`EVAL_GUARD_COMMAND` 是JSON数组形式的本机准入命令：每次调用前检查注册的API/引擎独占、已加载且空闲、可用内存至少8GiB、配置哈希与封存一致；成功输出JSON，失败返回非0。

[host_guard.py](host_guard.py)保留本次实际准入检查的只读实现。其部署根目录为`/srv/ai/services/strata-eval-20261015`；`private-profile.json`只含结果标签，`measured-private.json`为权限0600的本机服务配置，`sealed-identity.json`为调用前封存的身份。其他部署需按实际路径适配，密钥不写入命令行或公开文件。

一次发起并审读一个案例，保留已有目录，不能择优覆盖：

```sh
python short_runner.py --provider local --task C01 --round 1 --output results/short/rtx4060ti
python short_runner.py --provider local --task D01 --round 1 --variant depth --output results/short/rtx4060ti
python speed_runner.py --profile rtx4060ti --kind prompt4k --round 1 --output results/speed
python long-horizon/runner.py --provider local --profile rtx4060ti --round 1 --output results/long
```

写作及长程交付报告另由主评测代理按事实、完整、清楚、可用各0–5审读，总分至少16；[审读记录](editorial-review.json)绑定原文SHA。该审读并非盲审或真人验收。空正文、截断、超时、回合预算耗尽均保留；功能断言全过与完整交付分开报告。

## 结果文件

`summary.json` 由 `python summarize.py` 从保留的原始记录生成。`complete_collection` 表示计划的案例和审读是否全部收齐，不能当作通过率。缺失记录不补0或推算速度。API最终usage已返回的预算截断可以计入已知token；HTTP中断缺少最终usage的部分保持未知。

- 短题：`results/short/{profile}/{main|depth}/local/{task}-r{n}/`。
- 速度：`results/speed/{profile}/{kind}-r{n}/`。
- 长程：`results/long/{profile}/r{n}/`，含阶段快照、完整工具轨迹、最终文件与资源采样。
- [历史参考](historical-reference.json)：保留原日期、部署和失败口径；不混入本轮中位数。

本研究不调用远程 Token Plan API。库中不包含模型权重、服务密钥、内网登录信息或私有音色参考。

## 本期结果

每端14次短题、2次关闭思考、9次测速和2次长程，共54个案例、223次正式API调用；另4次接入检查不计分。全部收齐，不代表全部通过。

| 指标 | Qwen3.8 Next Flash / RTX4060 Ti 16GB整机 | Qwen3.8 Next Flash / AI Max+395 |
|---|---:|---:|
| 短题完整交付 | 10/14 | 12/14 |
| 长程最终文件正确 | 2/2 | 2/2 |
| 长程严格完整交付 | 0/2 | 0/2 |
| 长程完整等待中位（秒） | 871.8 | 586.0 |
| 固定512解码中位（token/s） | 31.9 | 44.8 |
| 4K预填充中位（token/s） | 321.8 | 438.3 |
| 32K预填充中位（token/s） | 620.2 | 499.1 |
| 32K完整API等待中位（秒） | 69.0 | 77.6 |

本轮综合优先AI Max+395：七类工作题等待均更短，严格JSON排障交付多两轮。4060 Ti整机的32K输入探针更快，未据此评价长文理解。两端复杂备忘录均0/2；长程均有阶段回复额度耗尽而缺少结束说明，不能推荐无人监督接管整项任务。

[全部API轮次计时](all-turn-timings.csv)包含首事件、首思考、首正文/工具、完整API等待、原生预填充/解码、缓存和token。[最终文件复核](final-artifact-audit.json)核对四份最终发布金额及各三项manifest SHA。[计时与评分口径](reporting-clarifications.md)披露套接字超时和冻结评分的关键词漏判；本期原始记录不覆盖。395的S4漏判不改变独立存在的S1预算失败。

[逐题、逐阶段Prefill/Decode对照](native-speeds.md)补齐七道工作题、D01关闭思考、长程S1–S4及整项、三类速度探针。每轮先求全部调用的原生token总量除以对应原生计算总秒数，再跨轮取中位；缓存复用另列。[70条聚合明细CSV](native-speeds.csv)与[原始来源SHA及完整口径JSON](native-speeds.json)可核对，离线执行`python aggregate_native_speeds.py`重建。长程整项与阶段组重叠，不能相加为调用总数。本次仅补报告，仍为223次正式调用、18个冻结文件，未增加推理或重评分。

同一模型在不同后端上的两轮差异是本组交付观察，不证明硬件改变模型智能。代理编辑不是盲审或真人批准。历史Gufo的63.5 token/s来自10月10日同512提示三次中位；框架、MTP、上下文及传输设置不同，作为历史部署参考。

[公众号逐题文章](publication/wechat-article.md) · [可复制富文本](publication/wechat-richtext.html) · [B站旁白脚本](publication/bilibili-script.md)。

[B站逐阶段速度表及实际时间轴](publication/bilibili-native-speed-panels.json)与文章使用同一份速度数据。视频对应任务加入独立Prefill/Decode表，完整交付与等待另表保留。

## PCIe规格澄清（同日补充）

第2槽为PCIe3.0 ×16，显卡确在SLOT2。RTX4060 Ti本身最多×8；3秒小内存传输时，两端均读到8GT/s、Width ×8，确认有效链路为PCIe3.0 ×8。空闲读到2.5GT/s是另一状态。[完整能力与状态证据](environment/rtx4060ti-pcie-clarification.json)与原始开测环境分别保留；本补充不计入模型测速，也不改变原成绩。
