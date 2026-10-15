# 交付说明（final）

最终金额（来源：release/summary.json、data/final/refunds.csv）：已付¥40.21、退款¥5.51、净额¥34.70。客户净额：A¥24.80、B¥9.90。

迟到成功退款R04（¥3.40，O02，2026-10-04T20:00:00Z≤截止）已入账，使总净额较此前发布减少¥3.40至¥34.70，订单本金不变。

截止时间2026-10-04T23:59:59Z。排除：订单O05（创建于截止后）、退款R02（状态pending）、R03（截止后发生）。

v1契约保持兼容，导出与发布格式不变。

测试证据：visible测试8项全部通过（base_exact、empty、v1_precision、order_duplicate_conflict、unknown_refund、v2_exact、v2_cutoff_missing、v2_inclusive_round_each）；reconcile(final)与发布manifest一致；首次publish(v2)遇ENOSPC注入、旧版未变，重试成功，publish(final)返回published:true。

业务风险：R02仍pending，若转为成功需重新对账发布；R04使A客户净额降至¥24.80，需同步客服与财务；隐藏独立验收未反馈，不声称其通过。
