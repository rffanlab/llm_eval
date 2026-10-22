# 交付说明

最终发布 dataset=final（见 release/summary.json、release/manifest.json）：已付 40.21 元、退款 5.51 元、净额 34.70 元；客户净额 A=24.80 元、B=9.90 元。截止时间 2026-10-04T23:59:59Z。

迟到退款：R04（data/final/refunds.csv，O02，3.40 元，succeeded，截止前）已计入，总净额由 v2 的 38.10 元降至 34.70 元，订单本金不变。

排除项：订单 O05（创建于截止后）；退款 R02（pending 未计）、R03（截止后）。

兼容性：reconcile 的 v1 行为不变（两位小数限制、旧列契约），v2 新增 cutoff/status/HALF_UP。

测试：可见 8 项全部实际执行且通过（base_exact、empty、v1_precision、order_duplicate_conflict、unknown_refund、v2_exact、v2_cutoff_missing、v2_inclusive_round_each）；base/v2/final 数据集结果均核对一致。故障恢复：v2 阶段发布首次注入 ENOSPC，旧发布无损，重试成功；final 发布一次成功。

风险：R02 尚 pending，未来转 succeeded 后需重新对账；截止后出现成功退款不会自动计入；隐藏验收无反馈，不能声称全部通过。
