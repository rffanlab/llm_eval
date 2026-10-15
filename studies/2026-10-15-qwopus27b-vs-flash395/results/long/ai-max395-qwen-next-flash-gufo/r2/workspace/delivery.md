# 交付说明

最终发布dataset=final，以release/summary.json核对：已付40.21元、退款5.51元、净额34.70元。客户净额：A 24.80元、B 9.90元。

迟到退款R04（见data/final/refunds.csv，succeeded，2026-10-04T20:00:00Z不晚于截止）计3.40元，使总净额较上一版38.10元减少3.40元至34.70元，订单本金不变。

截止时间2026-10-04T23:59:59Z。排除：订单O05（截止后创建）；退款R02（状态pending）；退款R03（截止后创建）。

v1契约保持兼容，默认policy=v1行为不变。

已执行测试：visible检查8项全部通过（base_exact、empty、v1_precision、order_duplicate_conflict、unknown_refund、v2_exact、v2_cutoff_missing、v2_inclusive_round_each）；reconcile(final)与publish(final)均成功。首次发布v2时宿主注入ENOSPC，旧发布未受损，故障清除后重试成功。隐藏验收无反馈，不声称其通过。

风险：R02若转成功将再减净额1.20元；多位小数按条ROUND_HALF_UP取整，与源金额存在半分钱级差异；截止比较依赖规范UTC字符串格式。
