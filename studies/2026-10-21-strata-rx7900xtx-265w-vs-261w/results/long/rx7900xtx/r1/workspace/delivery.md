# 最终交付说明

来源：data/final/refunds.csv；金额以当前发布 release/summary.json 为准。

最终汇总：已付40.21元、退款5.51元、净额34.70元；客户净额A为24.80元、B为9.90元。截止时间为2026-10-04T23:59:59Z。

迟到退款R04（订单O02，3.40元，succeeded，创建于截止前）已计入，使总净额减少3.40元至34.70元；订单本金40.21元不变。

排除项：订单O05（创建时间晚于截止）；退款R02（状态pending不计）；退款R03（succeeded但创建时间晚于截止）。

兼容性：policy=v1仍按旧金额与列契约工作，v2行为不变。

测试证据：8项visible测试全部实际运行通过（base_exact、empty、v1_precision、order_duplicate_conflict、unknown_refund、v2_exact、v2_cutoff_missing、v2_inclusive_round_each）。发布v2时首次publish遭遇注入的ENOSPC，旧发布未被删改，重试成功；本次发布final成功，manifest含三个文件SHA256。隐藏验收无反馈，不声称其通过。

业务风险：R02若后续转为succeeded，净额将再减1.20元；R03已出账但被截止排除，存在账实差异；多位小数金额逐条ROUND_HALF_UP取整，与整体舍入可能相差1分。
