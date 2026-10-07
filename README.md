# llm_eval

可公开复跑的工作能力评测：为什么测 → 怎么测 → 测试结果。

首期：137 本地 Qwen3.8 Flash Next 与阿里云 Token Plan `qwen3.8-flash` 的工作能力对照。测试前规范见 [方法](studies/2026-10-07-local-vs-cloud/protocol.md)，完整题面与验收答案由 [题库生成器](suite/build_suite.py) 写入 `suite/tasks.json`。结果保留响应正文、用量、计时、工具轨迹和失败。

运行环境 Python 3.10+，标准库。无第三方安装需求。密钥只从环境读取。`python runner.py --help` 查看逐题运行方式；本仓库不提供 Token Plan 批量执行入口。生成代码只在受限制的独立进程中执行纯函数测试，拒绝导入、文件和网络调用。

题量有限，结论只针对被测任务与当次配置。云端与本地模型身份不能证明完全相同，差距不能直接解释为量化损失。
