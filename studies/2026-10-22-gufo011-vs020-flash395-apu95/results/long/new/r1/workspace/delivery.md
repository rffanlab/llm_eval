# 交付说明

最终发布以 release/summary.json 为准：已付 40.21 元、退款 5.51 元、净额 34.70 元；客户净额 A=24.80 元、B=9.90 元。截止时间 2026-10-04T23:59:59Z。

迟到退款 R04（订单 O02，3.40 元，succeeded，早于截止，见 data/final/refunds.csv）已计入，使总净额减少 3.40 元，订单本金不变。

排除项：订单 O05 创建晚于截止；退款 R02 为 pending、R03 晚于截止，均不计入。

兼容性：v1 契约完整保留（两位小数限制与旧列契约），v2 行为不变。

测试：visible 测试 8/8 通过（base/empty/v1精度/重复冲突/未知退款/v2精确/缺cutoff/逐条四舍五入）；final 数据集 reconcile 与 publish 均一次成功。此前 v2 发布首次遭遇 ENOSPC 注入，旧发布未受损，重试成功且 manifest 已核对。

风险：R02 若后续 succeeded 将再减少净额，需下期对账处理；隐藏验收未向模型反馈，无法声称其通过；迟到退款持续出现意味着截止快照口径可能低估退款，建议约定迟到退款处理流程。引用：data/final/refunds.csv、release/summary.json。
