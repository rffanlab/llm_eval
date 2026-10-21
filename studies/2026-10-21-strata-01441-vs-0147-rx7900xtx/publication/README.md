# 7900 XTX跑Qwen3.8 Next Flash：Strata三版本实测

同一RX7900 XTX、265W、Qwen3.8 Next Flash UD-Q4_K_XL，比较Strata引擎0.1.44.1、0.1.46、0.1.47。

本文按为什么做、怎么做、逐题结果组织；七道短题、四阶段长程、思考诊断和固定吞吐均保留三版对照与逐项结论。32K仅为吞吐探针，不作为100K+长上下文理解成绩。

- `wechat-richtext.html`：带复制按钮的内联富文本。
- `bilibili-script.md`、`bilibili-chapters.txt`、`bilibili-release.txt`：视频文案。
- `prompts-and-rubric.md`：冻结题面与标准。
- `evidence-ledger.json`：原始结果路径与哈希。
- `core-native-counter-audit.json`：核心混合任务原生速度汇总。
- `media-manifest.json`：成片哈希与公开资产清单。

综合推荐0.1.47。它维持原版短题交付数并缩短等待；0.1.46在固定生成探针中更快。复杂写作、严格JSON与连续阶段收尾仍有失败。
