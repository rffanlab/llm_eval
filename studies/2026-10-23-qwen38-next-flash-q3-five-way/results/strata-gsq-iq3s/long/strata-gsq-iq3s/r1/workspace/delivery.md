# 交付说明
最终发布（release/summary.json）：已付¥40.21、退款¥5.51、净额¥34.70；客户净额A¥24.80、B¥9.90。
迟到退款R04¥3.40（data/final/refunds.csv，succeeded，2026-10-04T20:00:00Z≤截止2026-10-04T23:59:59Z）计入O02，总净额由38.10降至34.70，订单本金不变。
排除：订单O05（创建于截止后）、退款R02（pending）、R03（创建于截止后）。
v1契约仍兼容，签名与输出结构未变。
测试：共8个可见测试通过(base_exact,empty,v1_precision,order_duplicate_conflict,unknown_refund,v2_exact,v2_cutoff_missing,v2_inclusive_round_each)；v2发布时ENOSPC一次，旧版未改动，重试成功；final发布一次成功，金额按release/summary.json核对。
风险：R02的pending退款日后可能succeeded并增加退款；R03为成功退款但因截止后未入账，或引发客户争议；金额逐条四舍五入再汇总，可能有1分级别舍入差。
隐藏验收测试未执行，不声称其通过。
