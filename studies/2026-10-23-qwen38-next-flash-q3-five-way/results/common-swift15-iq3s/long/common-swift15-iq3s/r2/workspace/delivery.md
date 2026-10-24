# 交付说明
最终金额（见release/summary.json）：已付40.21元，退款5.51元，净额34.70元。客户净额：A 24.80元，B 9.90元。
迟到退款：data/final/refunds.csv中R04（O02，3.40元，succeeded，2026-10-04T20:00:00Z）在截止前计入，使总净额从38.10元降至34.70元（-3.40元），订单本金不变（40.21元）。
截止时间：2026-10-04T23:59:59Z。排除：O05（截止后订单）、R02（pending未成功）、R03（截止后退款）。
兼容性：reconcile保留policy="v1"全部旧行为；v2/final按新规则。
测试证据：visible测试8项全部通过（base_exact、empty、v1_precision、order_duplicate_conflict、unknown_refund、v2_exact、v2_cutoff_missing、v2_inclusive_round_each）。发布v2时首次publish返回ENOSPC_INJECTED（旧发布未变），重试成功；final发布一次成功，manifest含三文件SHA256。不声称隐藏测试通过。
风险：R02若转succeeded将再减A净额1.20元；R04表明退款可迟到落库，建议异步补记机制；逐条ROUND_HALF_UP取整与汇总取整可能差1分；customer按字符串分组，改名拆新客户。
