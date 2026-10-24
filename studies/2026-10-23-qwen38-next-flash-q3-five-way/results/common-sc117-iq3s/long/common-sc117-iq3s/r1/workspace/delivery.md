# 最终交付说明

对账依据 data/final/refunds.csv，最终金额以 release/summary.json 核对：已付40.21元、退款5.51元、净额34.70元（4021/551/3470分）。客户净额：A为24.80元，B为9.90元。

迟到退款R04（O02，3.40元，succeeded，2026-10-04T20:00:00Z不晚于截止）已计入，使总净额较v2发布时的38.10元减少3.40元至34.70元，订单本金不变。截止时间2026-10-04T23:59:59Z。排除项：订单O05（created_at晚于截止）、退款R02（状态pending）、退款R03（created_at晚于截止）。

兼容性：v1金额限制与旧列契约保持不变，base数据集对账结果不变。

测试与故障恢复：visible测试8项全部通过（base_exact、empty、v1_precision、order_duplicate_conflict、unknown_refund、v2_exact、v2_cutoff_missing、v2_inclusive_round_each）。v2首次发布注入ENOSPC，工具确认旧发布未改动，重试后成功；final发布一次成功，manifest中三个文件SHA256与发布返回一致。

风险：R02的1.20元pending退款若后续成功，总净额将再降1.20元；R03及R04类迟到退款可能再现，建议保留复核窗口；隐藏验收无反馈，不声称隐藏测试全部通过。
