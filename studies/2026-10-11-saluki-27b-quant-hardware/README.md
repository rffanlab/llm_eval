# Saluki 27B：量化与硬件对照

状态：题面、验收和顺序已冻结；RTX3090的Saluki首组48条记录已闭合，其他部署正在准备或执行。全部获准部署完成前不发布总体推荐。

- [协议](protocol.md)：三步结构、四组权重、RTX3090与Ryzen AI Max+395、全层GPU限制与停止条件。
- [完整题面与确定答案](tasks.json)：12类/每部署18主会话；答案不会传给被测模型。
- [原十类题目的工具、提示词与独立验收](tasks-and-reproduction.md)。新增R01/R02的完整题面及字段验收见tasks.json；R02由独立全空间枚举确定唯一最优。
- [模型身份](models.json)、[统一聊天模板来源](chat-template-source.json)、[冻结哈希](freeze.json)。
- [单次执行入口](run_case.py)：只通过环境变量设置LOCAL_BASE_URL、LOCAL_MODEL、LOCAL_API_KEY，私有连接信息不入库。
- [首组独立摘要](first-profile-summary.json)：只描述RTX3090的Saluki，未把待测部署计为零。
- [可用性与差距门槛](acceptance-gate.json)：原数值门槛及同任务等待比的计算定义。
- [运行控制与资源上限](runtime_control.py)、[控制脚本版本记录](runtime-controller.json)：逐个加载、准入和395运行期间24GiB监测。

请求、流式延迟、原生timings、token和首次失败将在结果目录逐次保存。过度思考、固定512输出与不同输入长度单列，不并入主交付得分。

另有两份明确标为事后诊断的注册：关闭思考复查C01/W01/W02/W03，以及按推荐采样参数复查C03/W02。均在诊断调用前登记，并对全部获准部署一致执行；不替换温度0的初测成绩。R02唯一最优答案可用reference_reasoning.py全空间枚举复核。
