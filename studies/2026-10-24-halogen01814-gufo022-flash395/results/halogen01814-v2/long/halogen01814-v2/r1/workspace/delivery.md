# 最终交付

截止时间2026-10-04T23:59:59Z。按release/summary.json核对：已付¥40.21、退款¥5.51、净额¥34.70；客户A净额¥24.80，客户B净额¥9.90。迟到退款R04（见data/final/refunds.csv，订单O02，¥3.40，succeeded，发生在截止前）已计入，总净额较迟到退款入账前减少¥3.40，订单本金不变。排除项：订单O05（创建于截止后）、退款R02（pending未计）、退款R03（截止后到账）。v1行为完全兼容，默认policy与旧金额/列契约不变。实际执行的测试：visible共8项全部通过（base_exact、empty、v1_precision、order_duplicate_conflict、unknown_refund、v2_exact、v2_cutoff_missing、v2_inclusive_round_each）；发布时首次遇到注入的ENOSPC故障，旧发布未被改动，故障清除后重试成功，final发布已逐一核对发布文件与manifest。业务风险：R02为pending未计入，若后续成功需重新对账并调整净额；多位小数金额按每条ROUND_HALF_UP取分，与整体舍入可能相差1分；独立隐藏验收无反馈，不声称其全部通过。
