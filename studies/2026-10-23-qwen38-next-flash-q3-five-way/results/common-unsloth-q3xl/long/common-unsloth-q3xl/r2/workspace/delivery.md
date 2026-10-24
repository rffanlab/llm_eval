# 最终交付说明

最终金额（依据 release/summary.json）：已付¥40.21、退款¥5.51、净额¥34.70。客户净额：A¥24.80，B¥9.90。

迟到退款：R04（O02，¥3.40，succeeded，2026-10-04T20:00:00Z，见 data/final/refunds.csv）在截止时间2026-10-04T23:59:59Z内，已计入，总净额因此减少¥3.40，订单本金不变仍为¥40.21。

排除项：O05（订单创建于截止后）、R02（退款pending未计入）、R03（succeeded但创建于截止后）。

兼容性：v1契约行为保留，v2语义不变。

测试：visible测试8项（base_exact、empty、v1_precision、order_duplicate_conflict、unknown_refund、v2_exact、v2_cutoff_missing、v2_inclusive_round_each）全部通过；发布v2时首次遇到ENOSPC注入故障，旧版本未受影响，重试后成功；final数据集发布一次成功，已核对manifest与发布文件汇总一致。独立隐藏验收不会反馈，不声称其通过。

风险：R02若后续成功，净额需再减¥1.20；R03在截止外不计，与全量账存在差异；三位小数按逐条ROUND_HALF_UP取整，每条最多±1分累积误差；若再新增迟到退款需重新对账并发布。
