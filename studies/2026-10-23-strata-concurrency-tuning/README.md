# Strata双并发：参数解析与复跑工具

这是源码核对与调参方法配套材料，**没有新增本机双并发实验成绩**。不能将本目录脚本生成、HTTP成功或配置文件有效当作性能收益、质量通过。官方其他硬件示例与已有本地单路控制分开标注。

## 固定来源

Strata v0.2.2，commit `011c9e600a93bbc9fd451c563501b5831c32bbca`。参数映射在`serve/server.py::parallel_args`，调度说明见同commit的`docs/BATCHING.md`。采集清单见sources.json。

## 复跑顺序

停止下载、复制和哈希等大文件I/O，检查实际服务进程、内存/VRAM/GTT及启动配置。一个模型单实例，以配置副本逐个重启，不同时启动多个模型。保持GPU功耗、引擎包、GGUF、聊天模板、MTP、线程等条件一致。保存真实版本、引擎日志、配置脱敏副本和文件SHA。

| 条件 | 服务 | 客户端 | 唯一目的 |
| --- | --- | ---: | --- |
| A | parallel1 | 1 | 单用户起点 |
| B | parallel2 | 1 | 槽位预留代价 |
| C | parallel1 | 2同时提交 | 两任务排队基线 |
| D | parallel2 | 2同时提交 | 真双并发 |
| E | D追加batch-mtp | 2 | 批量MTP影响 |
| F | E只改prefill2048 | 2 | 分块对调度影响 |
| G | F只改decode_share1.0 | 2 | 输入与生成时间分配 |

每组至少三轮，配置交错并保留顺序。C与D/E比较同一对题目；A与B比较同一单题。冷缓存/生产暖缓存分别报告，工具不主动清缓存。它们是吞吐探针，质量另外用既有冻结题库功能断言、Agent权限、写作编辑量表、连续四阶段长程与100K以上长上下文验收。不要以短吞吐探针替代长程或长上下文。

建议预先门槛：相同两任务的整批等待中位至少改善5%，没有新增失败/越权；TTFT与最长生成停顿满足事前填写的业务响应上限。5%是筛选建议，并非已测收益或统计显著结论。质量不能退步，资源余量必须记录。

```sh
python profile_patch.py base.json --output p2.json --parallel 2
python profile_patch.py base.json --output p2-mtp.json --parallel 2 --batch-mtp
python profile_patch.py base.json --output p2-mtp-smallchunk.json --parallel 2 --batch-mtp --prefill 2048
# 用副本正常启动服务；下面只请求已经运行的API。
python concurrent_probe.py --label p1-c2 --clients 2 --prompts prompts.json --repeats 3 --output results/p1-c2
python concurrent_probe.py --label p2-c2 --clients 2 --prompts prompts.json --repeats 3 --output results/p2-c2
```

配置工具拒绝覆盖，私有副本可能含已有凭据，不提交副本。API key只从EVAL_API_KEY读取，不输出到记录。

首个实际content/reasoning片段才记为TTFT，role和保活不算。整批HTTP输出token/s以全部输出除整批墙钟；服务原生timings仅保留原始字段，不用墙钟反推原生Prefill/Decode。并发下原生窗口可能共享，先按实际版本审计计数，不能把两条重叠时间直接求和视为整机计算时间。原生缺失保持未知。

本版不自动采集GPU/内存、不验证代码或文章质量、不自动管理服务。执行者必须另保存资源日志并完成质量评测。原始响应、usage、finish_reason、失败和每轮文件均保留，不择优覆盖。
