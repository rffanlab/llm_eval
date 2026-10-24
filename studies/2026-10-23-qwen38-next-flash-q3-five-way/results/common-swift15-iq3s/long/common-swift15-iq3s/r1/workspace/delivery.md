# 交付说明
最终发布（dataset=final，见 release/summary.json）：已付40.21元，退款5.51元，净34.70元；客户净额A=24.80元，B=9.90元。
迟到退款：R04（data/final/refunds.csv，3.40元，succeeded，2026-10-04T20:00:00Z≤cutoff）计入，作用于O02，使总净额由38.10元降至34.70元，订单本金40.21元不变。
截止时间2026-10-04T23:59:59Z。排除：订单O05（100.00元，2026-10-05截止后）；退款R02（状态pending）；R03（2026-10-05截止后）。
v1仍兼容：默认policy=v1，保留旧金额两位小数限制与旧CSV列契约。
测试：visible测试8/8通过（base_exact、empty、v1_precision、order_duplicate_conflict、unknown_refund、v2_exact、v2_cutoff_missing、v2_inclusive_round_each）；reconcile(dataset=final)结果与发布一致。发布v2时遇ENOSPC注入一次，旧版未变，重试成功并核对manifest。
风险：R02为pending，若后续成功，净额将再减1.20元；R03在截止后未计，如业务追溯需改policy重发；O05的100.00元本期不计，客户C无结算；金额逐条HALF_UP取整到分，与整单汇总存在分位差。
隐藏验收无反馈，不声称其通过。
