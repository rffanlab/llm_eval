# 交付说明

最终发布(dataset=final，总额以release/summary.json为准)：已付40.21元、退款5.51元、净额34.70元；客户净额A=24.80元、B=9.90元。截止时间2026-10-04T23:59:59Z。

迟到退款：R04(O02，3.40元，succeeded，2026-10-04T20:00:00Z，见data/final/refunds.csv)在截止前，计入后总净额由38.10元降为34.70元(减少3.40元)，订单本金不变。

排除项：订单O05创建于截止后被排除；退款R02为pending、R03创建于截止后，均不计入，也不报错。

兼容与测试：reconcile保留v1行为(两位小数限制、旧列契约)，签名不变。visible测试8项全部实际运行通过(base_exact、empty、v1_precision、order_duplicate_conflict、unknown_refund、v2_exact、v2_cutoff_missing、v2_inclusive_round_each)。v2首次发布遇ENOSPC注入故障，工具确认旧发布未损，故障解除后重试成功；final发布一次成功，manifest记录三文件SHA256。隐藏验收不反馈给模型，不声称其通过。

风险：R02若后续succeeded，净额将再减1.20元；R03属截止后成功退款，若业务要求追溯会与截止口径不一致；多位小数按ROUND_HALF_UP逐条取整，与合作方汇总口径可能差1分；cutoff为严格UTC字符串比较，格式不符会拒绝。
