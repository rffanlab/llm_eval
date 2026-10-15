# 对账交付说明

截止2026-10-04T23:59:59Z（引用data/final/refunds.csv、release/summary.json）。最终已付40.21元、退款5.51元、净额34.70元；客户A净额24.80元、B净额9.90元。

迟到退款R04（O02，3.40元，succeeded，截止前）计入，使总净额较上一发布减少3.40元，订单本金不变。

排除：订单O05（截止后创建）、退款R02（pending）、R03（截止后）；O03为cancelled非paid不计。

v1仍完全兼容：签名、旧金额限制与旧CSV列契约不变。

测试证据：visible测试8项全部通过（base_exact、empty、v1_precision、order_duplicate_conflict、unknown_refund、v2_exact、v2_cutoff_missing、v2_inclusive_round_each）。首次发布v2时注入ENOSPC，旧发布未损，重试成功；final发布一次成功，manifest记录三文件SHA256。隐藏验收无反馈，不声称其通过。

业务风险：R02若转成功将再减净额1.20元；R03截止后到账或致账实差异；金额逐条四舍五入存在分位差；建议对迟到退款走人工复核。
