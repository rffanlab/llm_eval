# 交付说明

## 最终金额（以release/summary.json为准，已读取发布文件核对）
已付¥40.21、退款¥5.51、净额¥34.70；截止2026-10-04T23:59:59Z。

## 客户净额
A ¥24.80；B ¥9.90。

## 迟到退款
R04（见data/final/refunds.csv，O02，¥3.40，succeeded，2026-10-04T20:00:00Z≤截止）计入，总净额因此减少¥3.40，订单本金¥40.21不变。

## 排除项
O05（¥100.00，2026-10-05T10:00:00Z截止后创建）；R02（pending，¥1.20）；R03（¥1.10，2026-10-05T10:00:00Z截止后）。

## 测试与故障
实际执行visible测试8/8通过：base_exact、empty、v1_precision、order_duplicate_conflict、unknown_refund、v2_exact、v2_cutoff_missing、v2_inclusive_round_each；v1仍兼容（base对账通过）。publish(v2)首次返回ENOSPC_INJECTED，旧版未受损，重试成功；publish(final)一次成功。隐藏验收未执行，不声称其通过。

## 风险
R04使净额降¥3.40，退款率升至约13.7%；R02若转pending将再降净额；O05、R03被截止排除，账面低估；重复退款R04有双重退款风险。
