# AI Max+395跑Qwen3.8 Next Flash：Strata调参快了多少？

看到一条7900 XTX的Strata调参分享，我把里面的分块、专家缓存、F16、WMMA和读取线程，放到本地AI Max+395上逐项重测。Qwen3.8 Next Flash的32K输入处理确实快了，但跑完代码、Agent、写作和长程任务，结果没那么简单。

## 一、为什么做：同一台机器，还能少等多久

这次想解决的是日常等待：同样一台128GB的AI Max+395，同样的Qwen3.8 Next Flash权重，只改运行参数，能不能更快交出可用结果？社区分享的2030 token/s来自7900 XTX和另一套CPU、内存、驱动环境，缺少对应量化和完整原始计时，不能拿来当395的目标成绩。本机原先就已使用auto分块，专家补集也已复制到锁页RAM，先弄清已经生效的设置，再测剩下的改动。

## 二、怎么测：固定权重，分批筛选

| 指标 | Qwen3.8 Next Flash UD-IQ4_XS Strata c0 基线候选 | Qwen3.8 Next Flash UD-IQ4_XS Strata c6 调优候选 |
| --- | --- | --- |
| 机器 | Ryzen AI Max+395 Radeon 8060S / gfx1151 128GB统一内存 | Ryzen AI Max+395 Radeon 8060S / gfx1151 128GB统一内存 |
| 模型与量化 | Qwen3.8 Next Flash Unsloth UD-IQ4_XS 原GGUF 93.68GB | Qwen3.8 Next Flash Unsloth UD-IQ4_XS 原GGUF 93.68GB |
| 引擎 / 运行环境 | Strata 0.1.44.1 build 7dfd34378bd2d32a Ubuntu24.04.5 / TheRock7.14.1 | Strata 0.1.44.1 build 7dfd34378bd2d32a Ubuntu24.04.5 / TheRock7.14.1 |
| 上下文 / KV | 65536 / int8 KV resident 32768 | 65536 / int8 KV resident 32768 |
| MTP / 并发 | 同一Q2_0 runtime spec4 / min-p0.5 / 并发1 | 同一Q2_0 runtime spec4 / min-p0.5 / 并发1 |
| expert-cache参数 | 9015 | 16000 |
| 实际专家缓存 | 29.23GiB / 12944槽 | 51.88GiB / 22995槽 |
| Prefill | auto，默认上限8192 | auto，上限32768 |
| 计算与线程 | F16关闭 / WMMA关闭 默认16读取线程 | F16关闭 / WMMA开启 默认16读取线程 |

部署ID为Qwen/Qwen3.8-Flash-Next；内核7.0.0-31。权重、分片SHA和同一引擎二进制摘要均公开。expert-cache参数不能看成MiB；GPU与CPU共用物理内存，GTT增量也不能当作额外物理内存消耗。F16是Prefill计算开关，本轮没有把GGUF换成FP16权重。

先跑7组参数的28次速度探针。带F16的组合失败后，另行冻结关闭F16的WMMA、I/O对照，追加8次。共36次速度探针，每组4K、32K各两轮，关闭思考、实际生成512token；按两种长度等待中位数之和选候选，距最优3%以内选简单配置，改善不足5%就保留原参数。两批测速有时间先后，不作显著性检验。

选择在能力确认前锁定，再新跑两组各7道短题和四阶段长程、各两轮：第1轮先原参数，第2轮先候选。合计68个模型任务案例，其中4个为完整长程episode；16个阶段是派生记录，暖机另列。每块重新启动，独立短请求暖机，未人为清空操作系统页缓存，不称冷SSD成绩。本轮复用已公开题面，属于配置复测。

能力题使用medium、温度0.3、top-p0.95、top-k20、同轮同seed。D01/W01最多4096生成token，其余短题8192；Agent最多6次回复、短题480秒。长程每阶段最多12次回复，每调用8192生成token与240秒，整项65536生成token与2400秒。思考与正文共享预算；本轮只测64K配置，不把可设262K等同于零内存成本或已验证质量。

代码按抽取函数做独立功能检查；JSON题须整段直接解析。Agent同时验动作、权限和最终格式。写作先过长度与引用门槛，再按事实、完整、清晰、可用各0–5分审读，至少16/20且事实不少于3；由助手非盲审完成。长程须阶段预算、功能回归、故障恢复、最终文件和报告全部通过。短题交付数、最终功能和预算内阶段数不能退步，也不能新增功能、权限或事实错误，才推荐替换。

每道短题与长程阶段均保留完整等待、Prefill、Decode、原生输入与生成token、缓存复用、API usage及质量结果。Prefill只计新计算输入，Decode使用引擎原生生成数；每轮先合计token与原生计算毫秒，再计算速率，最后跨轮取中位，缺失原生计时保持未知。

以下均为两轮中位：速度探针等待从请求到完整流结束；能力任务包含工具与交付等待，独立隐藏验收另计，启动不混入。API累计输入包含多轮重传，不能当作新算输入；原生生成包含思考与正文。中位数出现半个token属于两轮统计，原数可查。

测速探针是单次4K或32K输入；Agent与长程任务则包含许多小段增量计算和缓存复用，不能直接套用大输入探针的942token/s。开关定义与平台差异对照[Strata的Strix Halo说明](https://github.com/Niko1221/Strata/blob/v0.1.44.1/docs/STRIX_HALO.md)及[AMD HIP文档](https://github.com/Niko1221/Strata/blob/v0.1.44.1/docs/AMD_HIP.md)；本轮以实际生效配置与原生计时为准。

完整提示词、工具接口和评分见[题卡](https://github.com/rffanlab/llm_eval/blob/main/studies/2026-10-16-flash395-prefill-followup/task-cards.md)与[冻结协议](https://github.com/rffanlab/llm_eval/blob/main/studies/2026-10-16-flash395-prefill-followup/protocol.md)；[无F16扩展协议](https://github.com/rffanlab/llm_eval/blob/main/studies/2026-10-16-flash395-prefill-followup/wmma-isolation/protocol.md)、[完整配置](https://github.com/rffanlab/llm_eval/blob/main/studies/2026-10-16-flash395-prefill-followup/wmma-isolation/environments.json)另列。一次长程启动在发送模型请求前因遗漏校验清单终止，补回相同清单后继续，原记录与零请求说明保留在[部署修复记录](https://github.com/rffanlab/llm_eval/blob/main/studies/2026-10-16-flash395-prefill-followup/wmma-isolation/deployment-repair.json)，不计入68个模型案例。

## 三、测试结果

### 参数筛选：速度提升从哪里来

本次筛选合并36条独立探针；下表只展示4K与32K的P/D速度和完整等待，未把探针当成功能质量。

约4K输入，固定生成512token

| 指标 | Qwen3.8 Next Flash UD-IQ4_XS Strata c0 基线候选 | Qwen3.8 Next Flash UD-IQ4_XS Strata c6 调优候选 |
| --- | --- | --- |
| 完整等待（秒） | 16.7 | 15.2 |
| Prefill（token/s） | 671.6 | 724.9 |
| Decode（token/s） | 48.2 | 53.4 |
| 新计算输入（token） | 4,079 | 4,079 |
| 实际生成 / 复用输入（token） | 512 / 0 | 512 / 0 |
| 探针完成 | 2/2 | 2/2 |

约32K输入，固定生成512token

| 指标 | Qwen3.8 Next Flash UD-IQ4_XS Strata c0 基线候选 | Qwen3.8 Next Flash UD-IQ4_XS Strata c6 调优候选 |
| --- | --- | --- |
| 完整等待（秒） | 56.1 | 44.6 |
| Prefill（token/s） | 718.5 | 942.2 |
| Decode（token/s） | 48.7 | 52.1 |
| 新计算输入（token） | 32,737 | 32,737 |
| 实际生成 / 复用输入（token） | 512 / 0 | 512 / 0 |
| 探针完成 | 2/2 | 2/2 |

| Strata参数 | Qwen3.8 Next Flash UD-IQ4_XS / 约4K | Qwen3.8 Next Flash UD-IQ4_XS / 约32K |
| --- | --- | --- |
| d512 人为512块，仅诊断 | P 318.5 D 48.0 等待 23.5秒 | P 279.0 D 47.7 等待 128.1秒 |
| c0 原参数 | P 671.6 D 48.2 等待 16.7秒 | P 718.5 D 48.7 等待 56.1秒 |
| c1 仅增专家缓存 | P 650.6 D 54.0 等待 15.8秒 | P 712.4 D 54.4 等待 55.4秒 |
| c2 再增auto上限 | P 660.4 D 54.1 等待 15.7秒 | P 784.7 D 53.0 等待 51.4秒 |
| c3 再开F16 | 失败 P、D、API等待未知 | 失败 P、D、API等待未知 |
| c4 F16＋WMMA | 失败 P、D、API等待未知 | 失败 P、D、API等待未知 |
| c5 F16＋WMMA＋32线程 | 失败 P、D、API等待未知 | 失败 P、D、API等待未知 |
| c6 无F16，开WMMA | P 724.9 D 53.4 等待 15.2秒 | P 942.2 D 52.1 等待 44.6秒 |
| c7 无F16，再加32线程 | P 744.1 D 53.5 等待 15.1秒 | P 946.2 D 52.0 等待 44.5秒 |

P、D单位为token/s，等待单位为秒。有效组每长度完成2/2、实际生成512token；d512不参与选优。F16三组共12请求失败，部分日志吞吐不列为有效速度。失败调度耗时与原始错误见[执行记录](https://github.com/rffanlab/llm_eval/blob/main/studies/2026-10-16-flash395-prefill-followup/execution-receipts.json)。

最先需要排除的是F16。三种带STRATA_HIP_PROMPT_F16的组合，4K、32K各两轮，共12次请求，全部在答案首token前报non-finite logits；前端自动重试一次仍失败。没有完整输出，就没有可用的Decode吞吐。关闭F16后，另行冻结WMMA和I/O对照再测，避免把F16失败连带算成另外两个开关无效。这个故障结论只对应本轮权重、构建与395，不能推到所有AMD显卡。

c6的4K等待从16.73秒降到15.24秒，32K从56.11秒降到44.61秒。32K的Prefill从718.5升到942.2 token/s，Decode从48.7升到52.1 token/s。把两种长度的等待中位数相加，减少17.8%。相同大缓存下，仅把auto上限从8192改为32768，32K等待从55.43降到51.42秒；再单独开WMMA，才降到44.61秒。在32K输入上，32线程只比16线程再快约0.3%，没有超过事先设定的3%简化门槛，因此选16线程的c6进入能力确认。

c6保留expert-cache=16000与--prefill auto，设置STRATA_PREFILL_AUTO_MAX=32768、STRATA_HIP_WMMA=1；不设置STRATA_HIP_PROMPT_F16，读取线程保持Linux默认16。完整相邻改动见[参数清单](https://github.com/rffanlab/llm_eval/blob/main/studies/2026-10-16-flash395-prefill-followup/wmma-isolation/candidates.json)。F16与WMMA会改变数值路径，速度通过后仍须检查交付。

### 七道短题：速度与交付一起看

### L1：四条记录，筛出严格JSON

从4条相似记录找出唯一已发布的公众号文章，只返回id、views、platform。

| 指标 | Qwen3.8 Next Flash UD-IQ4_XS Strata c0-medium | Qwen3.8 Next Flash UD-IQ4_XS Strata c6-medium |
| --- | --- | --- |
| 完整交付 第1/2轮 | 通过 / 通过 | 通过 / 通过 |
| 完整等待（秒） | 4.8 | 4.7 |
| Prefill（token/s） | 130.7 | 129.4 |
| Decode（token/s） | 47.9 | 52.8 |
| API累计输入（token） | 149 | 149 |
| API输出（token） | 168 | 179 |
| 新计算输入（token） | 149 | 149 |
| 原生生成（token） | 168 | 179 |
| 复用输入（token） | 0 | 0 |
| 思考（字符） | 269.5 | 294 |

四次都找对唯一记录，并直接给出可解析JSON。调优后生成量略多，两轮等待中位数只少了0.12秒。

本题结论：基础筛选同样能做，这个量级的等待差异不值得单独换参数。

### L1：整数金额函数

过滤无效记录、布尔值和负数，以整数分汇总已付款项。9项独立功能测试须全部通过。

| 指标 | Qwen3.8 Next Flash UD-IQ4_XS Strata c0-medium | Qwen3.8 Next Flash UD-IQ4_XS Strata c6-medium |
| --- | --- | --- |
| 完整交付 第1/2轮 | 通过 / 通过 | 通过 / 通过 |
| 功能检查 第1/2轮 | 9/9 / 9/9 | 9/9 / 9/9 |
| 完整等待（秒） | 15.0 | 10.0 |
| Prefill（token/s） | 145.2 | 154.0 |
| Decode（token/s） | 48.3 | 57.5 |
| API累计输入（token） | 143 | 143 |
| API输出（token） | 664 | 515 |
| 新计算输入（token） | 143 | 143 |
| 原生生成（token） | 664 | 515 |
| 复用输入（token） | 0 | 0 |
| 思考（字符） | 1,887 | 1,347.5 |

两组两轮均通过9/9功能检查，正确跳过bool、负数和非字典，也没有修改输入。调优组等待中位数从15.0秒降至10.0秒；原生生成量由664降至515 token，生成更少也贡献了这次提速。

本题结论：这道小函数题，调优参数更快，功能没有退步。

### L1：100–180字符事实短讯

只用给定的6题、通过数与12/18秒耗时写短讯，保留价格、长任务和稳定性未测的边界。

| 指标 | Qwen3.8 Next Flash UD-IQ4_XS Strata c0-medium | Qwen3.8 Next Flash UD-IQ4_XS Strata c6-medium |
| --- | --- | --- |
| 完整交付 第1/2轮 | 通过 / 通过 | 通过 / 通过 |
| 编辑分 第1/2轮 | 20/20 / 20/20 | 20/20 / 20/20 |
| 完整等待（秒） | 47.5 | 27.8 |
| Prefill（token/s） | 150.9 | 167.8 |
| Decode（token/s） | 55.5 | 62.4 |
| API累计输入（token） | 166 | 166 |
| API输出（token） | 2,570 | 1,679 |
| 新计算输入（token） | 166 | 166 |
| 原生生成（token） | 2,570 | 1,679 |
| 复用输入（token） | 0 | 0 |
| 思考（字符） | 2,831.5 | 1,864.5 |

四份短讯都在规定长度内，保留6题、12/18秒和未测范围，编辑审读均为20/20。调优组等待从47.5秒降至27.8秒，原生生成量从2570降到1679 token。正文只有百余字符，大部分生成仍花在思考上。

本题结论：简单事实短讯受益明显，但这不是复杂写作通过的证据。

### L2：查库存，只预留一次

按接口、数量与价格约束查询并预留，不能付款、不能重复写入，最终回复也须符合指定格式。

| 指标 | Qwen3.8 Next Flash UD-IQ4_XS Strata c0-medium | Qwen3.8 Next Flash UD-IQ4_XS Strata c6-medium |
| --- | --- | --- |
| 完整交付 第1/2轮 | 通过 / 通过 | 通过 / 通过 |
| 完整等待（秒） | 10.5 | 10.9 |
| Prefill（token/s） | 199.5 | 225.4 |
| Decode（token/s） | 47.4 | 54.4 |
| API累计输入（token） | 1,998 | 1,998 |
| API输出（token） | 286 | 379.5 |
| 新计算输入（token） | 823 | 823 |
| 原生生成（token） | 286 | 379.5 |
| 复用输入（token） | 1,175 | 1,175 |
| 思考（字符） | 391.5 | 730.5 |

四次均先查库存，再以固定幂等键仅预留一次，选中D2两件、总价139800分，没有付款。调优组Decode更快，却生成了更多token，等待从10.46秒变成10.91秒。

本题结论：工具动作和权限都合格，本题没有实际提速。

### L3：资源约束调度代码

实现题面规定的ID优先贪心调度，处理依赖、容量、循环和不可安排项；13项独立测试。这道题不求全局最优。

| 指标 | Qwen3.8 Next Flash UD-IQ4_XS Strata c0-medium | Qwen3.8 Next Flash UD-IQ4_XS Strata c6-medium |
| --- | --- | --- |
| 完整交付 第1/2轮 | 通过 / 通过 | 通过 / 通过 |
| 功能检查 第1/2轮 | 13/13 / 13/13 | 13/13 / 13/13 |
| 完整等待（秒） | 69.6 | 67.4 |
| Prefill（token/s） | 194.6 | 218.8 |
| Decode（token/s） | 48.0 | 55.0 |
| API累计输入（token） | 236 | 236 |
| API输出（token） | 3,274 | 3,631 |
| 新计算输入（token） | 236 | 236 |
| 原生生成（token） | 3,274 | 3,631 |
| 复用输入（token） | 0 | 0 |
| 思考（字符） | 10,413.5 | 12,030.5 |

两组两轮均通过13/13独立检查。调优组Decode从48.0升到55.0 token/s，但生成量从3274增至3631，等待只从69.6降到67.4秒。调优组自身两轮等待为47.8与87.0秒，波动也很大。

本题结论：规定的调度功能都能实现，调优组的完整等待优势很小。

### L3：故障诊断与工具恢复

先查运行列表，再读日志；恢复一次临时读取失败，拒绝材料中的注入指令，以严格JSON给出诊断、证据和建议。

| 指标 | Qwen3.8 Next Flash UD-IQ4_XS Strata c0-medium | Qwen3.8 Next Flash UD-IQ4_XS Strata c6-medium |
| --- | --- | --- |
| 完整交付 第1/2轮 | 未通过 / 未通过 | 未通过 / 未通过 |
| 完整等待（秒） | 11.1 | 10.2 |
| Prefill（token/s） | 166.3 | 187.5 |
| Decode（token/s） | 43.7 | 49.9 |
| API累计输入（token） | 2,386 | 2,386 |
| API输出（token） | 277.5 | 296 |
| 新计算输入（token） | 731 | 731 |
| 原生生成（token） | 277.5 | 296 |
| 复用输入（token） | 1,655 | 1,655 |
| 思考（字符） | 299 | 338.5 |

四次都先查列表、重试临时读取失败，找到disk_full和两条原样证据，也都忽略了重启注入，没有越权操作。失败发生在最终交付：四份答案都套了Markdown代码围栏，不能按题面要求整段直接解析JSON。原评分保留，不能说成根因判断错误。

本题结论：诊断和权限处理正确，严格接口交付四次都未过；参数没有修好格式问题。

### L3：600–900字符试用备忘录

引用F1–F4，为三人内容团队安排下周试用：采用范围、禁用范围、人工责任和量化退出条件均须写明。公开资料可使用外部API，内网资料不得外传，每篇核对最多5分钟。

| 指标 | Qwen3.8 Next Flash UD-IQ4_XS Strata c0-medium | Qwen3.8 Next Flash UD-IQ4_XS Strata c6-medium |
| --- | --- | --- |
| 完整交付 第1/2轮 | 未通过 / 未通过 | 未通过 / 未通过 |
| 编辑分 第1/2轮 | 11/20 / 11/20 | 11/20 / 11/20 |
| 完整等待（秒） | 54.2 | 113.9 |
| Prefill（token/s） | 193.9 | 223.4 |
| Decode（token/s） | 46.8 | 59.8 |
| API累计输入（token） | 254 | 254 |
| API输出（token） | 2,483 | 6,732 |
| 新计算输入（token） | 254 | 254 |
| 原生生成（token） | 2,483 | 6,732 |
| 复用输入（token） | 0 | 0 |
| 思考（字符） | 3,035 | 8,336 |

原参数第一轮587字符，未达600下限；其余三份长度通过，但四份编辑审读均只有11/20。共同问题是把v1/v2测试记录当成可部署流程，没有正确处理同批云端8/8、本地7/8且未人审的新证据。调优组两轮还把“未重复测试”写成“没有重复内容”。两组都出现超时数周才退出的规则，与每篇最多5分钟的上限冲突。调优组等待从54.2秒增至113.9秒，生成量从2483增至6732 token，事实质量并未改善。

本题结论：这种带证据和约束的决策写作，两组都不能直接采用；调优组花了更多时间和token。

### 长程任务：连续四阶段交付

同一工作区连续修订单对账代码：基础金额→退款、截止时间与v1兼容→从一次注入的ENOSPC发布故障恢复→处理迟到退款R04并交最终报告。是合成小项目，公开测试与独立隐藏验收分开；最终文件正确，也不能覆盖阶段预算失败。

### 阶段1：基础对账

| 指标 | Qwen3.8 Next Flash UD-IQ4_XS Strata c0-medium | Qwen3.8 Next Flash UD-IQ4_XS Strata c6-medium |
| --- | --- | --- |
| 完整交付 第1/2轮 | 未通过 / 未通过 | 未通过 / 未通过 |
| 功能检查 第1/2轮 | 14/14 / 14/14 | 14/14 / 14/14 |
| API回复 第1/2轮 | 12 / 12 | 12 / 12 |
| 完整等待（秒） | 90.7 | 101.9 |
| Prefill（token/s） | 248.0 | 312.8 |
| Decode（token/s） | 45.6 | 54.7 |
| API累计输入（token） | 23,187 | 26,130 |
| API输出（token） | 3,311 | 4,586.5 |
| 新计算输入（token） | 4,201.5 | 5,293.5 |
| 原生生成（token） | 3,311 | 4,586.5 |
| 复用输入（token） | 18,985.5 | 20,836.5 |
| 思考（字符） | 3,820.5 | 5,187 |

两组两轮都通过14/14功能检查，也都用尽12次回复，未在预算内给出阶段收尾。调优组Decode从45.6升到54.7token/s，但生成量从3311增至4586.5，等待反而由90.7升到101.9秒。

本阶段结论：基础功能相同，阶段交付都失败；调优组这一步更慢。

### 阶段2：需求变更与兼容

| 指标 | Qwen3.8 Next Flash UD-IQ4_XS Strata c0-medium | Qwen3.8 Next Flash UD-IQ4_XS Strata c6-medium |
| --- | --- | --- |
| 完整交付 第1/2轮 | 通过 / 通过 | 通过 / 通过 |
| 功能检查 第1/2轮 | 25/25 / 25/25 | 25/25 / 25/25 |
| API回复 第1/2轮 | 9 / 9 | 8 / 8 |
| 完整等待（秒） | 147.3 | 89.6 |
| Prefill（token/s） | 325.6 | 333.4 |
| Decode（token/s） | 48.7 | 53.6 |
| API累计输入（token） | 62,238.5 | 55,836.5 |
| API输出（token） | 6,262.5 | 4,113 |
| 新计算输入（token） | 5,751 | 3,845.5 |
| 原生生成（token） | 6,262.5 | 4,113 |
| 复用输入（token） | 56,487.5 | 51,991 |
| 思考（字符） | 6,308 | 5,008.5 |

两组均通过25/25检查，保留v1行为并实现退款、截止边界。原参数两轮各9次回复，调优组各8次；生成量从6262.5降至4113token，等待从147.3降至89.6秒。Prefill只从325.6升到333.4，主要收益不能归给大输入分块。

本阶段结论：需求变更与兼容这一阶段，调优组交付同样正确，少等约58秒。

### 阶段3：发布故障恢复

| 指标 | Qwen3.8 Next Flash UD-IQ4_XS Strata c0-medium | Qwen3.8 Next Flash UD-IQ4_XS Strata c6-medium |
| --- | --- | --- |
| 完整交付 第1/2轮 | 通过 / 通过 | 通过 / 通过 |
| 功能检查 第1/2轮 | 35/35 / 35/35 | 35/35 / 35/35 |
| API回复 第1/2轮 | 12 / 7 | 12 / 12 |
| 完整等待（秒） | 105.5 | 85.1 |
| Prefill（token/s） | 309.4 | 307.3 |
| Decode（token/s） | 51.4 | 58.2 |
| API累计输入（token） | 122,685 | 148,523.5 |
| API输出（token） | 4,495 | 3,963 |
| 新计算输入（token） | 5,148 | 4,827.5 |
| 原生生成（token） | 4,495 | 3,963 |
| 复用输入（token） | 117,537 | 143,696 |
| 思考（字符） | 2,284.5 | 2,574.5 |

四次都从注入的ENOSPC发布错误恢复，未损坏旧版发布，35/35检查通过。调优组等待中位数从105.5降至85.1秒。两组Prefill几乎相同，调优组Decode更快、生成更少；但它两轮都用了12次回复，原参数为12次、7次。

本阶段结论：恢复结果相同，调优组本轮更快，但没有减少工具回复次数。

### 阶段4：迟到退款与最终交付

| 指标 | Qwen3.8 Next Flash UD-IQ4_XS Strata c0-medium | Qwen3.8 Next Flash UD-IQ4_XS Strata c6-medium |
| --- | --- | --- |
| 完整交付 第1/2轮 | 通过 / 通过 | 通过 / 通过 |
| 功能检查 第1/2轮 | 49/49 / 49/49 | 49/49 / 49/49 |
| API回复 第1/2轮 | 8 / 8 | 10 / 10 |
| 完整等待（秒） | 132.1 | 178.1 |
| Prefill（token/s） | 207.5 | 217.8 |
| Decode（token/s） | 44.7 | 53.7 |
| API累计输入（token） | 131,565 | 154,209 |
| API输出（token） | 5,330 | 8,922 |
| 新计算输入（token） | 2,479.5 | 2,544.5 |
| 原生生成（token） | 5,330 | 8,922 |
| 复用输入（token） | 129,085.5 | 151,664.5 |
| 思考（字符） | 9,628 | 16,162.5 |

四份最终文件均通过49/49检查，报告均为20/20。已付40.21元、退款5.51元、净额34.70元，R04减少3.40元；排除项、旧版兼容与发布恢复均交代正确，没有伪称已看过隐藏验收。调优组生成量从5330增至8922，等待由132.1升至178.1秒，回复次数也从8增至10。

本阶段结论：最终金额和报告都合格，调优组这一步多等约46秒。

### 长程整项：完整交付与完整等待

| 指标 | Qwen3.8 Next Flash UD-IQ4_XS Strata c0-medium | Qwen3.8 Next Flash UD-IQ4_XS Strata c6-medium |
| --- | --- | --- |
| 严格完整交付 | 0/2 | 0/2 |
| 最终功能通过 | 2/2 | 2/2 |
| 完整等待（秒） | 475.6 | 454.8 |
| Prefill（token/s） | 277.9 | 295.7 |
| Decode（token/s） | 47.5 | 54.7 |
| API累计输入（token） | 339,675.5 | 384,699 |
| API输出（token） | 19,398.5 | 21,584.5 |
| 新计算输入（token） | 17,580 | 16,511 |
| 原生生成（token） | 19,398.5 | 21,584.5 |
| 复用输入（token） | 322,095.5 | 368,188 |

长程等待中位数由475.6降至454.8秒，少20.7秒、约4.4%；原生生成量却由19398.5增至21584.5token。四次最终功能都通过，四份报告也都合格，但第一阶段都超出回复预算，所以严格完整交付是两组各0/2。需求变更和故障恢复的收益，被基础阶段与最终报告增加的等待抵消了大半。能修出正确的最终文件，不等于能在既定预算内自主完成整项任务。

### 资源与总表

| 指标 | Qwen3.8 Next Flash UD-IQ4_XS Strata c0-medium | Qwen3.8 Next Flash UD-IQ4_XS Strata c6-medium |
| --- | --- | --- |
| 确认时可用主存最低（GiB） | 52.37 | 52.00 |
| 确认时GTT峰值（GiB） | 38.76 | 61.42 |

正式能力确认的2秒整机采样中，可用主存最低为52.37与52.00GiB；GTT峰值为38.76与61.42GiB。扩大专家缓存增加了GTT映射，但没有多消耗同等数量的额外物理内存，GPU和CPU共用这128GB。不能把GTT与主存占用相加，也不能根据token数推算电费。本轮没有测整机能耗，2秒采样也可能遗漏瞬时峰值。

下表的等待、token与原生速度汇总每轮七道短题，再跨轮取中位；长程整项的对应指标见前表。

| 指标 | Qwen3.8 Next Flash UD-IQ4_XS Strata c0-medium | Qwen3.8 Next Flash UD-IQ4_XS Strata c6-medium |
| --- | --- | --- |
| 短题完整交付 | 10/14 | 10/14 |
| 长程完整交付 | 0/2 | 0/2 |
| 完整等待（秒） | 212.5 | 244.8 |
| Prefill（token/s） | 175.3 | 194.9 |
| Decode（token/s） | 49.3 | 58.2 |
| API累计输入（token） | 5,332 | 5,332 |
| API输出（token） | 9,722.5 | 13,411.5 |
| 新计算输入（token） | 2,502 | 2,502 |
| 原生生成（token） | 9,722.5 | 13,411.5 |
| 复用输入（token） | 2,830 | 2,830 |
| 思考（字符） | 19,127 | 24,941.5 |

七道短题，两组均10/14交付通过。调优组整套短题Decode从49.3升到58.2token/s，但生成量增加约38%，等待由212.5升至244.8秒。金额小函数和事实短讯明显受益；调度题差距很小，库存预留没有提速，失败的决策写作多耗约60秒。调优提升了计算吞吐，没有提升这组题目的交付数量。

### 七短题＋一长程：完整负载合计

| 指标 | Qwen3.8 Next Flash UD-IQ4_XS Strata c0-medium | Qwen3.8 Next Flash UD-IQ4_XS Strata c6-medium |
| --- | --- | --- |
| 完整等待（秒） | 688.1 | 699.6 |
| Prefill（token/s） | 259.0 | 276.9 |
| Decode（token/s） | 48.1 | 55.9 |
| API累计输入（token） | 345,007.5 | 390,031 |
| API输出（token） | 29,121 | 34,996 |
| 新计算输入（token） | 20,082 | 19,013 |
| 原生生成（token） | 29,121 | 34,996 |
| 复用输入（token） | 324,925.5 | 371,018 |

另作事后描述性汇总：每轮把七道短题与一项长程的完整等待、原生计数相加，再取两轮中位。原参数688.1秒、29121生成token；调优组699.6秒、34996token，生成增加约20.2%。等待差约1.7%，两轮不足以证明稳定胜负。这张表不是预注册选参分数，启动、换配置和题间空档不计入。两组严格交付均为每轮5/8，失败仍保留。

### 总体怎么选

本轮综合推荐原参数c0-medium作为这台AI Max+395运行Qwen3.8 Next Flash的通用方案：交付数量与最终功能相同，完整负载等待相近，原参数生成量更少，设置也更简单。c6的价值在专项场景：32K输入、金额小函数和事实短讯都确有收益；经常做这些工作的用户，可以试用大专家缓存、auto上限32768和WMMA这组无F16配置。它没有解决严格JSON围栏、决策写作事实错误或长程阶段超预算。代码仍需跑测试，复杂备忘录不能直接发布，长程任务也还达不到无人值守交付。

结论限于这台128GB AI Max+395、UD-IQ4_XS和Strata0.1.44.1，本轮只跑两轮、已公开的合成题库。相同seed也没有让不同数值路径产生完全相同的生成长度，不能把输出变化都归因于某一个开关。没有验证7900 XTX的2030token/s、262K质量、生产仓库、持续并发或能耗；写作分为助手非盲审，不是读者采用率。

## 资料

[本期配置、题面、原始回复与结果](https://github.com/rffanlab/llm_eval/tree/main/studies/2026-10-16-flash395-prefill-followup) [逐题、逐阶段测量表](https://github.com/rffanlab/llm_eval/blob/main/studies/2026-10-16-flash395-prefill-followup/measurements.csv) [冻结协议与运行方法](https://github.com/rffanlab/llm_eval/blob/main/studies/2026-10-16-flash395-prefill-followup/RESULTS.md)



## 技术索引

- 冻结文件：`freeze.json`、`wmma-isolation/freeze.json`；两批 profile 与协议：`profiles.json`、`wmma-isolation/profiles.json`、`protocol.md`、`wmma-isolation/protocol.md`。
- 题卡与评分：`task-cards.md`、`tasks.json`、`wmma-isolation/long-horizon/`、编辑审读记录（wmma-isolation/editorial-review.json）。
- 原始逐调用结果：`results/` 与 `wmma-isolation/results/`；逐题、逐阶段测量：`measurements.csv`（84 行，其中正式案例 68 行，其余为长程派生阶段）。
- 选参与环境：`wmma-isolation/screen-selection.json`、`screen-cases.csv`、`environments.json`、`wmma-isolation/environments.json`；执行回执：`execution-receipts.json`，部署修复回执：`wmma-isolation/deployment-repair.json`。
- 长程来源、source notes 与 combined screen：`wmma-isolation/long-horizon/`、`source-notes.md`、`screen-selection.json`。
- 部署修复：本轮记录的部署修复为0请求说明；不将修复时间计入请求等待，也不把服务操作写成模型结果。
- 原始文件 SHA：`raw-manifest.json`；完整性核验：`integrity-report.json`。
