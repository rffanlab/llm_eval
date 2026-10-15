# 最终交付
截止时间2026-10-04T23:59:59Z。以release/summary.json为准：已付40.21元、退款5.51元、净额34.70元；客户净额A 24.80元、B 9.90元。
迟到退款：data/final/refunds.csv新增R04（O02，3.40元，succeeded，截止前），计入后总净额较v2发布减少3.40元（38.10→34.70），订单本金40.21元不变。
排除项：订单O05（截止后创建）、退款R02（pending）、退款R03（截止后），均不计入。
兼容性：v1契约与旧CSV行为保留，workflow.py同时支持policy v1/v2。
测试证据：visible测试8/8通过（含base_exact、v2_exact、v2_inclusive_round_each等）；首次发布v2时遇到ENOSPC注入故障，旧版未受影响，故障清除后重试成功；final数据集一次发布成功，已复核release/orders.csv、customers.csv、summary.json与manifest一致。
风险：R02若转为succeeded将再减净额1.20元，需重新对账；R04迟到说明上游退款落库可能晚于截止，建议固化重跑机制；隐藏验收未由我方执行，不声称其结果。
