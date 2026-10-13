# v1契约
reconcile(orders_csv, refunds_csv, policy="v1", cutoff=None)返回对象：
{"orders":[{"order_id":str,"customer":str,"paid_cents":int,"refund_cents":int,"net_cents":int}],"customers":[{"customer":str,"net_cents":int}],"totals":{"paid_cents":int,"refund_cents":int,"net_cents":int}}
orders按order_id字典序，customers按customer字典序。只包含paid订单，cancelled订单不入结果。金额非负，v1最多两位小数，拒绝NaN/Infinity/负数/超过两位小数；使用十进制定点，不使用float乘100。
order_id和refund_id用于去重：相同id完全相同行只算一次；相同id但任何字段不同必须ValueError。未知订单退款、cancelled订单退款或单笔订单累计退款超过已付必须ValueError。退款均有效；零金额允许。所有输出整数分，paid-refund=net。只对paid订单所属客户出汇总，包括净额为零的客户。
空CSV有表头时返回空列表及三个零。不能修改输入内容。
