# 交付说明
依据 data/final/refunds.csv，金额以 release/summary.json 为准。截止时间 2026-10-04T23:59:59Z。
最终合计：已付40.21元、退款5.51元、净额34.70元；客户净额 A 24.80元、B 9.90元。
迟到退款R04（订单O02，3.40元，succeeded，截止前）已计入，使总净额减少3.40元，订单本金不变。
排除项：订单O05（创建于截止后）；退款R02（状态pending）、R03（截止后），均不计入。
v1契约保持兼容，行为不变。
测试：8项visible测试全部通过（base/empty/v1精度/重复冲突/未知退款/v2精确/cutoff缺失/逐条四舍五入）；v2首次发布遇ENOSPC注入故障，旧版发布未受影响，故障解除后重试成功；final一次发布成功，manifest的SHA256与发布文件一致。
发布包：release/orders.csv、release/customers.csv、release/summary.json，dataset=final。
风险：R02若后续转为成功，净额将再减少1.20元；独立隐藏验收未由我执行，不声称其通过，建议使用方按manifest独立核验；三位小数按逐条HALF_UP取整，汇总与逐单核对可能存在1分以内的口径差。
