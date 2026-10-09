# 512K 客户端中断与独立冷启动补测

登记时间：2026-10-09；登记发生在恢复请求之前。

UD-IQ4 的首次 524288 窗口检索已开始推理，控制端 Windows 在 14:27:03 意外重启，记录进程丢失。恢复连接时，远端仍在处理原来的 520190 token 输入。未收到完整 API 回复，无法给出正确性、完整 token 消耗或客户端请求耗时。这次记录保留为未评分中断，不能记为模型答错或零消耗。

- 原始记录：[incident.json](diagnostics/client-reboot-001/incident.json)
- 原始资源采样：[resources.jsonl](diagnostics/client-reboot-001/resources.jsonl)
- 原始启动快照：[environment/strata-iq4-524288.json](environment/strata-iq4-524288.json)
- 原始服务日志：[logs/strata-iq4-524288](logs/strata-iq4-524288)
- 停止后的资源释放：[model-release-strata-iq4-client-reboot.json](diagnostics/model-release-strata-iq4-client-reboot.json)

恢复方法：停止原来本实验独占的 IQ4 API 与引擎，确认 Halogen 停止、无其他模型进程、主内存和外卡分配回落，再用原有 524288 / YaRN factor2 配置重新启动。核对模型、二进制、tokenizer 与 API 插桩哈希一致，服务请求计数为零后再调用。检索沿用冻结输入及输出上限4090，随后沿用512 token同前缀续写。温度0、关闭思考、1800秒截止及验收标准均不变。

恢复结果、采样、状态与快照使用 `client-recovery` 独立后缀。首次被中断请求和此次完整补测分别公开；恢复等待与重启时间不计入请求速度。已有主测和原生容量结果不重跑。

Windows 系统事件报告 bugcheck 0x116。微软将其定义为显卡驱动超时后恢复失败；该代码不能证明具体应用、远端模型或硬件故障是根因。本次中断与先前 IQ4 verify layer31 / 外卡 MES 故障分别记录。

参考：[Microsoft 0x116说明](https://learn.microsoft.com/en-us/windows-hardware/drivers/debugger/bug-check-0x116---video-tdr-failure)
