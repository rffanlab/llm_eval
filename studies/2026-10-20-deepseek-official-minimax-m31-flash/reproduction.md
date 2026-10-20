# 单案例复跑与离线核对

本目录为冻结实验快照。Python 3.12使用标准库urllib调用API，代码验证使用受限独立worker。先在隔离目录、非生产环境检查工具、沙箱与预算，不执行模型生成代码到自己的真实仓库。`transport.py`从`EVAL_API_KEY`读凭据，不从结果文件取Key。使用者应遵守其API套餐和接口规则。

## 离线核对（不调用API）

在本研究目录运行`python aggregate.py`，生成`summary.json`及逐调用CSV。先按`freeze.json`的SHA256验证26项源未变；历史Preview目录应保持原样。编辑审读属于已记录的判断，聚合不重评文章。

## 单例入口

环境仅在进程中设置：`EVAL_API_KEY`、`EVAL_MODEL`、`EVAL_BASE_URL`。分别选择DeepSeek官方模型`deepseek-flash`或MiniMax官方模型`MiniMax-M3.1-Flash`；不可把另一个来源的结果混入当前目录。

在研究目录，每次只执行一个入口并审读，再决定是否执行下一项：

```text
python short_runner.py --provider deepseek --task C01 --round 1 --variant main --output <new-private-output>
python long-context/runner.py --provider deepseek --task LC01 --round 1 --output <new-private-output>
python long-horizon/runner.py --provider deepseek --profile deepseek --round 1 --output <new-private-output>
```

MiniMax将`--provider`/`--profile`改为`minimax`并更换对应环境变量。不要覆盖本次已存在的结果目录。`--variant depth`只用于冻结D01 low诊断；额外C03/LC01 low探索见其独立登记与源码。

## 已知限制

此快照长程runner在tool call被length截断时没有补配对tool返回，下一阶段可能被API拒绝。复现旧版本会复现这一限制。生产Agent应修复该状态恢复，但那将是新的协议/实验，不能修改本研究原始成绩。LC字面值过严的解释使用`semantic_annotations.py`单列，不回写原grade。

代理材料未随当前官方分数公开；不需要搭建反代来复跑本研究。保留完整reasoning/tool历史，不把网络等待当原生Decode，也不根据字符估算100K资格。
