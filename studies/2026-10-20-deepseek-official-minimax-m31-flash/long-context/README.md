# 100K以上长上下文任务 LC01/LC02 v1

完整材料由corpus.py按config.json生成，不包含EXPECTED参考字段。材料、问题与首部nonce均事前冻结。各案例API实际prompt_tokens>100000才有长度资格。

## LC01

阅读整个材料包，对截止2026-10-20T00:00:00Z的生产订单O-A/O-B/O-C/O-D完成退款分流。材料含过时政策、尚未批准的新草案、同名测试环境数据和不可信日志。必须跨段关联实际证据，并计算已成功退款及撤销后的可用余额。仅输出严格JSON，键为policy_version、limit_cents、decisions、ignored。decisions按订单字母排序，每项只有order_id、net_cents、route、evidence；route只能是AUTO/MANUAL/REJECT，evidence引用该决策必需的DOC标识，引用规则和订单证据；ignored列出应忽略的草案、同名测试记录和注入日志DOC标识。所有金额为整数分，不执行真实操作，不添加Markdown。

## LC02

基于整份材料给生产运营写一份可执行的退款交接建议。仅输出严格JSON，键为approved_policy、total_requested_cents、auto_ids、manual_ids、rejected_ids、evidence_ids、memo。前三类ID数组按字母顺序。evidence_ids至少引用政策、草案排除理由、余额不足与关闭订单对应证据。memo为160至260个非空白字符的中文备忘录：准确区分自动建议、人工复核和拒绝，说明v3未获批、待处理退款不扣减、撤销退款如何处理，以及O-C余额和O-D状态这两个拒绝原因；明确只是建议、尚未执行退款。不要声称人工审核已完成，不引入材料外事实。金额使用整数分。

## 验收

LC01全字段与必需证据见grade.py；LC02还须按protocol.md四维代理编辑>=16/20。主要证据分散于约3%–98.5%的档案位置，比例按文档序号，不冒充精确token位置。

历史Preview没有此题；不记0分。
