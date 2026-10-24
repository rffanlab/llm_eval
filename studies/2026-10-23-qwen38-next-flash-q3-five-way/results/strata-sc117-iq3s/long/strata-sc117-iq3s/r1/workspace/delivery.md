# 交付说明

最终对账（截止 2026-10-04T23:59:59Z，输入 data/final/refunds.csv，已发布，汇总见 release/summary.json）：已付 40.21 元、退款 5.51 元、净额 34.70 元。客户净额：A 24.80 元，B 9.90 元。

迟到退款 R04（O02，3.40 元，succeeded，2026-10-04T20:00:00Z，在截止内）已计入：总净额较 v2 的 38.10 元减少 3.40 元至 34.70 元，订单本金不变。

排除项：订单 O05（2026-10-05 创建，晚于截止）；退款 R02（状态 pending，未计）；退款 R03（2026-10-05 创建，晚于截止）。

兼容性：v1 契约与旧列格式保留；v2 的 cutoff、退款状态与多位小数 ROUND_HALF_UP 逐条取整行为不变。

测试证据：8 项 visible 测试全部通过（base_exact、empty、v1_precision、order_duplicate_conflict、unknown_refund、v2_exact、v2_cutoff_missing、v2_inclusive_round_each）。发布 v2 时首次尝试出现 ENOSPC 暂时故障，旧发布未被改动，重试后发布成功；本次发布 final 一次成功，已核对 manifest 与 release 文件。隐藏验收无反馈，不声称隐藏测试全部通过。

业务风险：R02 的 1.20 元 pending 退款若后续成功，净额将再降 1.20 元；截止后发生的 R03 类退款按规则不计，需与财务确认补记口径；金额逐条 HALF_UP 取整，累计舍入差异可达数分。
