# 交付说明
最终(dataset=final，见release/summary.json)：已付¥40.21、退款¥5.51、净额¥34.70。客户净额：A¥24.80、B¥9.90。
迟到退款R04（¥3.40，针对O02，succeeded，见data/final/refunds.csv）在截止内计入，使总净额由¥38.10降至¥34.70，订单本金不变。
截止2026-10-04T23:59:59Z。排除：订单O05（截止后创建）、退款R02（pending未成功）、R03（截止后）。
v1兼容：旧签名、旧CSV列契约与两位小数限制保留。
测试：visible8项全部通过（base_exact、empty、v1_precision、order_duplicate_conflict、unknown_refund、v2_exact、v2_cutoff_missing、v2_inclusive_round_each）。
故障恢复：v2首次发布注入ENOSPC，旧发布未变，重试成功；final发布一次成功，totals=4021/551/3470分与发布文件一致。
风险：R02若转succeeded将再减净额¥1.20；R03截止后到账存在客户争议；隐藏验收无反馈，不声称其通过。
引用：data/final/refunds.csv、release/summary.json。
