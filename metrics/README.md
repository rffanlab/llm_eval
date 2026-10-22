# 原生计算速度

`native_speed.py`仅聚合已保存记录，不发起API调用。

- 工作轮内：`Σprompt_n × 1000 / Σprompt_ms`、`Σpredicted_n × 1000 / Σpredicted_ms`。
- 独立工作轮间：取上述速度的中位数；不直接平均每次调用速率。
- `prompt_n`为新计算输入，缓存复用`cache_n`另列。`predicted_n`使用引擎原生生成数，不将正文和工具参数都算作思考。
- 某轮任一调用缺少对应计时、字段非有限数或计时非法，则该轮对应整体速度未知；保留有效覆盖量。0新计算token、0计算秒的全缓存调用是合法零工作量，见下节。某组任一轮速度未知或全缓存无定义时，不把余下轮次的中位数声称为完整组中位。
- 原生计算耗时与API、工具和完整工作等待分别报告。整项长程重算全部调用，不平均阶段速度。

示例导出器：`studies/2026-10-15-strata-4060ti-vs-ai-max395/aggregate_native_speeds.py`。边界核对：`python -m unittest discover -s tests -p test_native_speed.py`。
## 全缓存调用（2026-10-22）

`prompt_n=0`、`prompt_ms=0`表示没有新计算输入，是合法记录。在多调用工作轮中加入0 token、0秒，不使其它调用的原生计时失效。聚合器另报`prefill_zero_work_calls`（Decode有对应字段）。

整轮没有新计算时，Prefill速率无定义，保留`None`，展示为“全缓存”。重复轮次中有一轮全缓存，就逐轮列出速率与缓存状态，不能用其余轮次补一个全组中位数。正数token配0计算秒、字段缺失或非法数仍记计时不完整/未知。本次修正不覆盖历史冻结记录或已发布评分。

