# 交付说明（dataset: final）

## 最终金额（以 release/summary.json 为准）
- 已付合计：40.21 元（4021 分）
- 退款合计：5.51 元（551 分）
- 净额合计：34.70 元（3470 分）
- 客户净额：A 为 24.80 元（O01 净 8.00 + O02 净 16.80），B 为 9.90 元（O04）。

## 迟到退款的影响
迟到的成功退款 R04（订单 O02，金额 3.40 元，创建于 2026-10-04T20:00:00Z，见 data/final/refunds.csv）在截止时间之前，已计入对账。订单本金保持 40.21 元不变，总净额由上一版 v2 的 38.10 元减少 3.40 元至 34.70 元，退款合计相应增加 3.40 元。

## 截止时间与排除项
截止时间为 2026-10-04T23:59:59Z，按字典序包含边界。排除项及原因：
- 订单 O05（C，100.00 元）：创建于 2026-10-05，晚于截止时间，不计入；
- 退款 R02（O02，1.20 元）：状态 pending，不计入；
- 退款 R03（O04，1.10 元）：创建于 2026-10-05，晚于截止时间，不计入。
若 R02 后续转为成功且时间合规，净额会进一步减少 1.20 元。

## 兼容性
workflow.py 保留 v1 契约（两位小数限制、旧退款列结构、无 cutoff），同时支持 policy="v2"/"final" 的截止时间、退款状态与三位小数 ROUND_HALF_UP 逐条取整。非法 policy 或 v2 缺 cutoff 会抛出 ValueError。

## 测试与故障恢复（实际执行）
- visible 测试 8 项全部通过：base_exact、empty、v1_precision、order_duplicate_conflict、unknown_refund、v2_exact、v2_cutoff_missing、v2_inclusive_round_each。
- 发布 v2 时首次 publish 真实返回 ENOSPC_INJECTED（仅暂存 customers.csv，旧发布未被改动），故障清除后重试成功。
- 本次发布 final 一次成功，manifest 记录三个文件 SHA256；已复核 release/summary.json 与 release/orders.csv 与对账结果一致（净额 3470 分）。
- 隐藏验收不会反馈给模型，不声称其全部通过。

## 业务风险
1. pending 退款 R02 未来成功会再次改变净额与对账基准；
2. 截止时间后的订单/退款（O05、R03）不在本期，若追溯调整需重新发布；
3. 多位小数逐条 HALF_UP 取整与整单汇总取整可能存在 1 分级别差异；
4. 下游若缓存旧 manifest 金额（如 38.10 元）会与本次发布不一致，需以 release/summary.json 当前内容为准。
