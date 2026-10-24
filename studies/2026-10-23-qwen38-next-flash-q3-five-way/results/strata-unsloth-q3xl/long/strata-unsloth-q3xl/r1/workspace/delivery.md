# 最终交付说明

对账发布已完成，现发布dataset=final，金额以release/summary.json为准：已付¥40.21、退款¥5.51、净额¥34.70。客户净额：A为¥24.80，B为¥9.90。

迟到退款：data/final/refunds.csv中的R04（O02，¥3.40，succeeded，2026-10-04T20:00:00Z）不晚于截止2026-10-04T23:59:59Z，已计入，使总净额减少¥3.40，订单本金不变。

排除项：订单O05创建于2026-10-05，晚于截止；退款R02为pending；退款R03虽succeeded但创建于2026-10-05，晚于截止。

兼容性：v1行为与旧列契约保持不变；v2需cutoff；非法policy或缺cutoff抛ValueError。

测试证据：visible测试8项全部通过（base_exact、empty、v1_precision、order_duplicate_conflict、unknown_refund、v2_exact、v2_cutoff_missing、v2_inclusive_round_each）。发布v2时曾发生一次ENOSPC注入故障，旧发布未改动，重试成功；发布final一次成功，manifest含三文件SHA256。独立隐藏验收无反馈，不声称其通过。

业务风险：R02若后续succeeded，净额将再降¥1.20；R03因截止未计，若业务要求追溯，B净额将降¥1.10；O05（¥100.00）属下期款项；逐条四舍五入与整体汇总存在分位舍入差；请以release/summary.json为准。
