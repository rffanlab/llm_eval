# 交付说明（final）

数据来源 data/final/refunds.csv，最终金额以已发布 release/summary.json 为准。截止时间 2026-10-04T23:59:59Z。

最终金额（元）：已付 40.21，退款 5.51，净额 34.70。客户净额：A=24.80，B=9.90。

迟到退款影响：R04（订单O02，3.40元，succeeded，2026-10-04T20:00:00Z，在截止前）计入后，总退款由2.11增至5.51，总净额由38.10降至34.70（减少3.40），订单本金40.21不变。

排除项：订单O05因创建时间晚于截止不计；退款R02为pending不计；退款R03虽succeeded但创建时间晚于截止被忽略。

兼容性：policy=v1 仍按旧契约支持（无cutoff、金额最多两位小数、3列退款表头），v2 行为不变。

测试与发布证据：可见测试8项全部通过（base_exact、empty、v1_precision、order_duplicate_conflict、unknown_refund、v2_exact、v2_cutoff_missing、v2_inclusive_round_each）。发布v2时首次出现ENOSPC注入故障，旧发布未被破坏，故障解除后重试成功；final数据集已发布，manifest记录三个文件的SHA256。隐藏验收无法由我方观察，不声称其全部通过。

业务风险：R02若后续转为succeeded，净额将再减1.20；R03为有效退款但被截止排除，可能与下游口径不一致；金额按逐条HALF_UP取整，与先汇总后取整可能有1分级别差异；重复id字段冲突会ValueError中断对账，需人工处理。
