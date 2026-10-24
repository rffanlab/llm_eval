# v2变更
签名不变；policy="v2"时，cutoff必填，格式YYYY-MM-DDTHH:MM:SSZ。订单增加/保留created_at；退款有status(succeeded或pending)、created_at。
只计created_at<=cutoff的paid订单，只计created_at<=cutoff且succeeded的退款。pending、截止后退款、截止后订单均不计；退款对应订单存在但因截止时间排除时也忽略。真正不存在或cancelled订单的有效退款仍ValueError。
订单/退款金额允许多位小数，Decimal ROUND_HALF_UP到整数分，先逐条取整再汇总。包含pending/截止后行的重复id冲突仍必须拒绝。所有日期均规范UTC字符串，比较字典序即可。
v1仍保留旧金额限制和旧CSV列契约。输出结构与顺序保持v1；非法policy或v2无cutoff必须ValueError。
