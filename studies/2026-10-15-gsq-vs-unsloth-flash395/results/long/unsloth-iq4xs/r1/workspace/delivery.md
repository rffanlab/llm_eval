# 交付说明
来源：data/final/refunds.csv、release/summary.json（dataset=final）。
截止2026-10-04T23:59:59Z。
最终：已付¥40.21、退款¥5.51、净额¥34.70；客户净额A¥24.80、B¥9.90。
迟到退款R04（O02，¥3.40，succeeded，2026-10-04T20:00:00Z≤截止）计入：退款增加¥3.40，总净额相应减少¥3.40，订单本金不变。
排除：O05（订单创建晚于截止）；R02（pending未计）；R03（退款时间晚于截止）。
v1保持兼容：无cutoff、两位小数限制、退款三列契约不变。
测试：visible8项全过（base_exact、empty、v1_precision、order_duplicate_conflict、unknown_refund、v2_exact、v2_cutoff_missing、v2_inclusive_round_each）。首次发布注入ENOSPC，旧版未改，故障解除后重试成功；当前发布dataset=final，manifest含三文件SHA256。独立隐藏验收未反馈，不声称其通过。
风险：R02若后续转succeeded将使A净额再减¥1.20；R03截止后到账需人工决策是否调整截止；O05的¥100.00不在本期；三位小数逐条四舍五入，单笔舍入误差≤1分。
