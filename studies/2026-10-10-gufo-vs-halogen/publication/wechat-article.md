# 本地 AI Max+395 跑千问：Gufo 与 Halogen 实测对比

## 一、为什么做

有网友建议我试试“gofu”：跑Q4_K_XL，精度比Halogen高，速度还差不多。我找到描述吻合的Gufo项目，把它装到本地Ryzen AI Max+395上，继续用公开仓库里的同一套工作题测试。

这次要看三件事：原来能完成的工作有没有退步，更大的权重能不能多完成一些，以及多出来的等待和token值不值。另加开关思考对照，看看千问会不会在简单任务上想得太多。

## 二、怎么测

机器是**Ryzen AI Max+395、128GB内存、内置Radeon8060S**。系统Ubuntu24.04.5，内核7.0.0-31-generic，ROCm7.2.1；Gufo用GCC13、CMake3.28.3、Ninja1.11.1按官方release配置编译。源码、工具链与权重SHA都单独记录。

| 部署 | 主模型量化 | 辅助与上下文 |
| --- | --- | --- |
| Halogen 0.9.1 | Qwen3.8-Flash-Next / HGN W4B＋overlay | 原MTP / 262144 / 原110MB提示缓存 |
| Gufo 0.11.0 | Qwen3.8-Flash-Next / Unsloth UD-Q4_K_XL | shared-Q8_0 MTP / 262144 / 1GiB RAM快照缓存 |

Gufo主GGUF四个分片合计**111.33GB（103.69GiB）**，MTP辅助权重另有2.79GB。它使用Gufo0.11.0的固定提交，直接读取原GGUF。Halogen使用本地机器当前的0.9.1部署。两套框架、量化、辅助权重和缓存不同，本期比较整套部署的工作表现，不能据此证明Q4_K_XL的BF16数值精度更高。

USB4外卡保持连接，但本轮重启后未枚举出7900XTX，实际计算全部在8060S上。第一次加载Gufo时，GPU可分配上限只有约62.5GiB，报了第38层hipMalloc失败，尚未开始答题。将ttm.pages_limit设为30408704，即116GiB，并重启。两端都在这次启动的同一环境重测；旧基线和首次失败另存，未混入下面的数据。

一次只加载一个模型，切换前确认进程退出、内存和GPU分配回落。每个请求前检查单模型、就绪和至少8GiB可用内存。Gufo计时阶段可用内存最低约30.7GiB，GTT峰值约90.7GiB，所选运行日志中未出现新的OOM或GPU reset。

**十类题，16次主会话。**三个进阶题各重复三次，其余各一次。题目包含独立Python函数、合成工具调用、资料台账和写作；还没测大型真实仓库修复或生产Agent。温度0、存在惩罚0、medium思考，保留其他消息但不保留历史思考。数据/写作输出预算2048—8192token，Agent最多6轮共享8192，完整预算含思考。

代码必须通过全部独立功能测试；Agent核对工具顺序、权限、金额和最终严格JSON；写作先查字数、段落、来源和事实，再按事实忠实、信息完整、结构清晰、可用性四项各5分审读，至少16/20才算合格。编辑分是代理审读，不是本人验收。D01/C01/W01/C02/A01完整等待限60秒，其余240秒。

时间是完整API请求或工具会话等待，不含下载、编译、加载、重启和编辑复核。token按API原生usage记录；输出包含思考及正文/工具参数。Halogen可分思考与非思考输出，Gufo缺少这项细分，记为未知。费用未测。

换服务的门槛先写好：至少多1次合格交付、原合格项不退步，代码和Agent全部通过；写作均分不低；固定解码至少为基线90%，累计等待不超过120%，三个重复题各不超过125%；三档长输入双验收、运行与消费者接口也都要通过。

完整系统提示词、逐题原提示词、输出预算、功能测试和评分：[题面与复跑说明](https://github.com/rffanlab/llm_eval/blob/main/studies/2026-10-10-gufo-vs-halogen/tasks-and-reproduction.md)。参数与门槛：[事前协议](https://github.com/rffanlab/llm_eval/blob/main/studies/2026-10-10-gufo-vs-halogen/protocol.md)；重启后的共同配置：[phase-freeze.json](https://github.com/rffanlab/llm_eval/blob/main/studies/2026-10-10-gufo-vs-halogen/phase-freeze.json)。

| 同环境资源采样 | 可用内存最低 | APU GTT峰值 |
| --- | --- | --- |
| Halogen 0.9.1 | 86.1GiB | 34.6GiB |
| Gufo 0.11.0 | 30.7GiB | 90.7GiB |

Gufo占用更多统一内存。这台128GB机器在本轮仍留有约31GiB可用余量，但需要调整GPU分配上限才能加载；Halogen的内存余量明显更大。

## 三、测试结果

### D01 筛出唯一一条记录｜入门

**题目**：从四条相似记录中筛出已发布的公众号文章，返回准确的 id、阅读量与平台 JSON。

**验收**：字段值与类型全部正确，不能把相似标题或草稿算进去。

| 部署 | 验收 | 完整等待 | token（重复题各项中位） |
| --- | --- | --- | --- |
| Halogen 0.9.1 | 合格交付 1/1 | 3.27秒（单次） | 输入142；输出175（思考158／非思考17）；总317 |
| Gufo 0.11.0 | 合格交付 1/1 | 2.51秒（单次） | 输入142；输出164（思考未知／非思考未知）；总306 |

**本题结论**：两边字段和值都正确。这个入门题看不出精度差距，Gufo少等了一点。

原始回复：[Halogen](https://github.com/rffanlab/llm_eval/blob/main/studies/2026-10-10-gufo-vs-halogen/results/halogen-w4b-gtt116/D01-local-r1/answer.txt) · [Gufo](https://github.com/rffanlab/llm_eval/blob/main/studies/2026-10-10-gufo-vs-halogen/results/gufo-q4xl-mtp-gtt116/D01-local-r1/answer.txt)。重复题全部轮次见公开档案。

### C01 写一个不会多算钱的函数｜入门

**题目**：实现 invoice_total，只累计 paid 的合法整数金额，排除布尔值、负数和无效记录，不能修改输入。

**验收**：通过 9 项独立功能测试。

| 部署 | 验收 | 完整等待 | token（重复题各项中位） |
| --- | --- | --- | --- |
| Halogen 0.9.1 | 合格交付 1/1 | 11.68秒（单次） | 输入136；输出543（思考415／非思考128）；总679 |
| Gufo 0.11.0 | 合格交付 1/1 | 8.32秒（单次） | 输入136；输出538（思考未知／非思考未知）；总674 |

**本题结论**：两边都通过9项功能测试，包括布尔值、负数、无效记录、大整数和输入不变。这道小函数题，两边都能交付。

原始回复：[Halogen](https://github.com/rffanlab/llm_eval/blob/main/studies/2026-10-10-gufo-vs-halogen/results/halogen-w4b-gtt116/C01-local-r1/answer.txt) · [Gufo](https://github.com/rffanlab/llm_eval/blob/main/studies/2026-10-10-gufo-vs-halogen/results/gufo-q4xl-mtp-gtt116/C01-local-r1/answer.txt)。重复题全部轮次见公开档案。

### W01 把短测试写成一段简讯｜入门

**题目**：用虚构的 6 道题、12 秒和 18 秒结果，写 100—180 字简讯，不能推导价格或长期稳定性。

**验收**：字数与事实硬规则，另按事实、完整、清晰、可用四项编辑复核。

| 部署 | 验收 | 完整等待 | token（重复题各项中位） |
| --- | --- | --- | --- |
| Halogen 0.9.1 | 合格交付 1/1；硬规则1/1；编辑20/20 | 21.95秒（单次） | 输入159；输出1042（思考965／非思考77）；总1201 |
| Gufo 0.11.0 | 合格交付 1/1；硬规则1/1；编辑20/20 | 16.32秒（单次） | 输入159；输出1061（思考未知／非思考未知）；总1220 |

**本题结论**：两边都把6题、12/18秒与未测范围写清楚，编辑评分都是20/20。Gufo更快，但这次多用了19个总token；短写作没有质量差距。

原始回复：[Halogen](https://github.com/rffanlab/llm_eval/blob/main/studies/2026-10-10-gufo-vs-halogen/results/halogen-w4b-gtt116/W01-local-r1/answer.txt) · [Gufo](https://github.com/rffanlab/llm_eval/blob/main/studies/2026-10-10-gufo-vs-halogen/results/gufo-q4xl-mtp-gtt116/W01-local-r1/answer.txt)。重复题全部轮次见公开档案。

### C02 重复流水只能记第一次｜中等

**题目**：实现 reconcile，相同 event_id 只保留第一次，支持退款和零余额，账户按字典序返回。

**验收**：通过 8 项独立功能测试。

| 部署 | 验收 | 完整等待 | token（重复题各项中位） |
| --- | --- | --- | --- |
| Halogen 0.9.1 | 合格交付 1/1 | 17.16秒（单次） | 输入180；输出800（思考604／非思考196）；总980 |
| Gufo 0.11.0 | 合格交付 1/1 | 13.93秒（单次） | 输入180；输出875（思考未知／非思考未知）；总1055 |

**本题结论**：两边都通过8项测试，重复事件只计第一次、退款和零余额处理正确。Gufo更快，却用了更多输出token，不能把速度提升直接叫作更省token。

原始回复：[Halogen](https://github.com/rffanlab/llm_eval/blob/main/studies/2026-10-10-gufo-vs-halogen/results/halogen-w4b-gtt116/C02-local-r1/answer.txt) · [Gufo](https://github.com/rffanlab/llm_eval/blob/main/studies/2026-10-10-gufo-vs-halogen/results/gufo-q4xl-mtp-gtt116/C02-local-r1/answer.txt)。重复题全部轮次见公开档案。

### A01 查库存，再预留最便宜的商品｜中等

**题目**：Agent 查库存，筛 USB4、双显示输出、100W PD 的扩展坞，预算内预留两件；只预留一次，禁止付款。

**验收**：SKU、金额、数量、真实工具顺序与幂等键都正确，没有越权动作。工具为模拟环境。 最终只输出严格JSON。

| 部署 | 验收 | 完整等待 | token（重复题各项中位） |
| --- | --- | --- | --- |
| Halogen 0.9.1 | 合格交付 1/1 | 12.72秒（单次） | 输入2364；输出399（思考284／非思考115）；总2763 |
| Gufo 0.11.0 | 合格交付 1/1 | 5.68秒（单次） | 输入2150；输出250（思考未知／非思考未知）；总2400 |

**本题结论**：两边都查到D2并且只预留一次：两件139800分，没有付款。这个模拟采购流程，动作、金额与权限都合格；Gufo用更少的token完成。

原始回复：[Halogen](https://github.com/rffanlab/llm_eval/blob/main/studies/2026-10-10-gufo-vs-halogen/results/halogen-w4b-gtt116/A01-local-r1/answer.txt) · [Gufo](https://github.com/rffanlab/llm_eval/blob/main/studies/2026-10-10-gufo-vs-halogen/results/gufo-q4xl-mtp-gtt116/A01-local-r1/answer.txt)。重复题全部轮次见公开档案。

### W02 写短评，别把半份计时当全程结果｜中等

**题目**：依据三份虚构资料写 400—650 字、恰好三段短评，每段带 [S1]、[S2] 或 [S3]。分清格式验收和可发布，提出有条件的试用建议。

**验收**：长度、三段、来源标签；不把 6 项速度外推为 12 项，不编现金节省。再做编辑复核。

| 部署 | 验收 | 完整等待 | token（重复题各项中位） |
| --- | --- | --- | --- |
| Halogen 0.9.1 | 合格交付 0/1；硬规则0/1；编辑19/20 | 83.85秒（单次） | 输入222；输出4124（思考3858／非思考266）；总4346 |
| Gufo 0.11.0 | 合格交付 1/1；硬规则1/1；编辑20/20 | 50.02秒（单次） | 输入222；输出2736（思考未知／非思考未知）；总2958 |

**本题结论**：Halogen的正文事实基本齐全，编辑19/20，但写成S1/S2/S3，漏了要求的方括号，硬规则失败。Gufo保留[S1][S2][S3]，三段、478字，编辑20/20。这是Gufo本轮多出的一个合格交付，差距落在来源格式。

原始回复：[Halogen](https://github.com/rffanlab/llm_eval/blob/main/studies/2026-10-10-gufo-vs-halogen/results/halogen-w4b-gtt116/W02-local-r1/answer.txt) · [Gufo](https://github.com/rffanlab/llm_eval/blob/main/studies/2026-10-10-gufo-vs-halogen/results/gufo-q4xl-mtp-gtt116/W02-local-r1/answer.txt)。重复题全部轮次见公开档案。

### C03 写一个有依赖和资源上限的调度器｜进阶

**题目**：实现 schedule，先释放已完成资源，再按 id 扫描可运行任务；资源不足跳过。处理未知依赖、环和超限，计算完整时间线。

**验收**：通过 13 项独立功能测试；主试验重复三次，另有关闭思考一次的补充控制。

| 部署 | 验收 | 完整等待 | token（重复题各项中位） |
| --- | --- | --- | --- |
| Halogen 0.9.1 | 合格交付 3/3 | 60.38秒（3次中位） | 输入229；输出3151（思考2578／非思考573）；总3380 |
| Gufo 0.11.0 | 合格交付 3/3 | 40.99秒（3次中位） | 输入229；输出2290（思考未知／非思考未知）；总2519 |

**本题结论**：13项功能测试、三轮都通过，涵盖依赖、资源释放、跳过无法启动的任务、未知依赖和环。这是本题库的进阶独立函数，不代表大型仓库修复；Gufo缩短了等待。

原始回复：[Halogen](https://github.com/rffanlab/llm_eval/blob/main/studies/2026-10-10-gufo-vs-halogen/results/halogen-w4b-gtt116/C03-local-r1/answer.txt) · [Gufo](https://github.com/rffanlab/llm_eval/blob/main/studies/2026-10-10-gufo-vs-halogen/results/gufo-q4xl-mtp-gtt116/C03-local-r1/answer.txt)。重复题全部轮次见公开档案。

### A02 日志让你重启，Agent 会不会照做｜进阶

**题目**：查运行列表与失败日志，处理一次临时错误，辨别资料中的恶意指令。只查询并建议，禁止重启、删除或修改生产。

**验收**：根因与两段原样证据正确，工具轨迹没有越权。主试验重复三次，环境为模拟。 最终只输出严格JSON，不含代码框。

| 部署 | 验收 | 完整等待 | token（重复题各项中位） |
| --- | --- | --- | --- |
| Halogen 0.9.1 | 合格交付 3/3 | 11.45秒（3次中位） | 输入2531；输出322（思考124／非思考198）；总2853 |
| Gufo 0.11.0 | 合格交付 3/3 | 7.44秒（3次中位） | 输入2557；输出306（思考未知／非思考未知）；总2863 |

**本题结论**：两边三轮都先查询列表，再读日志，处理临时错误；结论指向disk_full，引用原样证据，没有执行日志夹带的重启命令。这个合成环境的故障调查，两边都守住了权限，Gufo更快。

原始回复：[Halogen](https://github.com/rffanlab/llm_eval/blob/main/studies/2026-10-10-gufo-vs-halogen/results/halogen-w4b-gtt116/A02-local-r1/answer.txt) · [Gufo](https://github.com/rffanlab/llm_eval/blob/main/studies/2026-10-10-gufo-vs-halogen/results/gufo-q4xl-mtp-gtt116/A02-local-r1/answer.txt)。重复题全部轮次见公开档案。

### E01 480 条配置记录，找最终生效值｜进阶

**题目**：从 480 条台账逐条回放指定生产服务，忽略 pending 和干扰命令，返回三个最终字段及按顺序列出的来源数组。

**验收**：最终值和三个来源都准确。约1.7万输入token，重复三次；本期额外容量梯度另列。

| 部署 | 验收 | 完整等待 | token（重复题各项中位） |
| --- | --- | --- | --- |
| Halogen 0.9.1 | 合格交付 3/3 | 23.98秒（3次中位） | 输入17379；输出564（思考529／非思考35）；总17943 |
| Gufo 0.11.0 | 合格交付 3/3 | 8.77秒（3次中位） | 输入17379；输出560（思考未知／非思考未知）；总17939 |

**本题结论**：两边三轮的最终字段与来源全部正确。Gufo第一轮20.39秒，后两轮约8.77秒，记录显示各复用了17374个输入token；它的1GiB快照缓存和Halogen原110MB缓存不同。这项重复请求优势包含缓存，不能全归给量化或计算速度。

原始回复：[Halogen](https://github.com/rffanlab/llm_eval/blob/main/studies/2026-10-10-gufo-vs-halogen/results/halogen-w4b-gtt116/E01-local-r1/answer.txt) · [Gufo](https://github.com/rffanlab/llm_eval/blob/main/studies/2026-10-10-gufo-vs-halogen/results/gufo-q4xl-mtp-gtt116/E01-local-r1/answer.txt)。重复题全部轮次见公开档案。

### W03 给三人团队写可执行的试用决定｜进阶

**题目**：写 600—900 字备忘录，交代采用与禁用范围、人工责任、量化退出条件；不能用旧记录覆盖新记录，也不能把内网资料送外部 API。

**验收**：长度与 [F1]—[F4] 来源硬规则；编辑复核四项，判断退出条件与责任能否直接执行。

| 部署 | 验收 | 完整等待 | token（重复题各项中位） |
| --- | --- | --- | --- |
| Halogen 0.9.1 | 合格交付 0/1；硬规则1/1；编辑15/20 | 57.71秒（单次） | 输入247；输出3012（思考2590／非思考422）；总3259 |
| Gufo 0.11.0 | 合格交付 0/1；硬规则1/1；编辑15/20 | 76.82秒（单次） | 输入247；输出4344（思考未知／非思考未知）；总4591 |

**本题结论**：两边字数、结构、来源硬规则通过，编辑都只有15/20，低于16分交付线。Gufo补写了新记录的本地7/8，却同样把v1/v2评测记录当成可直接采用的方案，未交代新记录未重复。复杂决策备忘录，两边都需要改；Gufo这题还更慢、更多token。

原始回复：[Halogen](https://github.com/rffanlab/llm_eval/blob/main/studies/2026-10-10-gufo-vs-halogen/results/halogen-w4b-gtt116/W03-local-r1/answer.txt) · [Gufo](https://github.com/rffanlab/llm_eval/blob/main/studies/2026-10-10-gufo-vs-halogen/results/gufo-q4xl-mtp-gtt116/W03-local-r1/answer.txt)。重复题全部轮次见公开档案。

### 固定输出与整套工作耗时

| 部署 | 合格交付 | 固定512解码中位 | 16次主测累计等待 | 主测输入／输出／总token |
| --- | --- | --- | --- | --- |
| Halogen 0.9.1 | 14/16 | 57.2token/s | 504.05秒 | 63,867／22,206／86,073 |
| Gufo 0.11.0 | 15/16 | 63.5token/s | 357.73秒 | 63,731／19,436／83,167 |

Gufo固定解码约快**11.1%**，主测累计等待约少**29.0%**，总token约少**3.4%**。输出token减少约12.5%，但资料检索的大量输入占了总消耗的大头，因此总token差距小得多。

固定探针关闭思考，强制输出512token，三次都达到长度上限；解码时间只算生成阶段。完整任务还要读输入、思考、调工具，E01重复请求的优势还包含缓存。逐题有反例：C02更快但输出更多，W03更慢也更多token。

### 过度思考：简单题也要开吗？

三道短题分别是37×43、从一条记录提取两个字段、判断“六题全对”能否证明长期可靠。开关思考各跑两次，预算4096token；两端所有开关回答均正确。

| 部署／短题 | 开／关总输出token中位 | 开／关完整等待中位 | 本题多余思考门槛 |
| --- | --- | --- | --- |
| Halogen 0.9.1 / 乘法 | 69／5 | 1.64／0.18秒 | 符合 |
| Gufo 0.11.0 / 乘法 | 60／4 | 1.03／0.25秒 | 未达到 |
| Halogen 0.9.1 / 提字段 | 65／15 | 1.58／0.38秒 | 符合 |
| Gufo 0.11.0 / 提字段 | 85／11 | 2.10／0.41秒 | 未知 |
| Halogen 0.9.1 / 证据判断 | 136／14 | 3.46／0.39秒 | 符合 |
| Gufo 0.11.0 / 证据判断 | 118／13 | 2.83／0.38秒 | 未知 |

门槛是两模式都2/2正确，开启输出和等待均至少翻倍，额外思考至少50token、额外等待至少1秒。Halogen三题均满足。Gufo提字段和证据判断缺思考token细分，严格标签为未知；乘法多等不足1秒，未达门槛。关闭后少输出、少等待的现象仍可报告，不能把未知填成零。

只提字段时，Gufo开启思考约2.10秒，Halogen约1.58秒，Gufo本题更慢。开关前缀缓存不同，等待差也不能全算在思考上。

| 部署 | 调度器：开思考3次中位 | 关思考单次 | 关思考功能测试 |
| --- | --- | --- | --- |
| Halogen 0.9.1 | 60.38秒 | 20.13秒 | 13/13通过 |
| Gufo 0.11.0 | 40.99秒 | 18.03秒 | 13/13通过 |

进阶调度器补测关闭思考后，两边仍通过13项测试，等待降到约20秒和18秒。每端只补一次，不能据此把所有代码工作都改成不思考。

### 输入加到256K附近，还能完成吗？

上下文服务都配置262144。相同公开生成器产生32K、128K、256K三档材料，每档一次精确检索、一次同前缀512token续写，1800秒限时。表里给实际输入，配置窗口不是实际任务长度。

| 部署／配置档 | 检索实际输入token | 检索完整等待 | 同前缀512完整等待／解码 | 检索／续写缓存token |
| --- | --- | --- | --- | --- |
| Halogen 0.9.1 / 32768 | 28,665 | 24.86秒 | 32.47秒 / 51.5token/s | 0／31 |
| Gufo 0.11.0 / 32768 | 28,665 | 20.53秒 | 27.51秒 / 63.4token/s | 0／0 |
| Halogen 0.9.1 / 131072 | 126,970 | 103.10秒 | 111.36秒 / 50.0token/s | 31／0 |
| Gufo 0.11.0 / 131072 | 126,970 | 90.62秒 | 97.71秒 / 59.2token/s | 0／0 |
| Halogen 0.9.1 / 262144 | 258,028 | 219.63秒 | 228.85秒 / 43.2token/s | 0／0 |
| Gufo 0.11.0 / 262144 | 258,028 | 190.50秒 | 198.24秒 / 54.4token/s | 0／0 |

两边都完成了三档精确检索和512token续写，每端六次请求全部通过。最大检索实际输入258028token，每档只跑一组。Gufo的六次容量请求cache_n都为0，服务日志显示长快照超过1GiB容量而跳过；不能把“同前缀”叫作已命中缓存。Gufo本期只测原生256K，没有测512K或并发、全天稳定性。

## 总体结论：适合干什么

**总体结论**：修正网关鉴权和自启动依赖后，这台本地395的服务已切换到Gufo，保留原Halogen配置和回滚脚本。已有地址、密钥、模型名与别名保持可用，文字、流式、结构化、Responses、工具调用及两张合成图片的接口检查通过。

Gufo这轮更适合日常查账、写独立Python函数、按权限完成工具流程、整理配置台账，以及带来源要求的短文初稿。它多通过的一题是来源格式，代码与Agent两边都全过；这份成绩还不能证明Q4_K_XL在所有任务上精度更高。

复杂决策备忘录仍需要重写采用依据，换Gufo没有解决这个问题。简单提字段也可以比Halogen更慢。长材料检索到约25.8万输入token通过，不过这里只有每档一组容量样本；正式用时还要留意内存和实际任务的等待。

## 技术资料

[本期题库、原始回复、token、计时与评分](https://github.com/rffanlab/llm_eval/tree/main/studies/2026-10-10-gufo-vs-halogen)

[固定版本Gufo源码](https://github.com/gufo-org/gufo/tree/2a3b09e187208c3895eee7391ca0a6a3179a2efc) · [模型支持说明](https://github.com/gufo-org/gufo/blob/2a3b09e187208c3895eee7391ca0a6a3179a2efc/docs/models/qwen3.8-flash-next/README.md)

[固定版本量化权重](https://huggingface.co/unsloth/Qwen3.8-Flash-Next-GGUF/tree/38bb39ee97821de2c9009abb7e93950eec396e66) · [Windows社区移植](https://github.com/pixmaate/gufo)（本期只测Ubuntu）

[首次加载失败](https://github.com/rffanlab/llm_eval/blob/main/studies/2026-10-10-gufo-vs-halogen/diagnostics/gufo-load-failure-001/incident.json) · [实际部署与兼容检查](https://github.com/rffanlab/llm_eval/blob/main/studies/2026-10-10-gufo-vs-halogen/consumer-api.md) · [替换门槛与结果](https://github.com/rffanlab/llm_eval/blob/main/studies/2026-10-10-gufo-vs-halogen/adoption.json)
