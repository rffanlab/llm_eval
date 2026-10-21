# 交付说明

最终发布(dataset=final，release/summary.json)：已付¥40.21、退款¥5.51、净额¥34.70；客户净额A¥24.80、B¥9.90。截止时间2026-10-04T23:59:59Z。

迟到退款：data/final/refunds.csv中R04(O02，¥3.40，succeeded，2026-10-04T20:00:00Z≤截止)已计入，总净额由38.10降至34.70，即减少¥3.40，订单本金不变。

排除项：O05(订单在截止后)、R02(pending状态)、R03(退款在截止后)。v1契约仍兼容，visible测试8/8通过(含v1/v2用例)。v2首次发布遇ENOSPC暂时故障，旧版未改动，重试成功；final发布一次成功，已按release/summary.json与manifest.json核对。

风险：R02仍为pending，若后续成功净额需再对账；迟到数据可能再次改变结果；三位小数金额逐条ROUND_HALF_UP取整，与整体取整可能有±1分差；隐藏验收未由我执行，不声称其结果。
