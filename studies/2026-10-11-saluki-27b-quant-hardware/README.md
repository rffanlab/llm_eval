# Saluki 27B：量化与硬件对照

状态：题面、验收和顺序已冻结，尚未开始正式模型调用。结果待实测，不能由文件大小或上游宣传推定。

- [协议](protocol.md)：三步结构、四组权重、RTX3090与Ryzen AI Max+395、全层GPU限制与停止条件。
- [完整题面与确定答案](tasks.json)：12类/每部署18主会话；答案不会传给被测模型。
- [原十类题目的工具、提示词与独立验收](tasks-and-reproduction.md)。新增R01/R02的完整题面及字段验收见tasks.json；R02由独立全空间枚举确定唯一最优。
- [模型身份](models.json)、[统一聊天模板来源](chat-template-source.json)、[冻结哈希](freeze.json)。
- [单次执行入口](run_case.py)：只通过环境变量设置LOCAL_BASE_URL、LOCAL_MODEL、LOCAL_API_KEY，私有连接信息不入库。

请求、流式延迟、原生timings、token和首次失败将在结果目录逐次保存。过度思考、固定512输出与不同输入长度单列，不并入主交付得分。
