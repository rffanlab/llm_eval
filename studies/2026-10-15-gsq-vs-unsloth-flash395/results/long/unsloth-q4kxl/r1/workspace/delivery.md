# 交付说明

最终发布（dataset=final，源 data/final/refunds.csv，结果见 release/summary.json）：已付40.21元、退款5.51元、净额34.70元；客户净额 A=24.80元、B=9.90元。截止时间 2026-10-04T23:59:59Z。

迟到退款 R04（O02，3.40元，截止前succeeded）已计入，总净额由38.10降为34.70，订单本金不变。排除项：订单O05（截止后创建）、退款R02（pending未入账）、退款R03（截止后创建）。v1契约保持兼容。

测试证据：visible测试8项全部通过（base_exact、empty、v1_precision、order_duplicate_conflict、unknown_refund、v2_exact、v2_cutoff_missing、v2_inclusive_round_each）；首次发布v2时遇宿主注入ENOSPC故障，旧版发布未受损，重试后成功；final数据集发布一次成功并核对manifest。

业务风险：R02若后续转为succeeded，净额将再减少1.20元；R03在截止后成功、不入本期账，可能与上游系统产生差异；隐藏验收不向本侧反馈，无法声称其通过，仅能确认上述visible测试与实际发布文件一致。
