# 最终交付说明

对账基于 data/final 输入，截止 2026-10-04T23:59:59Z，已发布 dataset=final（见 release/summary.json）：已付 $40.21、退款 $5.51、净 $34.70；客户净额 A=$24.80、B=$9.90。

迟到退款 R04（data/final/refunds.csv，O02，$3.40，succeeded，2026-10-04T20:00:00Z≤截止）已计入，总净额较上一版减少 $3.40，订单本金不变。

排除项：订单 O05（创建晚于截止）、退款 R02（pending 未生效）、R03（成功但创建晚于截止）。v1 契约保持兼容，旧行为经测试验证。

已执行 visible 测试 8 项：base_exact、empty、v1_precision、order_duplicate_conflict、unknown_refund、v2_exact、v2_cutoff_missing、v2_inclusive_round_each，全部通过；首次 v2 发布注入 ENOSPC，旧版未改动，故障解除后重试成功，manifest 与 SHA256 已核对。

风险：R02 仍 pending，未来成功将再降净额；R03 截止后成功不追溯，如需调整须人工处理；三位小数 HALF_UP 逐条取整，行与汇总可现 1 分舍入差；隐藏验收不反馈给本侧，不声称其全部通过。
