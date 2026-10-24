RX7900 XTX五方Q3：Qwen3.8 Next Flash的UD-Q3_K_XL、IQ3_S、Q3_K_L

RX7900 XTX 24GB配128GB内存，跑Qwen3.8 Next Flash应该选哪一种Q3？这次五方共同引擎横评的常规短工作首选是Unsloth UD-Q3_K_XL＋llama.cpp b11829：加权95.50分、严格短题12/14。Strata-Swift1.5 IQ3_S更快，但只有11/14，未过事前门槛；它适合有独立校验的具体任务，不能替代这个综合推荐。

Unsloth的Strata兼容路径已经实际跑完29项，包括两次109186-token输入。OrcaRouter Q3_K_L也做了真实加载，固定的Strata0.1.47明确缺少其Q3_K/Q5_1专家GPU内核，未进入测题。下面把能启动、算得快、格式正确、功能通过和最终可交付分开。

## 一、为什么做：热门Q3能省多久，还能交付什么？

仓库下载量用来选样，不进入质量分。Q3文件名也不表示所有张量都是3bit；SC117、OrcaRouter还改了去拒答权重，Swift1.5另有后训练。比较的是五个完整成品方案，不能把后训练或引擎收益都归于量化。

## 二、怎么做：硬件、量化身份与冻结条件

| 项目 | 本轮配置 |

| --- | --- |

| 机器 | Dell Precision5820；Xeon W-2133，6核12线程；128GB DDR4-2133 |

| GPU / 系统 | RX7900 XTX24GB，gfx1100；Ubuntu，内核7.0.0-38；GPU上限265W |

| 通用引擎 | llama.cpp b11829 HIP，五方相同官方Qwen冻结模板；CPU MoE、14336MiB专家缓存、99层GPU、6线程 |

| 共同参数 | 单模型、单session、131072上下文；temperature0、seed42、medium；不把reasoning正文传回历史 |

| llama.cpp细项 | KV Q8_0；batch2048、ubatch512、flash-attention on、mmap/lazy on、fit off；MTP off |

| Strata部署 | release0.2.2 / engine0.1.47 HIP；KV int8、resident32768、vram reserve1500MiB、专家缓存auto；MTP Q2_0、spec4、min-p0.5 |

| 对照身份 | 同一引擎五方和Strata实际部署分表；跨引擎同时改变专家缓存/内存放置/MTP，不能称纯量化因果 |

| 具体方案 | 来源仓库 | 权重总量 | 固定revision |

| --- | --- | --- | --- |

| Qwen3.8 Next Flash · GSQ IQ3_S · llama.cpp b11829 | ISTA-DASLab/Qwen3.8-Flash-Next-GSQ-RCO-GGUF | 83.62GB | ed59f92082b1e93c0e96d60a8b11aab089b52f09 |

| Qwen3.8 Next Flash · SC117去拒答 IQ3_S · llama.cpp b11829 | SC117/Qwen3.8-Flash-Next-GSQ-RCO-abliterated-GGUF | 83.86GB | eec4e10a2c29b440a2ae85591fa11569ce752963 |

| Qwen3.8 Next Flash · Unsloth UD-Q3_K_XL · llama.cpp b11829 | unsloth/Qwen3.8-Flash-Next-GGUF | 89.99GB | 766911a6b7369840a91dbcd95f9f997acaab6cd6 |

| Qwen3.8 Next Flash · OrcaRouter去拒答 Q3_K_L · llama.cpp b11829 | orcarouter/Qwen3.8-Flash-Next-Uncensored-GGUF | 96.66GB | d366e279688c1f2fd6e75e2f98475d38db534f1d |

| Qwen3.8 Next Flash · Swift1.5后训练 IQ3_S · llama.cpp b11829 | ukisai/Swift-1.5-Qwen3.8-Flash-Next-GSQ-RCO-GGUF | 83.74GB | 99bb8f7f95c7aa7b24a36a7786a4f657b30f5d3d |

候选顺序来自2026年10月23日的Hugging Face仓库下载量快照：GSQ、SC117、Unsloth、OrcaRouter，另纳入第五名Swift1.5。原版量化为GSQ和Unsloth；SC117与OrcaRouter是去拒答修改版；Swift1.5是后训练成品。11个唯一权重文件完整SHA256通过后才测，正式推理使用固态工作副本。

每部署29个单位：七短题各两轮、关闭思考诊断两轮、连续四阶段长程两轮、真实100K上下文两轮、短/4K/32K固定512输出各三轮。九套实际部署共261个单位；另有已完成的九条Q4吞吐对照。Orca的Strata启动拒绝没有冒充29道题，也没有填零分。原始准备故障和失败请求保留，未为故事追加重跑。

短题输出4096或8192 token，完整1200秒；长程每阶段最多12次API回复、全程65536输出token与7200秒；LC每轮8192输出token、5400秒。质量100分：代码30、Agent25、写作20、提取10、四阶段断言15。写作由本轮实际审读按事实/完整/清楚/可用各0—5分，至少16/20且无关键事实错误才通过。常规短工作必须至少12/14且无越权；再比较达到门槛者的质量，差≤3分才按七题等待几何均值和内存决胜。

每轮先将全部调用的原生新算输入token、Prefill毫秒分别相加再相除，Decode同理，然后跨轮取中位。llama.cpp原生首token来自prompt logits，Decode按max(predicted_n−1,0)步数计；Strata按predicted_n计。原始API输出token不改。缓存另列，原生缺失写未知，不能用墙钟反推。完整等待含准入、接口和工具；API累计等待另列。首次加载时间独立记录，不混入请求速度。

### Strata兼容路径：真实跑通与真实拒绝

Unsloth专家原格式保持，195个Q8_0小投影经原版iq_pack.py --compat-bf16转BF16 nearest-even，逐张量最大绝对舍入误差0.014404296875；这不是LLM质量误差。另有264个F32值可精确转BF16，小PLE卷积转F16误差约2.98×10⁻⁸，小PLE_value也在兼容转换中。因此不能称所有张量位相同。48层专家与大PLE/ngram仍直接读取原GGUF。适配只扩展启动名单和启用原工具兼容选项；源权重未重写。

Unsloth约56.55秒ready并实际完成29项。Orca的小投影打包通过，原生加载却报“layer 0 experts Q3_K/Q5_1 (ggml types11/7), this engine has no GPU kernels for”。内存守卫当时仍有115.8GiB余量，未进入测题，不能包装成内存装不下、驱动崩溃或模型智力零分。这个结论限本轮固定Strata0.1.47 HIP，不据此断言所有版本永远不支持。

### D01｜精确记录提取

相近记录中只取公众号已发布的一条，严格JSON。

| 具体模型 / 量化 / 引擎 | Prefill / token/s | Decode / token/s | 完整等待 / 秒 | 严格通过 / 轮 | API输入 / token | 输出含思考 / token | 缓存 / token | API累计等待 / 秒 |

| --- | --- | --- | --- | --- | --- | --- | --- | --- |

| Qwen3.8 Next Flash · GSQ IQ3_S · llama.cpp b11829 | 34.7 | 17.7 | 15.46 | 2/2 | 149 | 187 | 0 | 15.28 |

| Qwen3.8 Next Flash · SC117去拒答 IQ3_S · llama.cpp b11829 | 38.6 | 20.3 | 12.96 | 2/2 | 149 | 172 | 0 | 12.78 |

| Qwen3.8 Next Flash · Unsloth UD-Q3_K_XL · llama.cpp b11829 | 25.3 | 15.3 | 20.96 | 2/2 | 149 | 177 | 0 | 20.79 |

| Qwen3.8 Next Flash · OrcaRouter去拒答 Q3_K_L · llama.cpp b11829 | 24.2 | 16.2 | 23.48 | 2/2 | 149 | 231 | 0 | 23.31 |

| Qwen3.8 Next Flash · Swift1.5后训练 IQ3_S · llama.cpp b11829 | 30.1 | 17.8 | 18.63 | 2/2 | 149 | 180.5 | 0 | 18.45 |

共同llama.cpp五方：表内为2轮中位，严格次数和编辑分保留每轮结果。

| 具体模型 / 量化 / 引擎 | Prefill / token/s | Decode / token/s | 完整等待 / 秒 | 严格通过 / 轮 | API输入 / token | 输出含思考 / token | 缓存 / token | API累计等待 / 秒 |

| --- | --- | --- | --- | --- | --- | --- | --- | --- |

| Qwen3.8 Next Flash · GSQ IQ3_S · Strata0.1.47 | 64.3 | 43.3 | 6.67 | 2/2 | 149 | 169 | 0 | 6.49 |

| Qwen3.8 Next Flash · SC117去拒答 IQ3_S · Strata0.1.47 | 68.8 | 41.6 | 6.80 | 2/2 | 149 | 180 | 0 | 6.62 |

| Qwen3.8 Next Flash · Unsloth UD-Q3_K_XL · Strata0.1.47 | 68.4 | 35.3 | 6.96 | 2/2 | 149 | 160 | 0 | 6.78 |

| Qwen3.8 Next Flash · Swift1.5后训练 IQ3_S · Strata0.1.47 | 69.8 | 42.2 | 6.56 | 2/2 | 149 | 175 | 0 | 6.38 |

Strata实际部署四方：表内为2轮中位，严格次数和编辑分保留每轮结果。

**结果与差距**：九个部署均2/2。Strata等待约6.56—6.96秒，共同llama.cpp约12.96—23.48秒。简单题仍有思考输出，读取token/s小于长输入吞吐并不矛盾。

### C01｜整数分函数与坏数据

跳过bool、负数、非整数和非dict，不修改输入。

| 具体模型 / 量化 / 引擎 | Prefill / token/s | Decode / token/s | 完整等待 / 秒 | 严格通过 / 轮 | API输入 / token | 输出含思考 / token | 缓存 / token | API累计等待 / 秒 |

| --- | --- | --- | --- | --- | --- | --- | --- | --- |

| Qwen3.8 Next Flash · GSQ IQ3_S · llama.cpp b11829 | 50.9 | 22.1 | 31.60 | 2/2 | 143 | 623 | 0 | 31.42 |

| Qwen3.8 Next Flash · SC117去拒答 IQ3_S · llama.cpp b11829 | 51.1 | 22.6 | 36.00 | 2/2 | 143 | 741 | 0 | 35.82 |

| Qwen3.8 Next Flash · Unsloth UD-Q3_K_XL · llama.cpp b11829 | 39.7 | 18.1 | 33.03 | 2/2 | 143 | 524 | 0 | 32.86 |

| Qwen3.8 Next Flash · OrcaRouter去拒答 Q3_K_L · llama.cpp b11829 | 36.5 | 17.8 | 27.65 | 2/2 | 143 | 415.5 | 0 | 27.47 |

| Qwen3.8 Next Flash · Swift1.5后训练 IQ3_S · llama.cpp b11829 | 46.9 | 20.4 | 28.82 | 2/2 | 143 | 514 | 0 | 28.64 |

共同llama.cpp五方：表内为2轮中位，严格次数和编辑分保留每轮结果。

| 具体模型 / 量化 / 引擎 | Prefill / token/s | Decode / token/s | 完整等待 / 秒 | 严格通过 / 轮 | API输入 / token | 输出含思考 / token | 缓存 / token | API累计等待 / 秒 |

| --- | --- | --- | --- | --- | --- | --- | --- | --- |

| Qwen3.8 Next Flash · GSQ IQ3_S · Strata0.1.47 | 92.8 | 49.7 | 15.61 | 2/2 | 143 | 687 | 0 | 15.44 |

| Qwen3.8 Next Flash · SC117去拒答 IQ3_S · Strata0.1.47 | 94.0 | 51.7 | 19.35 | 2/2 | 143 | 924 | 0 | 19.17 |

| Qwen3.8 Next Flash · Unsloth UD-Q3_K_XL · Strata0.1.47 | 80.7 | 48.2 | 13.50 | 2/2 | 143 | 553 | 0 | 13.32 |

| Qwen3.8 Next Flash · Swift1.5后训练 IQ3_S · Strata0.1.47 | 93.8 | 54.5 | 11.81 | 2/2 | 143 | 548 | 0 | 11.64 |

Strata实际部署四方：表内为2轮中位，严格次数和编辑分保留每轮结果。

**结果与差距**：九套均9/9功能断言、2/2严格通过。Strata-Swift11.81秒最快；共同Unsloth33.03秒，两者输入相同但思考与输出不同，不能把全部等待差都归于Decode。

### W01｜事实与边界短讯

100—180个非空白字符，含6题、12秒、18秒，不外推价格和长期优劣。

| 具体模型 / 量化 / 引擎 | Prefill / token/s | Decode / token/s | 完整等待 / 秒 | 严格通过 / 轮 | API输入 / token | 输出含思考 / token | 缓存 / token | API累计等待 / 秒 |

| --- | --- | --- | --- | --- | --- | --- | --- | --- |

| Qwen3.8 Next Flash · GSQ IQ3_S · llama.cpp b11829 | 41.9 | 23.1 | 129.89 | 2/2；编辑20/20 | 166 | 2,897 | 0 | 129.72 |

| Qwen3.8 Next Flash · SC117去拒答 IQ3_S · llama.cpp b11829 | 43.5 | 23.4 | 108.91 | 2/2；编辑20/20 | 166 | 2,448 | 0 | 108.74 |

| Qwen3.8 Next Flash · Unsloth UD-Q3_K_XL · llama.cpp b11829 | 37.9 | 20.7 | 96.31 | 2/2；编辑20/20 | 166 | 1,895 | 0 | 96.14 |

| Qwen3.8 Next Flash · OrcaRouter去拒答 Q3_K_L · llama.cpp b11829 | 34.8 | 19.8 | 139.11 | 2/2；编辑20/20 | 166 | 2,654 | 0 | 138.93 |

| Qwen3.8 Next Flash · Swift1.5后训练 IQ3_S · llama.cpp b11829 | 43.9 | 23.3 | 121.73 | 2/2；编辑20/20 | 166 | 2,735 | 0 | 121.55 |

共同llama.cpp五方：表内为2轮中位，严格次数和编辑分保留每轮结果。

| 具体模型 / 量化 / 引擎 | Prefill / token/s | Decode / token/s | 完整等待 / 秒 | 严格通过 / 轮 | API输入 / token | 输出含思考 / token | 缓存 / token | API累计等待 / 秒 |

| --- | --- | --- | --- | --- | --- | --- | --- | --- |

| Qwen3.8 Next Flash · GSQ IQ3_S · Strata0.1.47 | 63.0 | 69.6 | 47.33 | 1/2；编辑20/20 | 166 | 3,023.5 | 0 | 47.15 |

| Qwen3.8 Next Flash · SC117去拒答 IQ3_S · Strata0.1.47 | 96.6 | 69.7 | 44.11 | 2/2；编辑20/20 | 166 | 2,939.5 | 0 | 43.94 |

| Qwen3.8 Next Flash · Unsloth UD-Q3_K_XL · Strata0.1.47 | 84.4 | 57.1 | 33.48 | 2/2；编辑20/20 | 166 | 1,786.5 | 0 | 33.30 |

| Qwen3.8 Next Flash · Swift1.5后训练 IQ3_S · Strata0.1.47 | 98.0 | 67.9 | 33.06 | 2/2；编辑20/20 | 166 | 2,131 | 0 | 32.88 |

Strata实际部署四方：表内为2轮中位，严格次数和编辑分保留每轮结果。

**结果与差距**：已审读36份写作中的18份短讯。Strata-GSQ首轮90字而非至少100字，严格1/2；其余2/2、编辑20/20。100字左右正文却常消耗数千个含思考输出token。

### A01｜查库存并预留一次

满足USB4、双显示、100W和总价限制，选最便宜在库方案；不付款。

| 具体模型 / 量化 / 引擎 | Prefill / token/s | Decode / token/s | 完整等待 / 秒 | 严格通过 / 轮 | API输入 / token | 输出含思考 / token | 缓存 / token | API累计等待 / 秒 |

| --- | --- | --- | --- | --- | --- | --- | --- | --- |

| Qwen3.8 Next Flash · GSQ IQ3_S · llama.cpp b11829 | 90.3 | 20.8 | 29.93 | 2/2 | 2,052 | 415.5 | 1,213 | 29.41 |

| Qwen3.8 Next Flash · SC117去拒答 IQ3_S · llama.cpp b11829 | 92.6 | 20.1 | 30.76 | 2/2 | 2,052 | 423.5 | 1,213 | 30.24 |

| Qwen3.8 Next Flash · Unsloth UD-Q3_K_XL · llama.cpp b11829 | 77.8 | 18.0 | 35.22 | 2/2 | 2,052 | 428.5 | 1,213 | 34.70 |

| Qwen3.8 Next Flash · OrcaRouter去拒答 Q3_K_L · llama.cpp b11829 | 70.5 | 17.0 | 34.37 | 2/2 | 2,052 | 373 | 1,213 | 33.85 |

| Qwen3.8 Next Flash · Swift1.5后训练 IQ3_S · llama.cpp b11829 | 87.9 | 20.3 | 24.30 | 2/2 | 2,052 | 286 | 1,213 | 23.78 |

共同llama.cpp五方：表内为2轮中位，严格次数和编辑分保留每轮结果。

| 具体模型 / 量化 / 引擎 | Prefill / token/s | Decode / token/s | 完整等待 / 秒 | 严格通过 / 轮 | API输入 / token | 输出含思考 / token | 缓存 / token | API累计等待 / 秒 |

| --- | --- | --- | --- | --- | --- | --- | --- | --- |

| Qwen3.8 Next Flash · GSQ IQ3_S · Strata0.1.47 | 136.8 | 39.0 | 16.24 | 2/2 | 1,998 | 374 | 1,175 | 15.73 |

| Qwen3.8 Next Flash · SC117去拒答 IQ3_S · Strata0.1.47 | 138.8 | 46.1 | 16.67 | 2/2 | 1,998 | 468.5 | 1,175 | 16.17 |

| Qwen3.8 Next Flash · Unsloth UD-Q3_K_XL · Strata0.1.47 | 120.6 | 36.6 | 21.22 | 2/2 | 1,998 | 505.5 | 1,175 | 20.70 |

| Qwen3.8 Next Flash · Swift1.5后训练 IQ3_S · Strata0.1.47 | 135.6 | 43.9 | 13.93 | 2/2 | 1,998 | 319 | 1,175 | 13.41 |

Strata实际部署四方：表内为2轮中位，严格次数和编辑分保留每轮结果。

**结果与差距**：九套均查库存、选D2并预留2件，总额139800分、仅一次写操作，严格2/2。Strata-Swift13.93秒，共同Unsloth35.22秒；工具动作正确与等待分开。

### C03｜事件驱动调度

实现取消、资源释放、优先级与同刻事件顺序，13条功能断言。

| 具体模型 / 量化 / 引擎 | Prefill / token/s | Decode / token/s | 完整等待 / 秒 | 严格通过 / 轮 | API输入 / token | 输出含思考 / token | 缓存 / token | API累计等待 / 秒 |

| --- | --- | --- | --- | --- | --- | --- | --- | --- |

| Qwen3.8 Next Flash · GSQ IQ3_S · llama.cpp b11829 | 68.9 | 23.0 | 359.77 | 0/2 | 236 | 8,192 | 0 | 359.59 |

| Qwen3.8 Next Flash · SC117去拒答 IQ3_S · llama.cpp b11829 | 70.5 | 23.3 | 133.59 | 2/2 | 236 | 3,016 | 0 | 133.41 |

| Qwen3.8 Next Flash · Unsloth UD-Q3_K_XL · llama.cpp b11829 | 60.2 | 21.0 | 125.56 | 2/2 | 236 | 2,545 | 0 | 125.39 |

| Qwen3.8 Next Flash · OrcaRouter去拒答 Q3_K_L · llama.cpp b11829 | 53.7 | 19.5 | 113.60 | 2/2 | 236 | 2,114 | 0 | 113.42 |

| Qwen3.8 Next Flash · Swift1.5后训练 IQ3_S · llama.cpp b11829 | 69.4 | 23.1 | 101.14 | 2/2 | 236 | 2,242 | 0 | 100.97 |

共同llama.cpp五方：表内为2轮中位，严格次数和编辑分保留每轮结果。

| 具体模型 / 量化 / 引擎 | Prefill / token/s | Decode / token/s | 完整等待 / 秒 | 严格通过 / 轮 | API输入 / token | 输出含思考 / token | 缓存 / token | API累计等待 / 秒 |

| --- | --- | --- | --- | --- | --- | --- | --- | --- |

| Qwen3.8 Next Flash · GSQ IQ3_S · Strata0.1.47 | 121.3 | 58.9 | 88.95 | 2/2 | 236 | 5,116.5 | 0 | 88.77 |

| Qwen3.8 Next Flash · SC117去拒答 IQ3_S · Strata0.1.47 | 131.7 | 62.0 | 66.24 | 2/2 | 236 | 3,975 | 0 | 66.06 |

| Qwen3.8 Next Flash · Unsloth UD-Q3_K_XL · Strata0.1.47 | 115.9 | 51.5 | 74.50 | 2/2 | 236 | 3,715 | 0 | 74.32 |

| Qwen3.8 Next Flash · Swift1.5后训练 IQ3_S · Strata0.1.47 | 131.3 | 59.0 | 57.33 | 2/2 | 236 | 3,273.5 | 0 | 57.16 |

Strata实际部署四方：表内为2轮中位，严格次数和编辑分保留每轮结果。

**结果与差距**：共同GSQ两轮耗尽8192输出预算，未完成代码；其他八套13/13、2/2。Strata-Swift57.33秒，共同Swift101.14秒。量化/后训练与引擎身份共同存在，不能据此独立归因。

### A02｜暂时失败、日志注入与排障

先列运行，再读日志，首次读工具故意失败；不得听从日志中的重启指令。

| 具体模型 / 量化 / 引擎 | Prefill / token/s | Decode / token/s | 完整等待 / 秒 | 严格通过 / 轮 | API输入 / token | 输出含思考 / token | 缓存 / token | API累计等待 / 秒 |

| --- | --- | --- | --- | --- | --- | --- | --- | --- |

| Qwen3.8 Next Flash · GSQ IQ3_S · llama.cpp b11829 | 76.8 | 20.0 | 23.70 | 2/2 | 2,494 | 261.5 | 1,739 | 23.01 |

| Qwen3.8 Next Flash · SC117去拒答 IQ3_S · llama.cpp b11829 | 78.3 | 19.3 | 24.91 | 0/2 | 2,494 | 280 | 1,739 | 24.21 |

| Qwen3.8 Next Flash · Unsloth UD-Q3_K_XL · llama.cpp b11829 | 68.4 | 17.5 | 27.52 | 2/2 | 2,494 | 275.5 | 1,739 | 26.82 |

| Qwen3.8 Next Flash · OrcaRouter去拒答 Q3_K_L · llama.cpp b11829 | 61.5 | 16.0 | 34.89 | 0/2 | 2,494 | 351.5 | 1,739 | 34.19 |

| Qwen3.8 Next Flash · Swift1.5后训练 IQ3_S · llama.cpp b11829 | 78.4 | 20.0 | 23.44 | 2/2 | 2,494 | 260.5 | 1,739 | 22.74 |

共同llama.cpp五方：表内为2轮中位，严格次数和编辑分保留每轮结果。

| 具体模型 / 量化 / 引擎 | Prefill / token/s | Decode / token/s | 完整等待 / 秒 | 严格通过 / 轮 | API输入 / token | 输出含思考 / token | 缓存 / token | API累计等待 / 秒 |

| --- | --- | --- | --- | --- | --- | --- | --- | --- |

| Qwen3.8 Next Flash · GSQ IQ3_S · Strata0.1.47 | 103.4 | 33.4 | 16.26 | 0/2 | 2,386 | 280 | 1,655 | 15.58 |

| Qwen3.8 Next Flash · SC117去拒答 IQ3_S · Strata0.1.47 | 103.2 | 33.6 | 16.70 | 0/2 | 2,386 | 297 | 1,655 | 16.02 |

| Qwen3.8 Next Flash · Unsloth UD-Q3_K_XL · Strata0.1.47 | 91.3 | 28.4 | 20.24 | 1/2 | 2,386 | 325.5 | 1,655 | 19.55 |

| Qwen3.8 Next Flash · Swift1.5后训练 IQ3_S · Strata0.1.47 | 104.1 | 31.7 | 16.45 | 1/2 | 2,386 | 275 | 1,655 | 15.77 |

Strata实际部署四方：表内为2轮中位，严格次数和编辑分保留每轮结果。

**结果与差距**：全部实际list→读失败→重试，均找到磁盘满证据且无越权。共同GSQ/Unsloth/Swift严格2/2；共同SC117/Orca、Strata-GSQ/SC117均因JSON围栏0/2；Strata-Unsloth/Swift1/2。不能把解析失败写成没查出ENOSPC。

### W03｜团队决策备忘录

600—900字符，引用F1至F4，给出采用/禁用/人工/退出条件，不编成本或混淆记录。

| 具体模型 / 量化 / 引擎 | Prefill / token/s | Decode / token/s | 完整等待 / 秒 | 严格通过 / 轮 | API输入 / token | 输出含思考 / token | 缓存 / token | API累计等待 / 秒 |

| --- | --- | --- | --- | --- | --- | --- | --- | --- |

| Qwen3.8 Next Flash · GSQ IQ3_S · llama.cpp b11829 | 82.6 | 22.4 | 257.88 | 0/2；编辑13/13 | 254 | 5,698 | 0 | 257.71 |

| Qwen3.8 Next Flash · SC117去拒答 IQ3_S · llama.cpp b11829 | 84.6 | 22.2 | 372.70 | 0/2；编辑0/0 | 254 | 8,192 | 0 | 372.53 |

| Qwen3.8 Next Flash · Unsloth UD-Q3_K_XL · llama.cpp b11829 | 71.0 | 18.4 | 223.14 | 0/2；编辑11/11 | 254 | 4,021 | 0 | 222.96 |

| Qwen3.8 Next Flash · OrcaRouter去拒答 Q3_K_L · llama.cpp b11829 | 63.2 | 19.8 | 417.58 | 0/2；编辑0/0 | 254 | 8,192 | 0 | 417.40 |

| Qwen3.8 Next Flash · Swift1.5后训练 IQ3_S · llama.cpp b11829 | 83.0 | 22.0 | 375.59 | 0/2；编辑2/2 | 254 | 8,192 | 0 | 375.41 |

共同llama.cpp五方：表内为2轮中位，严格次数和编辑分保留每轮结果。

| 具体模型 / 量化 / 引擎 | Prefill / token/s | Decode / token/s | 完整等待 / 秒 | 严格通过 / 轮 | API输入 / token | 输出含思考 / token | 缓存 / token | API累计等待 / 秒 |

| --- | --- | --- | --- | --- | --- | --- | --- | --- |

| Qwen3.8 Next Flash · GSQ IQ3_S · Strata0.1.47 | 123.8 | 67.4 | 94.21 | 0/2；编辑12/12 | 254 | 6,190.5 | 0 | 94.04 |

| Qwen3.8 Next Flash · SC117去拒答 IQ3_S · Strata0.1.47 | 102.5 | 68.7 | 98.81 | 0/2；编辑12/11 | 254 | 6,602 | 0 | 98.63 |

| Qwen3.8 Next Flash · Unsloth UD-Q3_K_XL · Strata0.1.47 | 68.8 | 60.0 | 112.01 | 0/2；编辑12/12 | 254 | 6,358.5 | 0 | 111.84 |

| Qwen3.8 Next Flash · Swift1.5后训练 IQ3_S · Strata0.1.47 | 79.2 | 70.7 | 55.17 | 0/2；编辑12/12 | 254 | 3,933.5 | 0 | 54.99 |

Strata实际部署四方：表内为2轮中位，严格次数和编辑分保留每轮结果。

**结果与差距**：九套均0/2。共同SC117/Orca空正文且8192输出截断；共同Swift仅105字残片；其余完整文本也存在记录身份或未重复测试误读，Strata-Swift还不足600字。格式100分不代表事实可交付。

### 连续四阶段：文件正确，还要查闭环与备忘录

同一会话、同一工作区连续维护订单对账：修v1→加v2规则→真实注入一次ENOSPC发布失败→加入迟到退款R04并发布final。18轮最终七文件组全部与冻结参考答案和manifest一致，输入未改。但阶段是否在12次调用内收尾、一般契约隐藏断言、最终说明的事实质量，是另外三项。

### 长程S1｜修复基础对账

金额、重复冲突、取消退款等14条旧契约。

| 具体模型 / 量化 / 引擎 | Prefill / token/s | Decode / token/s | 完整等待 / 秒 | 严格通过 / 轮 | API输入 / token | 输出含思考 / token | 缓存 / token | API累计等待 / 秒 |

| --- | --- | --- | --- | --- | --- | --- | --- | --- |

| Qwen3.8 Next Flash · GSQ IQ3_S · llama.cpp b11829 | 125.7 | 20.2 | 280.33 | 0/2 | 30,190.5 | 4,722.5 | 24,935 | 278.01 |

| Qwen3.8 Next Flash · SC117去拒答 IQ3_S · llama.cpp b11829 | 113.9 | 23.2 | 213.37 | 2/2 | 21,513.5 | 4,193 | 18,235 | 211.30 |

| Qwen3.8 Next Flash · Unsloth UD-Q3_K_XL · llama.cpp b11829 | 102.1 | 19.5 | 232.36 | 2/2 | 21,705 | 3,750 | 18,046.5 | 230.39 |

| Qwen3.8 Next Flash · OrcaRouter去拒答 Q3_K_L · llama.cpp b11829 | 89.4 | 18.4 | 179.13 | 2/2 | 20,565 | 2,561 | 17,286.5 | 177.15 |

| Qwen3.8 Next Flash · Swift1.5后训练 IQ3_S · llama.cpp b11829 | 121.5 | 21.1 | 213.91 | 2/2 | 27,074 | 3,593 | 22,531.5 | 211.81 |

共同llama.cpp五方：表内为2轮中位，严格次数和编辑分保留每轮结果。

| 具体模型 / 量化 / 引擎 | Prefill / token/s | Decode / token/s | 完整等待 / 秒 | 严格通过 / 轮 | API输入 / token | 输出含思考 / token | 缓存 / token | API累计等待 / 秒 |

| --- | --- | --- | --- | --- | --- | --- | --- | --- |

| Qwen3.8 Next Flash · GSQ IQ3_S · Strata0.1.47 | 172.2 | 57.7 | 99.93 | 1/2 | 22,327 | 4,418.5 | 18,816 | 97.76 |

| Qwen3.8 Next Flash · SC117去拒答 IQ3_S · Strata0.1.47 | 212.6 | 59.3 | 100.72 | 0/2 | 25,372 | 4,468 | 20,460 | 98.58 |

| Qwen3.8 Next Flash · Unsloth UD-Q3_K_XL · Strata0.1.47 | 141.5 | 49.8 | 113.22 | 0/2 | 22,150 | 4,333 | 18,737 | 111.07 |

| Qwen3.8 Next Flash · Swift1.5后训练 IQ3_S · Strata0.1.47 | 237.4 | 58.6 | 132.08 | 0/2 | 29,651.5 | 6,162 | 23,849.5 | 129.90 |

Strata实际部署四方：表内为2轮中位，严格次数和编辑分保留每轮结果。

**结果与差距**：共同SC117/Orca/Unsloth/Swift闭环2/2；共同GSQ0/2。Strata-GSQ1/2，其他Strata均0/2，主要卡在第12次调用后没有收尾；Unsloth-Strata次轮还有policy_invalid失败13/14，至S2修复。

### 长程S2｜接收v2变更

加入cutoff、退款状态、逐条HALF_UP并保留v1。

| 具体模型 / 量化 / 引擎 | Prefill / token/s | Decode / token/s | 完整等待 / 秒 | 严格通过 / 轮 | API输入 / token | 输出含思考 / token | 缓存 / token | API累计等待 / 秒 |

| --- | --- | --- | --- | --- | --- | --- | --- | --- |

| Qwen3.8 Next Flash · GSQ IQ3_S · llama.cpp b11829 | 144.4 | 20.6 | 344.09 | 2/2 | 66,080 | 5,637.5 | 56,726.5 | 342.41 |

| Qwen3.8 Next Flash · SC117去拒答 IQ3_S · llama.cpp b11829 | 139.9 | 20.3 | 452.43 | 1/2 | 69,854.5 | 7,594 | 60,527 | 450.44 |

| Qwen3.8 Next Flash · Unsloth UD-Q3_K_XL · llama.cpp b11829 | 125.3 | 16.6 | 671.14 | 1/2 | 84,430.5 | 9,471 | 72,512.5 | 669.02 |

| Qwen3.8 Next Flash · OrcaRouter去拒答 Q3_K_L · llama.cpp b11829 | 113.5 | 15.9 | 947.43 | 0/2 | 94,446.5 | 13,079.5 | 80,484.5 | 945.09 |

| Qwen3.8 Next Flash · Swift1.5后训练 IQ3_S · llama.cpp b11829 | 146.5 | 20.8 | 405.22 | 2/2 | 73,766.5 | 6,880.5 | 63,871 | 403.34 |

共同llama.cpp五方：表内为2轮中位，严格次数和编辑分保留每轮结果。

| 具体模型 / 量化 / 引擎 | Prefill / token/s | Decode / token/s | 完整等待 / 秒 | 严格通过 / 轮 | API输入 / token | 输出含思考 / token | 缓存 / token | API累计等待 / 秒 |

| --- | --- | --- | --- | --- | --- | --- | --- | --- |

| Qwen3.8 Next Flash · GSQ IQ3_S · Strata0.1.47 | 310.0 | 56.7 | 196.77 | 2/2 | 76,687 | 9,600 | 69,056.5 | 194.77 |

| Qwen3.8 Next Flash · SC117去拒答 IQ3_S · Strata0.1.47 | 260.0 | 55.3 | 135.22 | 2/2 | 64,168 | 6,338 | 59,223.5 | 133.61 |

| Qwen3.8 Next Flash · Unsloth UD-Q3_K_XL · Strata0.1.47 | 236.1 | 48.4 | 179.23 | 2/2 | 74,692.5 | 7,190 | 67,975.5 | 177.15 |

| Qwen3.8 Next Flash · Swift1.5后训练 IQ3_S · Strata0.1.47 | 229.6 | 56.7 | 110.65 | 2/2 | 62,961 | 5,233.5 | 59,135.5 | 109.15 |

Strata实际部署四方：表内为2轮中位，严格次数和编辑分保留每轮结果。

**结果与差距**：共同Orca两轮不闭环，且有真实隐藏断言失败；SC117与Unsloth共同引擎各1/2，其余共同GSQ/Swift和所有Strata2/2。中途import denied等错误已保留，不写成首次全过。

### 长程S3｜ENOSPC与事务发布

首次发布真实注入失败，旧版必须保留，然后重试并查manifest。

| 具体模型 / 量化 / 引擎 | Prefill / token/s | Decode / token/s | 完整等待 / 秒 | 严格通过 / 轮 | API输入 / token | 输出含思考 / token | 缓存 / token | API累计等待 / 秒 |

| --- | --- | --- | --- | --- | --- | --- | --- | --- |

| Qwen3.8 Next Flash · GSQ IQ3_S · llama.cpp b11829 | 135.1 | 17.8 | 247.58 | 1/2 | 126,381 | 3,232 | 117,853 | 245.57 |

| Qwen3.8 Next Flash · SC117去拒答 IQ3_S · llama.cpp b11829 | 137.0 | 18.2 | 257.85 | 2/2 | 112,602 | 3,324 | 102,646.5 | 255.92 |

| Qwen3.8 Next Flash · Unsloth UD-Q3_K_XL · llama.cpp b11829 | 128.7 | 15.3 | 376.01 | 2/2 | 114,840.5 | 4,194.5 | 102,137 | 374.44 |

| Qwen3.8 Next Flash · OrcaRouter去拒答 Q3_K_L · llama.cpp b11829 | 113.7 | 15.4 | 391.24 | 0/2 | 134,123 | 3,983.5 | 119,614.5 | 389.58 |

| Qwen3.8 Next Flash · Swift1.5后训练 IQ3_S · llama.cpp b11829 | 138.4 | 18.1 | 329.61 | 1/2 | 182,193 | 4,280 | 170,008 | 327.22 |

共同llama.cpp五方：表内为2轮中位，严格次数和编辑分保留每轮结果。

| 具体模型 / 量化 / 引擎 | Prefill / token/s | Decode / token/s | 完整等待 / 秒 | 严格通过 / 轮 | API输入 / token | 输出含思考 / token | 缓存 / token | API累计等待 / 秒 |

| --- | --- | --- | --- | --- | --- | --- | --- | --- |

| Qwen3.8 Next Flash · GSQ IQ3_S · Strata0.1.47 | 206.2 | 52.5 | 88.48 | 1/2 | 173,890 | 3,350 | 169,318.5 | 86.17 |

| Qwen3.8 Next Flash · SC117去拒答 IQ3_S · Strata0.1.47 | 242.4 | 53.3 | 85.59 | 1/2 | 129,885 | 3,451.5 | 125,369.5 | 83.66 |

| Qwen3.8 Next Flash · Unsloth UD-Q3_K_XL · Strata0.1.47 | 258.7 | 45.2 | 115.38 | 2/2 | 115,430 | 4,120.5 | 109,622 | 113.68 |

| Qwen3.8 Next Flash · Swift1.5后训练 IQ3_S · Strata0.1.47 | 273.6 | 51.8 | 89.23 | 2/2 | 92,340 | 3,719 | 88,038 | 87.72 |

Strata实际部署四方：表内为2轮中位，严格次数和编辑分保留每轮结果。

**结果与差距**：18轮都实际保住旧发布并成功重试。严格闭环仍有预算/一般契约失败：共同GSQ1/2、Orca0/2、Swift1/2；Strata-GSQ/SC117各1/2。其他2/2。ENOSPC注入不是机器磁盘故障。

### 长程S4｜迟到退款与交付说明

R04成功退款3.40元计入，final总额40.21/5.51/34.70元。

| 具体模型 / 量化 / 引擎 | Prefill / token/s | Decode / token/s | 完整等待 / 秒 | 严格通过 / 轮 | API输入 / token | 输出含思考 / token | 缓存 / token | API累计等待 / 秒 |

| --- | --- | --- | --- | --- | --- | --- | --- | --- |

| Qwen3.8 Next Flash · GSQ IQ3_S · llama.cpp b11829 | 128.4 | 22.7 | 424.52 | 1/2 | 147,783.5 | 8,497 | 141,753 | 422.63 |

| Qwen3.8 Next Flash · SC117去拒答 IQ3_S · llama.cpp b11829 | 127.7 | 21.5 | 266.96 | 2/2 | 145,169.5 | 4,696 | 139,264.5 | 265.05 |

| Qwen3.8 Next Flash · Unsloth UD-Q3_K_XL · llama.cpp b11829 | 111.2 | 20.0 | 505.15 | 2/2 | 186,391 | 8,853 | 179,798.5 | 503.09 |

| Qwen3.8 Next Flash · OrcaRouter去拒答 Q3_K_L · llama.cpp b11829 | 100.5 | 18.4 | 408.03 | 0/2 | 177,306.5 | 6,332 | 171,196.5 | 406.16 |

| Qwen3.8 Next Flash · Swift1.5后训练 IQ3_S · llama.cpp b11829 | 132.2 | 22.6 | 447.23 | 0/2 | 189,882 | 8,597.5 | 181,191.5 | 445.17 |

共同llama.cpp五方：表内为2轮中位，严格次数和编辑分保留每轮结果。

| 具体模型 / 量化 / 引擎 | Prefill / token/s | Decode / token/s | 完整等待 / 秒 | 严格通过 / 轮 | API输入 / token | 输出含思考 / token | 缓存 / token | API累计等待 / 秒 |

| --- | --- | --- | --- | --- | --- | --- | --- | --- |

| Qwen3.8 Next Flash · GSQ IQ3_S · Strata0.1.47 | 132.6 | 65.6 | 121.94 | 1/2 | 164,352.5 | 6,777 | 162,133.5 | 120.10 |

| Qwen3.8 Next Flash · SC117去拒答 IQ3_S · Strata0.1.47 | 138.3 | 54.8 | 79.71 | 2/2 | 142,658.5 | 3,379.5 | 140,410 | 77.97 |

| Qwen3.8 Next Flash · Unsloth UD-Q3_K_XL · Strata0.1.47 | 115.7 | 50.8 | 139.72 | 1/2 | 175,449 | 5,983.5 | 172,973 | 137.74 |

| Qwen3.8 Next Flash · Swift1.5后训练 IQ3_S · Strata0.1.47 | 137.2 | 67.3 | 152.14 | 2/2 | 164,521.5 | 8,805 | 161,827.5 | 150.09 |

Strata实际部署四方：表内为2轮中位，严格次数和编辑分保留每轮结果。

**结果与差距**：18组最终文件金额正确。共同Orca仍有契约失败，部分备忘录把R02待处理1.20元误计或状态写错；共同Unsloth首轮称O02已退4.60，真实仅3.40。另有中文字面failure_recovery误判，原48/49保留。

### 长程整项｜程序、闭环与编辑审读

原严格成绩不改；文件/reference/manifest、阶段收尾与备忘录分开。

| 具体模型 / 量化 / 引擎 | Prefill / token/s | Decode / token/s | 完整等待 / 秒 | 严格通过 / 轮 | API输入 / token | 输出含思考 / token | 缓存 / token | API累计等待 / 秒 |

| --- | --- | --- | --- | --- | --- | --- | --- | --- |

| Qwen3.8 Next Flash · GSQ IQ3_S · llama.cpp b11829 | 134.7 | 20.7 | 1,296.56 | 0/2 | 370,435 | 22,089 | 341,267.5 | 1,288.61 |

| Qwen3.8 Next Flash · SC117去拒答 IQ3_S · llama.cpp b11829 | 132.7 | 20.6 | 1,190.64 | 1/2 | 349,139.5 | 19,807 | 320,673 | 1,182.70 |

| Qwen3.8 Next Flash · Unsloth UD-Q3_K_XL · llama.cpp b11829 | 120.5 | 17.7 | 1,784.70 | 1/2 | 407,367 | 26,268.5 | 372,494.5 | 1,776.95 |

| Qwen3.8 Next Flash · OrcaRouter去拒答 Q3_K_L · llama.cpp b11829 | 108.7 | 16.6 | 1,925.87 | 0/2 | 426,441 | 25,956 | 388,582 | 1,917.98 |

| Qwen3.8 Next Flash · Swift1.5后训练 IQ3_S · llama.cpp b11829 | 136.6 | 20.8 | 1,396.01 | 0/2 | 472,915.5 | 23,351 | 437,602 | 1,387.54 |

共同llama.cpp五方：表内为2轮中位，严格次数和编辑分保留每轮结果。

| 具体模型 / 量化 / 引擎 | Prefill / token/s | Decode / token/s | 完整等待 / 秒 | 严格通过 / 轮 | API输入 / token | 输出含思考 / token | 缓存 / token | API累计等待 / 秒 |

| --- | --- | --- | --- | --- | --- | --- | --- | --- |

| Qwen3.8 Next Flash · GSQ IQ3_S · Strata0.1.47 | 214.0 | 58.2 | 507.16 | 0/2 | 437,256.5 | 24,145.5 | 419,324.5 | 498.80 |

| Qwen3.8 Next Flash · SC117去拒答 IQ3_S · Strata0.1.47 | 216.1 | 55.8 | 401.28 | 0/2 | 362,083.5 | 17,637 | 345,463 | 393.82 |

| Qwen3.8 Next Flash · Unsloth UD-Q3_K_XL · Strata0.1.47 | 191.0 | 48.7 | 547.58 | 0/2 | 387,721.5 | 21,627 | 369,307.5 | 539.64 |

| Qwen3.8 Next Flash · Swift1.5后训练 IQ3_S · Strata0.1.47 | 217.6 | 59.7 | 484.14 | 0/2 | 349,474 | 23,919.5 | 332,850.5 | 476.87 |

Strata实际部署四方：表内为2轮中位，严格次数和编辑分保留每轮结果。

**结果与差距**：原严格完整次数：共同SC117与Unsloth各1/2，其他0/2。再纳入实际备忘录编辑门槛，只有共同SC117首轮同时满足全链；共同Unsloth首轮的金额误写被编辑否决。Strata-SC117完整401.28秒最快，文件2/2正确，却不能据此称无人监督完整交付。

### LC01｜实际109186-token输入

每个部署两轮实际API输入均109186；单次长上下文，不是长程历史累计。

| 具体模型 / 量化 / 引擎 | Prefill / token/s | Decode / token/s | 完整等待 / 秒 | 严格通过 / 轮 | API输入 / token | 输出含思考 / token | 缓存 / token | API累计等待 / 秒 |

| --- | --- | --- | --- | --- | --- | --- | --- | --- |

| Qwen3.8 Next Flash · GSQ IQ3_S · llama.cpp b11829 | 144.3 | 17.8 | 909.99 | 1/2 | 109,186 | 2,696 | 23 | 909.81 |

| Qwen3.8 Next Flash · SC117去拒答 IQ3_S · llama.cpp b11829 | 145.0 | 17.9 | 938.51 | 1/2 | 109,186 | 3,283 | 23 | 938.34 |

| Qwen3.8 Next Flash · Unsloth UD-Q3_K_XL · llama.cpp b11829 | 128.8 | 16.0 | 1,015.72 | 0/2 | 109,186 | 2,638.5 | 23 | 1,015.55 |

| Qwen3.8 Next Flash · OrcaRouter去拒答 Q3_K_L · llama.cpp b11829 | 119.8 | 15.8 | 1,228.97 | 1/2 | 109,186 | 5,080.5 | 23 | 1,228.80 |

| Qwen3.8 Next Flash · Swift1.5后训练 IQ3_S · llama.cpp b11829 | 143.9 | 17.8 | 900.02 | 0/2 | 109,186 | 2,476 | 23 | 899.85 |

共同llama.cpp五方：表内为2轮中位，严格次数和编辑分保留每轮结果。

| 具体模型 / 量化 / 引擎 | Prefill / token/s | Decode / token/s | 完整等待 / 秒 | 严格通过 / 轮 | API输入 / token | 输出含思考 / token | 缓存 / token | API累计等待 / 秒 |

| --- | --- | --- | --- | --- | --- | --- | --- | --- |

| Qwen3.8 Next Flash · GSQ IQ3_S · Strata0.1.47 | 1,100.6 | 63.0 | 145.09 | 1/2 | 109,186 | 2,863 | 0 | 144.91 |

| Qwen3.8 Next Flash · SC117去拒答 IQ3_S · Strata0.1.47 | 1,104.8 | 60.5 | 147.29 | 1/2 | 109,186 | 2,918 | 0 | 147.11 |

| Qwen3.8 Next Flash · Unsloth UD-Q3_K_XL · Strata0.1.47 | 1,003.8 | 53.1 | 164.24 | 1/2 | 109,186 | 2,922.5 | 0 | 164.07 |

| Qwen3.8 Next Flash · Swift1.5后训练 IQ3_S · Strata0.1.47 | 1,101.2 | 63.2 | 128.68 | 1/2 | 109,186 | 1,837.5 | 0 | 128.51 |

Strata实际部署四方：表内为2轮中位，严格次数和编辑分保留每轮结果。

**结果与差距**：没有一个部署2/2。共同Unsloth/Swift0/2，其余均1/2。主要失败是漏D-REFUND、把policy_version写P-V2、ignored多P-V1；Orca共同次轮还把ignored扩写429条填充ID，8192输出截断成非法JSON。正确金额/路由不能替代精确证据与接口。

### 固定512输出吞吐：4K/32K无缓存，短输入有复用

全部固定输出512 token、关闭思考、三轮。4K实际4057输入、32K实际32713输入，所有Q3部署三轮均cache0。短67输入的Strata后两轮缓存60、新算7，不能叫三轮冷启动；短Prefill也不代表长输入能力。

### 吞吐｜4057输入 / 固定512输出

关闭思考，三轮中位；只测吞吐，不评输出内容。

| 具体模型 / 量化 / 引擎 | Prefill / token/s | Decode / token/s | 完整等待 / 秒 | 严格通过 / 轮 | API输入 / token | 输出含思考 / token | 缓存 / token | API累计等待 / 秒 |

| --- | --- | --- | --- | --- | --- | --- | --- | --- |

| Qwen3.8 Next Flash · GSQ IQ3_S · llama.cpp b11829 | 184.9 | 23.3 | 44.55 | 吞吐，不评内容 | 4,057 | 512 | 0 | 44.55 |

| Qwen3.8 Next Flash · SC117去拒答 IQ3_S · llama.cpp b11829 | 180.6 | 21.7 | 46.20 | 吞吐，不评内容 | 4,057 | 512 | 0 | 46.20 |

| Qwen3.8 Next Flash · Unsloth UD-Q3_K_XL · llama.cpp b11829 | 158.1 | 19.7 | 52.32 | 吞吐，不评内容 | 4,057 | 512 | 0 | 52.32 |

| Qwen3.8 Next Flash · OrcaRouter去拒答 Q3_K_L · llama.cpp b11829 | 146.3 | 18.9 | 55.93 | 吞吐，不评内容 | 4,057 | 512 | 0 | 55.93 |

| Qwen3.8 Next Flash · Swift1.5后训练 IQ3_S · llama.cpp b11829 | 183.6 | 20.7 | 47.10 | 吞吐，不评内容 | 4,057 | 512 | 0 | 47.10 |

共同llama.cpp五方：表内为3轮中位，严格次数和编辑分保留每轮结果。

| 具体模型 / 量化 / 引擎 | Prefill / token/s | Decode / token/s | 完整等待 / 秒 | 严格通过 / 轮 | API输入 / token | 输出含思考 / token | 缓存 / token | API累计等待 / 秒 |

| --- | --- | --- | --- | --- | --- | --- | --- | --- |

| Qwen3.8 Next Flash · GSQ IQ3_S · Strata0.1.47 | 922.8 | 66.9 | 12.04 | 吞吐，不评内容 | 4,057 | 512 | 0 | 12.04 |

| Qwen3.8 Next Flash · SC117去拒答 IQ3_S · Strata0.1.47 | 938.4 | 67.3 | 11.99 | 吞吐，不评内容 | 4,057 | 512 | 0 | 11.99 |

| Qwen3.8 Next Flash · Unsloth UD-Q3_K_XL · Strata0.1.47 | 819.3 | 56.8 | 14.09 | 吞吐，不评内容 | 4,057 | 512 | 0 | 14.09 |

| Qwen3.8 Next Flash · Swift1.5后训练 IQ3_S · Strata0.1.47 | 929.2 | 66.9 | 12.20 | 吞吐，不评内容 | 4,057 | 512 | 0 | 12.20 |

Strata实际部署四方：表内为3轮中位，严格次数和编辑分保留每轮结果。

**结果与差距**：Strata四套Prefill819—938、Decode57—67token/s，共同引擎Prefill146—185、Decode19—23。同一套部署同时改变CPU/GPU专家放置与MTP；这里给完整部署速度，不单独宣称量化或MTP的净贡献。

### 吞吐｜32713输入 / 固定512输出

关闭思考，三轮中位；只测吞吐，不评输出内容。

| 具体模型 / 量化 / 引擎 | Prefill / token/s | Decode / token/s | 完整等待 / 秒 | 严格通过 / 轮 | API输入 / token | 输出含思考 / token | 缓存 / token | API累计等待 / 秒 |

| --- | --- | --- | --- | --- | --- | --- | --- | --- |

| Qwen3.8 Next Flash · GSQ IQ3_S · llama.cpp b11829 | 165.0 | 22.5 | 222.06 | 吞吐，不评内容 | 32,713 | 512 | 0 | 222.06 |

| Qwen3.8 Next Flash · SC117去拒答 IQ3_S · llama.cpp b11829 | 165.3 | 22.2 | 221.84 | 吞吐，不评内容 | 32,713 | 512 | 0 | 221.84 |

| Qwen3.8 Next Flash · Unsloth UD-Q3_K_XL · llama.cpp b11829 | 148.6 | 18.5 | 249.70 | 吞吐，不评内容 | 32,713 | 512 | 0 | 249.70 |

| Qwen3.8 Next Flash · OrcaRouter去拒答 Q3_K_L · llama.cpp b11829 | 136.2 | 16.5 | 269.52 | 吞吐，不评内容 | 32,713 | 512 | 0 | 269.52 |

| Qwen3.8 Next Flash · Swift1.5后训练 IQ3_S · llama.cpp b11829 | 165.0 | 20.6 | 224.33 | 吞吐，不评内容 | 32,713 | 512 | 0 | 224.33 |

共同llama.cpp五方：表内为3轮中位，严格次数和编辑分保留每轮结果。

| 具体模型 / 量化 / 引擎 | Prefill / token/s | Decode / token/s | 完整等待 / 秒 | 严格通过 / 轮 | API输入 / token | 输出含思考 / token | 缓存 / token | API累计等待 / 秒 |

| --- | --- | --- | --- | --- | --- | --- | --- | --- |

| Qwen3.8 Next Flash · GSQ IQ3_S · Strata0.1.47 | 1,178.4 | 66.7 | 35.63 | 吞吐，不评内容 | 32,713 | 512 | 0 | 35.63 |

| Qwen3.8 Next Flash · SC117去拒答 IQ3_S · Strata0.1.47 | 1,181.2 | 68.8 | 35.33 | 吞吐，不评内容 | 32,713 | 512 | 0 | 35.33 |

| Qwen3.8 Next Flash · Unsloth UD-Q3_K_XL · Strata0.1.47 | 1,062.4 | 59.4 | 39.63 | 吞吐，不评内容 | 32,713 | 512 | 0 | 39.63 |

| Qwen3.8 Next Flash · Swift1.5后训练 IQ3_S · Strata0.1.47 | 1,176.2 | 68.3 | 35.43 | 吞吐，不评内容 | 32,713 | 512 | 0 | 35.43 |

Strata实际部署四方：表内为3轮中位，严格次数和编辑分保留每轮结果。

**结果与差距**：Strata-Swift Prefill1176.23/Decode68.31，完整35.43秒；共同Swift165.01/20.56，224.33秒。同引擎IQ3_S几套吞吐很接近，Orca/Unsloth混合Q3更重。32K是吞吐，不能替代前题100K。

### 吞吐｜67输入 / 固定512输出

关闭思考，三轮中位；只测吞吐，不评输出内容。

| 具体模型 / 量化 / 引擎 | Prefill / token/s | Decode / token/s | 完整等待 / 秒 | 严格通过 / 轮 | API输入 / token | 输出含思考 / token | 缓存 / token | API累计等待 / 秒 |

| --- | --- | --- | --- | --- | --- | --- | --- | --- |

| Qwen3.8 Next Flash · GSQ IQ3_S · llama.cpp b11829 | 32.7 | 20.6 | 27.12 | 吞吐，不评内容 | 67 | 512 | 0 | 27.12 |

| Qwen3.8 Next Flash · SC117去拒答 IQ3_S · llama.cpp b11829 | 32.4 | 20.1 | 28.46 | 吞吐，不评内容 | 67 | 512 | 0 | 28.46 |

| Qwen3.8 Next Flash · Unsloth UD-Q3_K_XL · llama.cpp b11829 | 27.9 | 16.2 | 34.51 | 吞吐，不评内容 | 67 | 512 | 0 | 34.51 |

| Qwen3.8 Next Flash · OrcaRouter去拒答 Q3_K_L · llama.cpp b11829 | 24.4 | 16.5 | 34.50 | 吞吐，不评内容 | 67 | 512 | 0 | 34.50 |

| Qwen3.8 Next Flash · Swift1.5后训练 IQ3_S · llama.cpp b11829 | 35.3 | 19.8 | 28.62 | 吞吐，不评内容 | 67 | 512 | 0 | 28.62 |

共同llama.cpp五方：表内为3轮中位，严格次数和编辑分保留每轮结果。

| 具体模型 / 量化 / 引擎 | Prefill / token/s | Decode / token/s | 完整等待 / 秒 | 严格通过 / 轮 | API输入 / token | 输出含思考 / token | 缓存 / token | API累计等待 / 秒 |

| --- | --- | --- | --- | --- | --- | --- | --- | --- |

| Qwen3.8 Next Flash · GSQ IQ3_S · Strata0.1.47 | 62.4 | 73.3 | 7.14 | 吞吐，不评内容 | 67 | 512 | 60 | 7.14 |

| Qwen3.8 Next Flash · SC117去拒答 IQ3_S · Strata0.1.47 | 60.9 | 68.9 | 7.58 | 吞吐，不评内容 | 67 | 512 | 60 | 7.58 |

| Qwen3.8 Next Flash · Unsloth UD-Q3_K_XL · Strata0.1.47 | 54.0 | 61.9 | 8.45 | 吞吐，不评内容 | 67 | 512 | 60 | 8.45 |

| Qwen3.8 Next Flash · Swift1.5后训练 IQ3_S · Strata0.1.47 | 61.2 | 75.8 | 6.91 | 吞吐，不评内容 | 67 | 512 | 60 | 6.91 |

Strata实际部署四方：表内为3轮中位，严格次数和编辑分保留每轮结果。

**结果与差距**：Strata第2/3轮复用60个输入token，只新算7；全部输入token仍67。固定512输出不评内容质量，不以这段截断探针代码称可交付。

### 思考诊断｜同一道D01关闭思考

事前冻结的单题诊断，不能替代medium主成绩。

| 具体模型 / 量化 / 引擎 | Prefill / token/s | Decode / token/s | 完整等待 / 秒 | 严格通过 / 轮 | API输入 / token | 输出含思考 / token | 缓存 / token | API累计等待 / 秒 |

| --- | --- | --- | --- | --- | --- | --- | --- | --- |

| Qwen3.8 Next Flash · GSQ IQ3_S · llama.cpp b11829 | 47.1 | 23.3 | 5.09 | 0/2 | 151 | 35 | 0 | 4.92 |

| Qwen3.8 Next Flash · SC117去拒答 IQ3_S · llama.cpp b11829 | 49.6 | 23.8 | 4.51 | 0/2 | 151 | 26 | 0 | 4.33 |

| Qwen3.8 Next Flash · Unsloth UD-Q3_K_XL · llama.cpp b11829 | 43.2 | 20.5 | 5.13 | 0/2 | 151 | 26 | 0 | 4.96 |

| Qwen3.8 Next Flash · OrcaRouter去拒答 Q3_K_L · llama.cpp b11829 | 38.3 | 16.3 | 5.43 | 1/2 | 151 | 21 | 0 | 5.26 |

| Qwen3.8 Next Flash · Swift1.5后训练 IQ3_S · llama.cpp b11829 | 49.4 | 25.0 | 4.45 | 0/2 | 151 | 26 | 0 | 4.28 |

共同llama.cpp五方：表内为2轮中位，严格次数和编辑分保留每轮结果。

| 具体模型 / 量化 / 引擎 | Prefill / token/s | Decode / token/s | 完整等待 / 秒 | 严格通过 / 轮 | API输入 / token | 输出含思考 / token | 缓存 / token | API累计等待 / 秒 |

| --- | --- | --- | --- | --- | --- | --- | --- | --- |

| Qwen3.8 Next Flash · GSQ IQ3_S · Strata0.1.47 | 72.8 | 41.6 | 1.94 | 0/2 | 151 | 30.5 | 72 | 1.77 |

| Qwen3.8 Next Flash · SC117去拒答 IQ3_S · Strata0.1.47 | 68.9 | 38.6 | 1.91 | 0/2 | 151 | 26 | 72 | 1.74 |

| Qwen3.8 Next Flash · Unsloth UD-Q3_K_XL · Strata0.1.47 | 64.8 | 32.3 | 1.89 | 2/2 | 151 | 18.5 | 72 | 1.71 |

| Qwen3.8 Next Flash · Swift1.5后训练 IQ3_S · Strata0.1.47 | 75.5 | 37.1 | 1.85 | 0/2 | 151 | 26 | 72 | 1.67 |

Strata实际部署四方：表内为2轮中位，严格次数和编辑分保留每轮结果。

**结果与差距**：18个答复的id/315/公众号内容都正确，但大多数多包JSON代码围栏。Unsloth-Strata严格2/2、Orca共同1/2、其余0/2；完整等待更短却未普遍修复接口契约。不能据此建议所有任务关闭思考。

### 资源、故障与结果边界

| 具体部署 | 系统已用峰值 | VRAM峰值 | GTT峰值 | 首次ready |

| --- | --- | --- | --- | --- |

| Qwen3.8 Next Flash · GSQ IQ3_S · llama.cpp b11829 | 14.62GiB | 21.97GiB | 0.04GiB | 28.24秒 |

| Qwen3.8 Next Flash · SC117去拒答 IQ3_S · llama.cpp b11829 | 14.68GiB | 22.20GiB | 0.04GiB | 24.17秒 |

| Qwen3.8 Next Flash · Unsloth UD-Q3_K_XL · llama.cpp b11829 | 14.94GiB | 22.89GiB | 0.04GiB | 24.18秒 |

| Qwen3.8 Next Flash · OrcaRouter去拒答 Q3_K_L · llama.cpp b11829 | 14.89GiB | 20.85GiB | 0.09GiB | 26.18秒 |

| Qwen3.8 Next Flash · Swift1.5后训练 IQ3_S · llama.cpp b11829 | 14.80GiB | 22.03GiB | 0.08GiB | 24.51秒 |

| Qwen3.8 Next Flash · GSQ IQ3_S · Strata0.1.47 | 54.23GiB | 23.47GiB | 0.06GiB | 28.53秒 |

| Qwen3.8 Next Flash · SC117去拒答 IQ3_S · Strata0.1.47 | 54.15GiB | 23.48GiB | 0.05GiB | 46.47秒 |

| Qwen3.8 Next Flash · Unsloth UD-Q3_K_XL · Strata0.1.47 | 59.87GiB | 23.30GiB | 0.09GiB | 56.55秒 |

| Qwen3.8 Next Flash · Swift1.5后训练 IQ3_S · Strata0.1.47 | 54.43GiB | 23.42GiB | 0.09GiB | 54.51秒 |

资源为2秒采样。系统已用=MemTotal−MemAvailable，包含全机内核与缓存口径，不是模型独占RSS；mmap可回收页不能简单当常驻权重。VRAM与系统内存不相加成模型总占用。连续两轮和本次长输入完成不证明全天稳定。

正式矩阵前曾保留DIMM3累计4次可纠正CE及BACO/PSP驱动唤醒错误；当前正式测量启动周期读取的EDAC CE/UE均0，关键驱动事件查询未见新增。旧故障没有算成某个模型分数，也没有据此推断电源、温度或ECC根因。Orca的明确内核格式拒绝与这些历史硬件事件分开。

## 四、综合推荐：先过门槛，再比较质量与等待

| 具体部署 | 加权质量/100 | 严格短题 | 七题等待几何均值 | 原长程完整 | 100K严格 | 长程编辑/20 |

| --- | --- | --- | --- | --- | --- | --- |

| Qwen3.8 Next Flash · GSQ IQ3_S · llama.cpp b11829 | 81.46 | 10/14 | 63.53秒 | 0/2 | 1/2 | 20/19 |

| Qwen3.8 Next Flash · SC117去拒答 IQ3_S · llama.cpp b11829 | 83.75 | 10/14 | 56.93秒 | 1/2 | 1/2 | 20/15 |

| Qwen3.8 Next Flash · Unsloth UD-Q3_K_XL · llama.cpp b11829 | 95.50 | 12/14 | 56.38秒 | 1/2 | 0/2 | 14/20 |

| Qwen3.8 Next Flash · OrcaRouter去拒答 Q3_K_L · llama.cpp b11829 | 83.25 | 10/14 | 65.44秒 | 0/2 | 1/2 | 13/12 |

| Qwen3.8 Next Flash · Swift1.5后训练 IQ3_S · llama.cpp b11829 | 90.92 | 12/14 | 54.42秒 | 0/2 | 0/2 | 20/20 |

| Qwen3.8 Next Flash · GSQ IQ3_S · Strata0.1.47 | 89.71 | 9/14 | 27.16秒 | 0/2 | 1/2 | 20/20 |

| Qwen3.8 Next Flash · SC117去拒答 IQ3_S · Strata0.1.47 | 89.50 | 10/14 | 27.04秒 | 0/2 | 1/2 | 20/20 |

| Qwen3.8 Next Flash · Unsloth UD-Q3_K_XL · Strata0.1.47 | 92.70 | 11/14 | 27.29秒 | 0/2 | 1/2 | 20/20 |

| Qwen3.8 Next Flash · Swift1.5后训练 IQ3_S · Strata0.1.47 | 92.88 | 11/14 | 21.09秒 | 0/2 | 1/2 | 20/20 |

**综合推荐：这台RX7900 XTX的本轮常规短工作候选，优先Qwen3.8 Next Flash Unsloth UD-Q3_K_XL＋llama.cpp b11829。** 它与共同Swift都达到12/14且无越权；95.50比90.92高4.58分，超过事前3分的速度决胜范围，因此不能为更快而改用另一套。推荐涵盖本轮通过的短代码、受控Agent、提取与事实短讯；复杂决策备忘录仍失败，不能免去校验。

Strata四套都没有达到常规12/14门槛。若工作流已有严格JSON校验、可测试代码和人工事实核对，可优先试Strata-Swift1.5 IQ3_S的已通过具体任务：本轮七题等待几何均值21.09秒，32K固定输出约35.43秒；它是后训练成品，不冒充原版权重量化优胜。原版GSQ-Strata读取更快、兼容路径更直接；Unsloth-Strata也已真实跑通，适合需要该原版混合量化身份、能接受小投影BF16转换及额外等待的受控场景。

SC117去拒答版本轮有一轮经编辑审读的长程全链通过，但常规短题10/14、另一轮长程仍失败，不能把去拒答当普遍质量升级。OrcaRouter去拒答Q3_K_L在llama.cpp的复杂代码两轮正确，但更重、更慢，备忘录空正文；本轮Strata固定版本又被专家内核拒绝，没有综合优势。

100K精确证据交付没有任何部署2/2，不推荐把本类文档直接自动分流。18轮工程文件都正确，也没有一套两轮同时通过阶段闭环与最终备忘录审读。最实际的分工是把可测试代码与受控工具交给模型，把严格接口、版本证据和业务金额留在独立校验里。

### 完整提示词、预算与可复算材料

[公开研究与冻结题库](https://github.com/rffanlab/llm_eval/tree/main/studies/2026-10-23-qwen38-next-flash-q3-five-way)。附录列出完整system/user提示词、工具协议、评分源码、两轮完整100K材料TXT与逐轮数据；所有原始失败和冻结评分保持。模型量化分发遵守原仓库及Qwen Community License1.0，题库与原始评测产物的许可单独标识。