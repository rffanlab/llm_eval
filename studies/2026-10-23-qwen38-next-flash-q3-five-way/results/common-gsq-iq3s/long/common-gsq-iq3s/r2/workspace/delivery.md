# 交付说明

最终对账（dataset=final，截止2026-10-04T23:59:59Z，以release/summary.json为准）：已付¥40.21，退款¥5.51，净额¥34.70；客户净额A=¥24.80，B=¥9.90。

迟到退款：R04=¥3.40（见data/final/refunds.csv，succeeded，2026-10-04T20:00:00Z≤cutoff）计入O02；订单本金不变，总净额因此减少¥3.40。

排除项：订单O05（created_at 2026-10-05晚于截止）；退款R02（状态pending）；退款R03（2026-10-05晚于截止）。

兼容性：v1契约（旧列、两位小数限制）完整保留，v2行为未改动。

测试证据：visible测试8项全部通过（base_exact、empty、v1_precision、order_duplicate_conflict、unknown_refund、v2_exact、v2_cutoff_missing、v2_inclusive_round_each）。发布v2时首次注入ENOSPC，旧发布未改动，重试成功；本次final发布一次成功并记录manifest SHA256。隐藏验收未由我执行，不声称其通过。

业务风险：R02仍pending，若后续成功需再调减净额¥1.20；R03因截止未计，若业务认定有效则存在¥1.10差异；金额逐条HALF_UP取整（10.105→10.11、2.105→2.11）可产生±1分尾差；截止比较依赖规范UTC字符串，异常格式会被拒绝。
