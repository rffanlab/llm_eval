# Saluki 27B：量化与硬件对照

状态：题面、验收和顺序已冻结；RTX3090的Saluki、GSQ与Q4各48条记录已闭合，Q5正在执行；AI Max+395的部署尚未开始。全部获准部署完成前不发布总体推荐。

- [协议](protocol.md)：三步结构、四组权重、RTX3090与Ryzen AI Max+395、全层GPU限制与停止条件。
- [完整题面与确定答案](tasks.json)：12类/每部署18主会话；答案不会传给被测模型。
- [完整12类题目的提示词、工具参数与复跑说明](tasks-and-reproduction.md)。确定答案及字段验收见tasks.json；R02由独立全空间枚举确定唯一最优。
- [模型身份](models.json)、[统一聊天模板来源](chat-template-source.json)、[冻结哈希](freeze.json)。
- [单次执行入口](run_case.py)：只通过环境变量设置LOCAL_BASE_URL、LOCAL_MODEL、LOCAL_API_KEY，私有连接信息不入库。
- [首组独立摘要](first-profile-summary.json)：只描述RTX3090的Saluki，未把待测部署计为零。
- [可用性与差距门槛](acceptance-gate.json)：原数值门槛及同任务等待比的计算定义。
- [运行控制与资源上限](runtime_control.py)、[控制脚本版本记录](runtime-controller.json)：逐个加载、准入和395运行期间24GiB监测。
- [原生计时定义](native-timing-definition.json)：解码吞吐沿用引擎的decode步数定义，Agent多轮按解码时间加权。
- [W02换行兼容解释登记](paragraph-compatibility-registration.json)：事后离线补算，原始答卷与评分保持不变。原始和补算接受状态分别报告。

请求、流式延迟、原生timings、token和首次失败将在结果目录逐次保存。过度思考、固定512输出与不同输入长度单列，不并入主交付得分。

另有两份明确标为事后诊断的注册：关闭思考复查C01/W01/W02/W03，以及按推荐采样参数复查C03/W02。均在诊断调用前登记，并对全部获准部署一致执行；不替换温度0的初测成绩。R02唯一最优答案可用reference_reasoning.py全空间枚举复核。

## 离线汇总与测量表

以下命令在本目录运行；它们只读取记录，不调用模型。正式汇总必须等全部部署闭合，写作审读完成；资源超限的部署单列为跳过，未测成绩不填零。

```sh
python build_summary.py --output summary.json
python build_comparisons.py --summary summary.json --output comparisons.json
python paragraph_compatibility.py --output paragraph-compatibility.json
python build_compatibility_summary.py --summary summary.json --compatibility paragraph-compatibility.json --output compatibility-summary.json
python build_measurement_tables.py --summary summary.json --compatibility compatibility-summary.json --output-dir measurements
```

CSV保存每条记录的原始接受状态、编辑分、完整等待、prefill/decode、token、缓存和错误；Markdown按同题呈现四种量化与两套硬件。重复主测的时间、token取各轮中位；原始逐轮数值仍在CSV中。简单思考题的开关各重复两次，分别取中位。首正文来自流式计时，非流式请求没有测量时保持未知。
