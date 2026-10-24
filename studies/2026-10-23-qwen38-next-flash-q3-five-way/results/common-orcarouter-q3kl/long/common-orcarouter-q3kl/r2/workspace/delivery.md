# 最终交付（final）

对账与发布基于data/final/refunds.csv，金额以当前发布文件为准（release/summary.json及orders.csv、customers.csv，已对账核对）。

最终金额：已付40.21元、退款5.51元、净额34.70元。客户净额：A为24.80元、B为9.90元。

迟到退款R04（O02，3.40元，succeeded，2026-10-04T20:00:00Z，见data/final/refunds.csv）不晚于截止2026-10-04T23:59:59Z，已计入：总净额较v2发布减少3.40元（38.10元→34.70元），订单本金40.21元不变。

排除项：O05（2026-10-05T10:00:00Z晚于截止）；R02（pending未成功）；R03（succeeded但2026-10-05T10:00:00Z晚于截止）。

v1仍兼容：两位小数金额、无cutoff、旧列契约与全部v1行为保留。

测试证据：12项visible测试全部通过（base_exact、empty、v1_precision、order_duplicate_conflict、unknown_refund、v2_exact、v2_cutoff_missing、v2_inclusive_round_each等）；隐藏验收未反馈，不声称其通过。发布：首次publish(v2)注入ENOSPC故障，旧发布未受损，重试后成功；final一次发布成功，release/summary.json与对账一致。

业务风险：R04晚到仍计入本期，若财务按退款创建时间关账将产生3.40元跨期差异；R02若转pending将再减净额1.20元；O05的100元订单未入账，下期截止后净额将大幅上调；对账依赖cutoff字符串比较，时区或格式漂移会造成漏计。
