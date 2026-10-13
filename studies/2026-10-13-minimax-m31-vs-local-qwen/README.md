# 本地AI Max+395：Qwen3.8 Next Flash与MiniMax M3.1 Flash Preview工作对照

2026-10-13完成。先冻结、逐案例主动发起、保留失败。36个正式案例：28个短题、4个思考档位诊断、4个连续长程会话，共204次API调用；完整已知用量3,000,259token（含诊断），不等于套餐扣费或单次上下文。

| 指标 | 本地 Qwen3.8 Next Flash/Gufo | MiniMax M3.1 Flash Preview |
| --- | --- | --- |
| 短题完整交付 | 10/14 | 9/14 |
| 短题硬要求通过 | 10/14 | 11/14 |
| 长程最终文件正确 | 2/2 | 1/2 |
| 严格完整长程 | 0/2 | 0/2 |
| 长程等待中位秒 | 542.48 | 250.85 |
| 长程两轮输入token | 838750 | 1919096 |
| 长程两轮输出token | 53710 | 105897 |

综合优先本地带测试开发；MiniMax M3.1 Flash Preview简单代码与短文更快。功能相同才把速度用于推荐。云端中位包含失败，量化、思考深度与历史策略不同，非等深度模型总榜。编辑分由不盲代理审读给出，不代替真人批准。

## 为什么、方法、结果

- [逐题公众号文章](publication/wechat-article.md) · [可复制富文本HTML](publication/wechat-richtext.html)
- [B站旁白脚本](publication/bilibili-script.md) · [发布文案和实际章节](publication/bilibili-release.md) · [镜头与来源](publication/director-plan.md)
- [短题完整系统提示词、题面与验收](task-cards.md) · [长程全部文件、工具及验收](long-horizon/README.md)
- [冻结协议](protocol.md) · [字节清单](freeze.json) · [环境与权重身份](environment.json)
- [结果汇总](summary.json) · [原始SSE、工具、快照、产物](results) · [全轮计时CSV](all-turn-timings.csv)
- [审读](editorial-review.json) · [分数解释及usage标志复核](adjudications.json) · [机械审计](audit.json)
- [不计分兼容探针](preflight) · [视频核验与SHA256](publication/final-media-audit.json)

本期长程使用1.1.1提供方原生适配冻结副本；不覆盖上一期1.0.1。每阶段12回复含收尾、每次8192输出、整项65536输出和2400秒。最终文件正确但没有预算内收尾仍未完整交付；报告金额风险方向也单独审读。小题档位对照只解释D01。

## 复跑

Python标准库即可。保持本目录字节（Git已配置-text），运行前校验freeze.json。将EVAL_BASE_URL/EVAL_API_KEY/EVAL_MODEL放进进程环境，不写入配置或Git。EVAL_GUARD_COMMAND为JSON数组：本地须验证单模型、就绪和可用内存；云端只验证调用宿主资源，不能冒称云端模型显存。两端的实际payload、参数与原生历史保留方式在每次calls中。

```
python short_runner.py --provider local --task D01 --round 1 --output ./private-short-results
python long-horizon/runner.py --provider local --profile local --round 1 --output ./private-long-results
```

通过个人Token Plan调用时，在主动会话逐案例发起和审读，不提供无人值守套件批量入口；遵守对应账户套餐。输入均为公开合成夹具，密钥、内网连接和私密本人音色原声均不入本库。
