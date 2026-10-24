# 最终交付说明

最终金额（来源：release/summary.json，输入 data/final/refunds.csv，截止 2026-10-04T23:59:59Z）：已付¥40.21，退款¥5.51，净额¥34.70。客户净额：A¥24.80，B¥9.90。

迟到退款R04（O02，¥3.40，succeeded，2026-10-04T20:00:00Z在截止内）已计入，总净额由¥38.10降至¥34.70，订单本金不变。

排除项：订单O05（截止后创建）；退款R02（pending状态）；退款R03（截止后）。R01重复行只计一次。

兼容性：reconcile同时支持policy v1/v2，v1旧金额限制与列契约保持不变。

测试：已运行visible测试8项全部通过（base_exact、empty、v1_precision、order_duplicate_conflict、unknown_refund、v2_exact、v2_cutoff_missing、v2_inclusive_round_each）。v2发布时遇到一次ENOSPC临时故障，旧发布未被改动，重试后成功；final发布一次成功，manifest的SHA256与release文件核对一致。隐藏验收未由我执行，不声称其结果。

风险：R02的pending¥1.20若后续成功需补记退款，A净额将进一步下降；三位小数金额逐条HALF_UP取整，汇总存在累计舍入差；cutoff为含边界比较，边界争议需与业务确认。
