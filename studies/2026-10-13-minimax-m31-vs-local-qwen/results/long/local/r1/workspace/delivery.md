# 最终交付说明

最终金额（源 release/summary.json）：已付40.21元、退款5.51元、净额34.70元；客户净额 A=24.80元、B=9.90元。截止时间2026-10-04T23:59:59Z。

迟到退款：R04（O02，3.40元，succeeded，2026-10-04T20:00:00Z，见 data/final/refunds.csv）在截止内计入，总净额较38.10元降至34.70元，减少3.40元，订单本金不变。

排除项：订单O05（创建于截止后）；退款R02（pending状态）；退款R03（超过截止时间）。

兼容性：reconcile保留全部v1行为（policy="v1"原契约不变），v2支持截止、退款状态、多位小数HALF_UP取整。

测试：8次可见测试全部通过（base_exact、empty、v1_precision、order_duplicate_conflict、unknown_refund、v2_exact、v2_cutoff_missing、v2_inclusive_round_each）；v2首次发布遇宿主注入ENOSPC，工具确认旧版未损且故障已清除，重试后发布成功；final发布与reconcile结果一致。独立隐藏验收不会反馈，不能声称其已通过。

风险：若R02后续转为succeeded，将再减净额1.20元；后续退款若使累计退款超过已付将抛ValueError；金额逐条HALF_UP取整使合计与原值可有±0.01元偏差。
