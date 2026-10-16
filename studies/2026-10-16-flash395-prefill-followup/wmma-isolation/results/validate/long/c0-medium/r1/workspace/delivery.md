# 最终交付说明（dataset=final）

最终金额（读自 release/summary.json，源数据 data/final/refunds.csv）：已付40.21元、退款5.51元、净额34.70元；客户净额 A=24.80元、B=9.90元。

迟到退款影响：R04（O02，3.40元，succeeded，2026-10-04T20:00:00Z）不晚于截止时间2026-10-04T23:59:59Z，已计入；总净额较v2的38.10元减少3.40元至34.70元，订单本金不变。

排除项：订单O05（截止后创建）、退款R02（状态pending）、退款R03（截止后退款）均不计入。

兼容性：policy=v1 的旧列契约与金额校验保持可用，v2 行为不变。

测试证据：visible测试8/8通过（base_exact、empty、v1_precision、order_duplicate_conflict、unknown_refund、v2_exact、v2_cutoff_missing、v2_inclusive_round_each）；实跑final对账得 paid=4021、refund=551、net=3470（分）；发布dataset=final成功，release/manifest.json 与发布文件一致。此前发布v2时首次注入ENOSPC，旧版本未受影响，重试成功。隐藏验收未反馈，不声称其通过。

业务风险：R02若转succeeded，净额将再减1.20元；R03截止后退未入账，或需争议处理；金额逐条ROUND_HALF_UP取整（10.105→10.11、2.105→2.11），存在分级舍入差；截止时间按UTC字符串比较，上游须保证格式规范。
