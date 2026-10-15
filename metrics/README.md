# 原生计算速度

`native_speed.py`仅聚合已保存记录，不发起API调用。

- 工作轮内：`Σprompt_n × 1000 / Σprompt_ms`、`Σpredicted_n × 1000 / Σpredicted_ms`。
- 独立工作轮间：取上述速度的中位数；不直接平均每次调用速率。
- `prompt_n`为新计算输入，缓存复用`cache_n`另列。`predicted_n`使用引擎原生生成数，不将正文和工具参数都算作思考。
- 某轮任一调用缺少对应计时、字段非有限数或计时非正，则该轮对应整体速度未知；保留有效覆盖量。某组任一轮未知时，不把余下轮次的中位数声称为完整组中位。
- 原生计算耗时与API、工具和完整工作等待分别报告。整项长程重算全部调用，不平均阶段速度。

示例导出器：`studies/2026-10-15-strata-4060ti-vs-ai-max395/aggregate_native_speeds.py`。边界核对：`python -m unittest discover -s tests -p test_native_speed.py`。
