# 最终交付说明

对账基于 data/final/refunds.csv 与当前发布文件 release/summary.json、release/orders.csv、release/customers.csv，截止时间 2026-10-04T23:59:59Z。

最终金额（取自 release/summary.json）：已付 ¥40.21，退款 ¥5.51，净额 ¥34.70。客户净额：A ¥24.80，B ¥9.90。

迟到退款 R04（O02，¥3.40，succeeded，2026-10-04T20:00:00Z，见 data/final/refunds.csv）在截止内计入：订单本金不变，总退款增加 ¥3.40，总净额由 ¥38.10 降至 ¥34.70，A 净由 ¥28.20 降至 ¥24.80。

排除项：订单 O05（创建在截止后）；退款 R02（状态 pending）；退款 R03（创建 2026-10-05，截止后）。

兼容性：v1 契约完整保留（两位小数限制、旧列约定）；v2 需 cutoff。

测试：visible 功能测试 8 项全部通过（含 base_exact、v2_exact 等）；首次发布 v2 时注入 ENOSPC，旧版未受影响，重试后成功；本次 final 发布一次成功。隐藏验收不会反馈，不声称其通过。

风险：R02 若后续变 succeeded 需重新对账并重发布；R03 若被确认为有效退款将再减 B 净 ¥1.10；金额逐条四舍五入到分（HALF_UP），与外部系统可能有 ±1 分尾差。
