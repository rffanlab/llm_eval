# 交付说明

最终发布（dataset=final，金额以release/summary.json为准）：付款40.21元、退款5.51元、净额34.70元；客户净额A=24.80元、B=9.90元。截止时间2026-10-04T23:59:59Z。

迟到退款：R04（O02，3.40元，succeeded，2026-10-04T20:00:00Z，见data/final/refunds.csv）已计入，总净额因此减少3.40元，订单本金不变。

排除项：O05（创建于截止后）、R02（pending）、R03（截止后）。

兼容性：v1契约与v2行为均保留。

测试：可见测试8项全部通过（base_exact、empty、v1_precision、order_duplicate_conflict、unknown_refund、v2_exact、v2_cutoff_missing、v2_inclusive_round_each）；首次发布v2时遇ENOSPC临时磁盘故障，旧发布未受损，重试后成功；final发布一次成功，manifest记录SHA256。

风险：R02 pending若后续成功需再次对账；金额含小数时逐条HALF_UP取整，每条与实际最多偏差0.005元；隐藏验收未反馈给我，不能声明其全部通过。
