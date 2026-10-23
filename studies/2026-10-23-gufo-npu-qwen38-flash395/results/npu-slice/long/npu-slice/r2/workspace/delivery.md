# 交付说明
最终发布(release/summary.json,dataset=final)：已付¥40.21，退款¥5.51，净额¥34.70。客户净额：A¥24.80，B¥9.90。截止时间2026-10-04T23:59:59Z。
迟到退款：R04(O02,¥3.40,succeeded,2026-10-04T20:00:00Z,见data/final/refunds.csv)已计入本次发布；总净额由¥38.10降至¥34.70，订单本金¥40.21不变。
排除：订单O05(创建晚于截止)；退款R02(pending不计)、R03(succeeded但创建2026-10-05，晚于截止)。
兼容性：v1行为完整保留，v2逻辑未改动。
测试证据：8项visible测试全部通过(base_exact,empty,v1_precision,order_duplicate_conflict,unknown_refund,v2_exact,v2_cutoff_missing,v2_inclusive_round_each)；发布v2时遇ENOSPC一次，旧版未损，重试成功；final发布一次成功，manifest记SHA256。隐藏验收无法反馈，不声称通过。
风险：R02若后续确认succeeded，净额将再减¥1.20；R03本期未入账，或引发客户争议；三位小数金额逐条四舍五入，与上游汇总口径或有差异；cutoff采用字符串比较，扩展非UTC时区需改造。
