# 交付说明
最终对账以data/final/refunds.csv为输入，金额以release/summary.json为准：已付¥40.21，退款¥5.51，净额¥34.70。客户净额：A ¥24.80，B ¥9.90。
迟到退款R04（¥3.40，succeeded，2026-10-04T20:00:00Z，截止前）计入O02，使总净额较v2发布减少¥3.40（38.10→34.70），订单本金不变（40.21）。截止时间为2026-10-04T23:59:59Z。排除项：订单O05（创建于截止后）、退款R02（状态pending未成功）、退款R03（创建于截止后），均不计入。
兼容性：reconcile保留policy="v1"全部旧行为（两位小数、旧列契约），v2为新增，未破坏。
测试证据：visible测试8项全部通过（base_exact、empty、v1_precision、order_duplicate_conflict、unknown_refund、v2_exact、v2_cutoff_missing、v2_inclusive_round_each）；final对账与发布汇总一致。发布v2时首次出现ENOSPC磁盘故障，旧发布未被删改，故障清除后重试成功；final一次发布成功，manifest含三文件SHA256。未执行独立隐藏验收，不断言其结果。
业务风险：R02若后续转成功将再减净额¥1.20；R03截止后到账属跨期，需下期处理；金额逐条HALF_UP取整，多条舍入可累积分差；对账以截止时间为界，迟到数据需人工确认补录。
