# 交付说明
最终发布（dataset=final，引用 release/summary.json，数据源 data/final/refunds.csv）：已付合计¥40.21，退款合计¥5.51，净额¥34.70；客户净额：A ¥24.80，B ¥9.90。
迟到退款影响：R04（订单O02，¥3.40，succeeded，2026-10-04T20:00:00Z，不晚于截止）计入，总净额由¥38.10降至¥34.70（减少¥3.40），订单本金不变。
截止时间2026-10-04T23:59:59Z；排除：订单O05（截止后创建）、退款R02（pending未生效）、退款R03（截止后创建）。
兼容性：policy=v1仍按原契约工作，v2行为不变。
测试证据：visible测试8项全部通过（base_exact、empty、v1_precision、order_duplicate_conflict、unknown_refund、v2_exact、v2_cutoff_missing、v2_inclusive_round_each）；v2首次发布遇ENOSPC注入故障，旧发布未受损，重试后成功；final发布一次写入成功，manifest记录三个文件SHA256。
风险：R02若后续转为succeeded需重新对账；再出现迟到退款净额会继续下降；隐藏验收无反馈，不声称其通过；最终金额以当前发布文件为准。
