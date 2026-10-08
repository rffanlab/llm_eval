# 本期部署与复跑配置

## 固定来源

精确模型 revision、文件 SHA-256 与引擎 manifest 见 `sources.json`。本期比较的是以下组合：

| profile | 引擎 | 主权重 |
| --- | --- | --- |
| old-w4b | 0.9.1 | qwen38-flash-next-w4b.hgn，配套 overlay |
| new-v2 | 0.17.2 | qwen38-flash-next-v2.hgn |
| swift-v2 | 0.17.2 | qwen38-flash-next-v2-swift15.hgn，普通 Swift 1.5 |
| new-w4b-control | 0.17.2 | 与 old-w4b 完全相同的 W4B＋overlay，单列辅助 |

v2 和 Swift 使用同一份 `qwen38-flash-next-ngram.hgn`、tokenizer 和 vision tower。本次仅测文本，vision tower 保留但没有图片输入。tokenizer 的六个文件与现有版本逐个 SHA-256 相同。模型请求 alias 统一为 `Qwen/Qwen3.8-Flash-Next`，alias 不能用来辨认权重；必须结合 profile 和启动配置。

## 机器和软件

- Ryzen AI Max+ 395，Radeon 8060S / gfx1151，128GB 统一内存。
- Ubuntu 24.04.5 LTS；Linux 7.0.0-31-generic。
- Docker，Halogen GPU 容器；没有外置 GPU，没有使用 NPU，没有并发压力测试。
- 各组健康、缓存、空闲状态、内存和镜像身份快照保存到 `environment/`。加载耗时不混入题目时间。
- 原 systemd 单元和 0.9.1 镜像保留；实验使用临时候选容器，结束后恢复原服务。

## 各组一致的设置

```text
HALOGEN_MODEL_ID=Qwen/Qwen3.8-Flash-Next
HALOGEN_CTX=262144
HALOGEN_KV_POOL_POSITIONS=262144
HALOGEN_KV_SLOTS=1
HALOGEN_CACHE_ENTRIES=4
HALOGEN_PROMPT_CACHE=2
HALOGEN_MAX_TOKENS_DEFAULT=16384
HALOGEN_MAX_TOKENS_CAP=65536
HALOGEN_REASONING_EFFORT=medium
HALOGEN_QUEUE_TIMEOUT=3600
HALOGEN_VERBOSE=1
HALOGEN_TOKENIZER=/models/tokenizer
HALOGEN_VISION_TOWER=/models/qwen38-flash-next-vision.hgn
```

v2/Swift 另外设置 `HALOGEN_CHECKPOINT` 为对应文件、`HALOGEN_NGRAM_TABLE` 为独立 ngram 文件。W4B 使用 checkpoint 里的查找表及同目录 overlay。新版本 MTP 深度沿用 0.17.2 默认动态策略；未为了获得更高速度而事后改设置。旧版保留自身默认。镜像加载设备为 `/dev/kfd` 和 `/dev/dri`，使用 host IPC、无限 memlock；模型目录只读挂载。

请求显式提供 `temperature=0`、`enable_thinking` 和每题 `max_tokens`，服务默认补入 medium。健康接口核实 `token_budget_covers_reasoning=true`。不开强制输出 schema；JSON 由模型生成后解析。

## 文件准备和存储

本地 Windows 的模型权重与大型缓存仍统一放在 D 盘。此次被测 Linux 主机沿用 `/srv/ai/models/llm` 存储；公开仓库只保存小型文本、配置说明和结果，绝不保存模型文件、内网地址、密钥或声音参考。

ngram 制品从已验证相同的旧 checkpoint 张量载荷复用，最终完整文件校验必须等于官方 SHA-256。Swift 复用与 stock v2 相同的载荷，再拼接作者发布的 header 和附加载荷，整个最终文件必须与作者公布的完整 SHA-256 相同。它是节省重复下载的字节复用，没有自行再量化或重做微调；完整哈希不符则不加载。

## 调用入口

详见 `task-cards.md` 与仓库根目录 `runner.py`、`overthinking_runner.py`。每组串行，一次只运行一个配置。先确认引擎健康、队列为空，下载和校验已停止，再做单独预检，随后运行注册顺序。记录 cache_n、完整客户端时间和服务器 prefill/decode 分别计时。

测试请求时间包含模拟工具往返，不包括独立代码评分或编辑审读。首次请求与重复请求的提示缓存状态分别保留；已有权重/操作系统缓存不等于整机冷启动。
