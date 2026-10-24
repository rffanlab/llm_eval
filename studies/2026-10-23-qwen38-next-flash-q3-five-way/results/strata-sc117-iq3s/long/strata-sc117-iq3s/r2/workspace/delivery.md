# 最终交付说明

截止 2026-10-04T23:59:59Z。以 release/summary.json 为准：已付 ¥40.21、退款 ¥5.51、净额 ¥34.70；客户净额 A=¥24.80、B=¥9.90。

迟到退款 R04（¥3.40，succeeded，2026-10-04T20:00:00Z，见 data/final/refunds.csv）在截止前，计入 O02，使总净额较上一版 ¥38.10 减少 ¥3.40 至 ¥34.70，订单本金不变。排除项：订单 O05（创建于截止后）、退款 R02（pending 未生效）、退款 R03（截止后到账）。

v1 契约保持兼容：默认 policy=v1，沿用旧列契约与两位小数限制。

测试证据：visible 测试 8 项全部通过（base_exact、empty、v1_precision、order_duplicate_conflict、unknown_refund、v2_exact、v2_cutoff_missing、v2_inclusive_round_each）。发布 v2 时首次遭遇 ENOSPC 注入，旧版发布未被改动，故障解除后重试成功；final 数据集一次发布成功，manifest 记录三文件 SHA256，与 release/ 下 orders.csv、customers.csv、summary.json 一致。

具体风险：R02 的 ¥1.20 若日后转为 succeeded，净额将再降 ¥1.20；亚分金额按每条 HALF_UP 取整（10.105→¥10.11、2.105→¥2.11），单笔可能有 1 分口径差；截止后到账退款（如 R03 的 ¥1.10）不入账，可能与支付平台流水存在差异。隐藏验收无反馈，不声称其通过。
