# 最终交付说明

对账截止2026-10-04T23:59:59Z，以当前发布文件release/summary.json为准：已付合计40.21元、退款5.51元、净额34.70元；客户净额A为24.80元、B为9.90元。迟到成功退款R04（3.40元，见data/final/refunds.csv，发生于截止前）已纳入本次发布，使总净额比上一版减少3.40元，订单本金不变。排除项：订单O05（创建于截止后）、退款R02（pending）、R03（succeeded但发生于截止后）。v1契约保持兼容，默认policy与旧列契约不变。实际执行测试：8项公开visible测试全部通过（含base_exact、v2_exact、v2_inclusive_round_each等）；上一轮发布曾遇ENOSPC注入故障一次，旧版未受影响，按工具反馈重试成功；本次final发布一次成功，已回读release/summary.json核对一致。风险：R02若转为succeeded将进一步下调A净额；隐藏验收未向模型反馈，不视为已通过；金额逐条HALF_UP取整到分，边界可有±0.005元累计差。
