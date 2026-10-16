# 交付说明（dataset=final）

**最终金额**（依据 release/summary.json 实读核对）：已付 ¥40.21，退款 ¥5.51，净额 ¥34.70。客户净额：A ¥24.80，B ¥9.90。

**迟到退款**：R04（O02，¥3.40，succeeded，2026-10-04T20:00:00Z，见 data/final/refunds.csv）在截止前，已计入；总净额较 v2 发布 ¥38.10 减少 ¥3.40 至 ¥34.70，订单本金不变。

**截止时间** 2026-10-04T23:59:59Z。排除：订单 O05（截止后创建）、退款 R02（pending 状态）、退款 R03（截止后创建）。

**兼容性**：reconcile 保留 policy="v1" 全部旧行为（两位小数限制、旧列契约），v2/final 用 cutoff 与退款状态。

**测试证据**：visible 测试 8/8 通过（base_exact、empty、v1_precision、order_duplicate_conflict、unknown_refund、v2_exact、v2_cutoff_missing、v2_inclusive_round_each）。发布 v2 时首次调用返回 ENOSPC_INJECTED 故障，旧版未被破坏，故障清除后重试成功；final 发布一次成功，manifest 记录三文件 SHA256。隐藏验收未反馈，未声称其通过。

**业务风险**：R02 若后续变 succeeded 需重算并补发；R03 超截止未计，客户 B 或主张权益；O05 的 ¥100.00 在本期外；三位小数按 HALF_UP 逐条取整，与合计后取整可能差 1 分。
