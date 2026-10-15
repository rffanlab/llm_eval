# 逐题、逐阶段原生速度

同为Qwen3.8 Next Flash，UD-Q4_K_XL，Strata 0.1.44.1。单位token/s；单元格为Prefill / Decode。工作题每端两轮中位，速度探针各三次中位。

| 任务或阶段 | Qwen3.8 Next Flash / RTX4060 Ti 16GB整机 | Qwen3.8 Next Flash / AI Max+395 |
|---|---:|---:|
| main/D01 | 58.6 / 29.1 | 69.8 / 45.2 |
| main/C01 | 57.2 / 31.7 | 70.5 / 48.9 |
| main/W01 | 53.9 / 35.3 | 70.6 / 49.8 |
| main/A01 | 98.9 / 27.2 | 85.5 / 43.7 |
| main/C03 | 67.0 / 31.3 | 83.6 / 42.8 |
| main/A02 | 69.8 / 25.2 | 66.8 / 39.7 |
| main/W03 | 68.7 / 34.8 | 83.6 / 47.2 |
| long/S1 | 112.1 / 29.6 | 126.4 / 42.1 |
| long/S2 | 144.7 / 29.3 | 189.4 / 45.1 |
| long/S3 | 151.9 / 31.3 | 158.4 / 45.9 |
| long/S4 | 102.4 / 31.7 | 97.7 / 43.6 |
| long/ALL | 129.2 / 30.7 | 146.1 / 44.3 |
| depth/D01 | 54.5 / 23.6 | 65.3 / 42.5 |
| speed/short512 | 32.6 / 31.9 | 74.8 / 44.8 |
| speed/prompt4k | 321.8 / 32.5 | 438.3 / 44.5 |
| speed/prompt32k | 620.2 / 31.7 | 499.1 / 42.0 |

每个工作轮先求Σ原生token/Σ原生计算秒数，再跨轮取中位。缓存复用另列，未加入Prefill分子。完整等待、工具周转、交付结果仍见[逐题文章](publication/wechat-article.md)；这些速度不能替代完整等待。

短输入固定开销较大；不能把其Prefill与无缓存4K/32K探针直接比较。没有新增推理或重评分。

[计算口径与完整逐轮数据](native-speeds.json) · [逐轮token、耗时、缓存及来源SHA CSV](native-speeds.csv) · [离线重建](aggregate_native_speeds.py) · [结果解释](reporting-clarifications.md)
