# RX7900 XTX：DeepSeek V4.1 Flash1017 GSQ-RCO IQ2_XXS与Qwen3.8 Next Flash Unsloth UD-Q3_K_XL

58项固定执行单位全部记录和逐正文/工具/产物主审；两方实际退出。DeepSeek23正常闭合、6限时部分交付；Qwen29正常闭合。常规严格10/14与11/14，均未达到12/14；长程严格均0/2，Qwen两轮所有阶段功能100%且真实发布故障恢复，DeepSeek完整功能未知。两方正式长文输入分别每轮102591和120981token、cache0，严格16/17与17/17各两轮。DeepSeek唯一LC差异是P-V2文档标识与v2版本规范，金额/决策/证据正确，不能改评分或扩大为理解全错。

限定本硬件与任务，综合推荐Qwen3.8 Next Flash Unsloth UD-Q3_K_XL用于受监督工作及本轮冻结100K材料，保留常规及长程严格失败；没有无人监督整包交付资格。DeepSeek未知域不填0、不计算虚假总分差。硬件纠正DIMM事件及4KB自动隔离历史未修复，正式区间RAS未新增；两轮不外推全天稳定。

- [完整文章](report.md)
- [测前冻结协议](protocol.md)与[34文件冻结SHA](freeze.json)
- [逐轮逐题逐阶段native/API/缓存/完整等待/资源](metrics-reviewed.json)
- [全部公开原始答复、请求、原生日志、工具轨迹与产物](results/)
- [精确源/公开SHA映射](result-file-manifest.json)
- [实际编辑判断与原始结果SHA](editorial-reviewed.json)
- [未编辑正文可读提取及来源SHA](readable-answers/manifest.json)
- [完整LC材料](long-context/materials/)、[短题](tasks.json)、[长程系统/阶段](long-horizon/task.json)、[评分](scoring.json)
- [许可与分发范围](license-and-provenance.json)
- [配套公众号文章、视频脚本、字幕与封面](media/README.md)；[实际成片技术与审读范围](media/package-summary.json)

运行 `python recompute_reviewed.py --output recomputed.json`，不联网、不发模型请求，验证公开文件SHA与全部逐题/阶段原生计量、API缓存、资源和中位数。165闭合请求metricsID唯一；6未闭合调用保留未知。完整原始SSE与根权限准入证据私有保留。未分发权重、引擎二进制、凭据或私密参考音。

原始README和protocol描述测前状态，按freeze保留字节；当前结果以本页和固定结果文件为准，不把旧状态当成重跑授权。
