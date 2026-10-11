# Saluki 27B：量化与硬件对照

状态：2026年10月11日至12日实测完成。四份量化×两套硬件，各48条记录，共384条；144个主测会话和56份写作审读全部闭合。实际GPU分配均低于24GiB，全部层在GPU；只使用单张RTX3090或内置Radeon8060S。

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

请求、流式延迟、原生timings、token和首次失败已逐次保存。过度思考、固定512输出与不同输入长度单列，不并入主交付得分。

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

CSV保存每条记录的原始接受状态、编辑分、完整等待、prefill/decode、token、缓存和错误；Markdown按同题呈现四种量化与两套硬件。重复主测的时间、token均取每轮中位；原始逐轮数值仍在CSV中。简单思考题的开关各重复两次，分别取中位。首正文来自流式计时，非流式请求没有测量时保持未知。

## 完成结果

- [原始摘要](summary.json)、[16组同题比较](comparisons.json)。
- [W02段落兼容逐记录解释](paragraph-compatibility.json)、[补算摘要](compatibility-summary.json)：只改变3090 GSQ与Q5的主测W02接受状态；原始答卷与分数不变。
- [同题及补充测量表](measurements/measurement-tables.md)、[384条测量CSV](measurements/measurement-records.csv)。
- [写作审读](editor-reviews.json)：AI代理主审，非人类盲评；全部56份按原始答卷哈希绑定。

| 量化 | RTX3090原始 / 分段兼容 | AI Max+395原始 / 分段兼容 |
| --- | --- | --- |
| Saluki | 10/18 / 10/18 | 9/18 / 9/18 |
| GSQ | 11/18 / 12/18 | 9/18 / 9/18 |
| Q4 | 12/18 / 12/18 | 9/18 / 9/18 |
| Q5 | 12/18 / 13/18 | 9/18 / 9/18 |

16组比较均未满足事前完成率、基础任务和等待差距的全部门槛。复杂调度、整数优化、决策备忘录的主测没有合格交付。只按已经完成的工作推荐：RTX3090兼顾基础代码与写作优先Q5；AI Max+395的筛选、工具流程、台账查证与基础概率优先GSQ。推荐只适用于本期具体权重、引擎、预算和题目。

超时usage未知，不补零，已知token小计不能当总成本。约每秒资源采样验证单模型与24GiB上限；实际最长输入约2万token。加载页缓存未控制。关闭思考及推荐采样补测单列，不替换正式成绩。
