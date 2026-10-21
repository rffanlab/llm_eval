# RX7900 XTX 265W跑Qwen3.8 Next Flash：Strata三版本汇总

单位：Prefill/Decode 为 token/s（3轮中位数）；吞吐探针完整等待为秒（3轮中位数）；主短题等待为14项累计；长程等待为2轮中位数。完整等待不能与不同输出量直接当作吞吐比较。0.1.47 对比百分比为相对变化，不代表智能提升。

| 指标 | Qwen3.8 Next Flash · Strata engine 0.1.44.1 | Qwen3.8 Next Flash · Strata engine 0.1.46 | Qwen3.8 Next Flash · Strata engine 0.1.47 |
|---|---:|---:|---:|
| 短题交付 | 11/14 | 10/14 | 11/14 |
| 严格长程交付 | 0/2 | 0/2 | 0/2 |
| 最终文件正确 | 2/2 | 2/2 | 2/2 |
| 主短题累计等待(s) | 698.14 | 562.21 | 542.53 |
| 主短题输出token | 27144 | 23397 | 23314 |
| 长程等待中位(s) | 711.40 | 561.47 | 649.71 |
| 短输入 Prefill | 47.2 token/s | 47.0 token/s | 46.8 token/s |
| 短输入 Decode | 45.2 token/s | 50.6 token/s | 50.3 token/s |
| 短输入 完整等待 | 11.52 s | 10.33 s | 10.38 s |
| 约4K输入 Prefill | 597.6 token/s | 594.7 token/s | 594.3 token/s |
| 约4K输入 Decode | 43.9 token/s | 48.8 token/s | 47.9 token/s |
| 约4K输入 完整等待 | 18.50 s | 17.40 s | 17.59 s |
| 约32K输入 Prefill | 929.5 token/s | 920.5 token/s | 922.1 token/s |
| 约32K输入 Decode | 44.3 token/s | 50.2 token/s | 47.2 token/s |
| 约32K输入 完整等待 | 46.88 s | 45.78 s | 46.44 s |
| 新增ECC可纠正错误 | 0 | 0 | 0 |
| 新增ECC不可纠正错误 | 0 | 0 | 0 |
| 边缘峰值温度(°C) | 63.0 | 62.0 | 62.0 |
| 热点峰值温度(°C) | 84.0 | 84.0 | 86.0 |
