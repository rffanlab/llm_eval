# Strata 首次请求前的运行保护补充

2026-10-09，Halogen 同日基线已完成、Strata 尚未发起请求时补充以下实现检查。题面、评分规则、生成预算与容量梯度不变；原 freeze.json 的历史文件 SHA 保留，实际运行版本 SHA 另记 environment 快照。

- 容量 runner 在请求前核对环境中 tokenizer/template SHA 与题面记录。API 输入计数不符时保留首次响应，标为无效测量，并停止后续容量窗口；语义或格式答错继续按冻结梯度执行，不能把 `finished_without_operational_error` 理解为验收通过。
- 容量异常记录增加 HTTP status 整数，不保存请求凭据。
- 资源采样按 AMD Navi31 PCI device 744c 与 24GiB 显存唯一识别外置卡，并保存实际 BDF；关键显存/GTT/busy 字段缺失时停止采样。本机的已核验路径是 0000:05:00.0。
- 汇总增加事前等待门槛内的合格交付数，和只看交付质量的数量分开；编辑审读必须绑定完整 answer.txt 的 SHA。
- Windows 客户端先建立 SSH 到远端 loopback API 的端口转发。隔离服务仅监听远端 loopback 且要求 Bearer 认证；私有连接信息不发布。

这些补充不重跑或替换 Halogen 基线首答，不改变任何题目验收门槛。
