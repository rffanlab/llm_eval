# 运行中观察与可比性限制

- 题库/评分首次冻结提交：`42cec2a`。运行前已推送。
- W01 官方 r1 请求 `max_tokens=2048`，返回 `completion_tokens=2129`、其中 `reasoning_tokens=2051`，正常 stop。本地 `/health` 明确 `token_budget_covers_reasoning=true`。同名预算字段的实际执行口径不完全相同；保留原始请求与用量，不事后截掉官方内容或改变某端参数。结果属于原生配置的工作体验比较，不能据此证明等算力/等思考预算条件下的模型能力差。
- 官方模型只返回 `qwen3.8-flash` alias；本地为开放权重的 HGN W4B 运行制品。缺少官方权重 revision，不把差异单独归因量化。
- 137 当前 structured_output 显示 disabled / VOCAB failed，故本次两边均不使用 JSON schema 强制解码。此状态为环境观察，不在测试途中修复后挑优报分。
- 原始结果只保存最终回复与思考字符数，模型思考文本不入公开库；usage 原字段保留，reasoning_tokens 已包含在 completion 中，不重复求和。
- C03 官方 r1 在240.1141秒发生读取超时，未返回usage。该条记录的零是初始化累计值，不能解释为免费或零消耗；汇总token仅为已返回用量，下界而非完整账单。
- E01 本地 r1 的三个值和来源ID都正确，但sources输出为对象；冻结评分器要求按字段顺序组成数组。题面写“依顺序列出”而未显式写“数组”，存在规范歧义。保留原始严格分数，并另列语义正确性，不能把格式失败宣传为检索事实错误。本轮不更改题面重跑挑分；后续题库版本应写明JSON schema。
- 原计划写作匿名化复核未完全实现：独立编辑代理读到了provider，故实际记录为可见身份的代理复核，不声称盲评、真人审稿或用户验收。评分理由公开，主代理再次核对。
- 随后查得阿里云官方文档明确：Qwen的max_tokens仅限制回答，不包含思维链；max_completion_tokens才限制两者合计。本地健康信息明确max_tokens覆盖思考。本轮冻结接口参数因此不是同等总生成预算，W02的截断只能说明当前调用配置的交付问题，不能据此判定本地写作智力更低。官方文档：https://www.alibabacloud.com/help/zh/model-studio/qwen-api-via-openai-chat-completions （核验2026-10-07）。后续等预算版本应按端分别映射字段并验证支持；本轮不静默改字段。
