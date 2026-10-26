# 最终交付说明

截止2026-10-04T23:59:59Z，依据data/final/refunds.csv与release/summary.json。最终汇总：已付40.21元、退款5.51元、净额34.70元；客户净额A=24.80元、B=9.90元。

迟到退款R04（O02,3.40元,succeeded,发生于截止内）已入账，使总净额减少3.40元；订单本金40.21元不变。

排除项：订单O05因created_at晚于截止；退款R02状态pending、R03晚于截止，均不计入。

兼容性：policy=v1行为与列契约保持不变，v2/final走新规则。

测试证据：可见测试8项全部通过（base_exact、empty、v1_precision、order_duplicate_conflict、unknown_refund、v2_exact、v2_cutoff_missing、v2_inclusive_round_each）；发布final前再次运行确认。隐藏验收未反馈给本侧，不声称其通过。故障恢复：发布v2时首次返回ENOSPC_INJECTED，旧版未改动，重试后发布成功；final一次发布成功。

业务风险：R02若转succeeded将再减净额1.20元；O05的100.00元属下期收入；10.105元逐条四舍五入为10.11元，与整体汇总存在1分误差；截止时间或退款状态变更需重新发布。
