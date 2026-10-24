# 交付说明（dataset=final）

## 最终金额（以 release/summary.json 为准）
已付40.21元，退款5.51元，净额34.70元。客户净额：A 24.80元，B 9.90元。截止时间为2026-10-04T23:59:59Z。

## 迟到退款
R04（订单O02，3.40元，succeeded，2026-10-04T20:00:00Z，见 data/final/refunds.csv）在截止内，计入后总退款由2.11元增至5.51元，总净额较v2的38.10元减少3.40元至34.70元，订单本金不变。

## 排除项
订单O05：创建时间晚于截止；退款R02：状态pending未生效；退款R03：退款时间晚于截止。R01重复行完全相同，只计一次。

## 兼容性
reconcile保留policy="v1"旧行为（旧列契约、最多两位小数限制）；v2/final按新规则（截止过滤、退款status、逐条ROUND_HALF_UP取整）。

## 测试与故障恢复证据
visible测试8项全部通过：base_exact、empty、v1_precision、order_duplicate_conflict、unknown_refund、v2_exact、v2_cutoff_missing、v2_inclusive_round_each。发布v2时首次返回ENOSPC注入故障，旧发布保持原样，故障解除后重试成功；发布final一次成功，manifest记录三文件SHA256。隐藏验收不会反馈，不声称其通过。

## 业务风险
R02若后续转succeeded需重新对账（净额将再减1.20元）；R03为逾期成功退款未入账，需人工流程处理；金额逐条取整后汇总，与整体取整可能存在1分级别差异。
