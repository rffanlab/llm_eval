# Ryzen AI Max+395：Qwen3.8 Next Flash 的GSQ与Unsloth量化对比

## 为什么做

同一个Qwen3.8 Next Flash有不同量化。比较GSQ-RCO IQ3_S、Unsloth UD-IQ4_XS与UD-Q4_K_XL，检查更小的权重是否带来更低内存、更短等待，以及代码、工具、写作与连续工作流会损失多少交付质量。它们是不同文件大小的实际部署选项；不把差异单独归因于GSQ或Unsloth算法，也不把作者成绩当作实测。

## 怎么做

同一台Ryzen AI Max+395、Radeon8060S gfx1151、128GB统一内存、Ubuntu24.04.5、同一Strata0.1.44.1 HIP构建与TheRock7.14.1运行时。Gufo的Flash-Next加载器不能直接接收这些GSQ格式，因此三档都使用Strata，不混入Gufo成绩。实际二进制、原权重、pack、共同MTP及环境在正式调用前逐档封存SHA256。原权重来源、固定revision、分片大小和SHA见profiles.json。仅文字任务，不加载vision。

统一65536上下文、int8 KV（resident32768）、并发1、expert-cache9015MiB、spec4/min-p0.5、同一原始checkpoint的Q2_0 MTP runtime、medium思考、temperature0.3/top_p0.95/top_k20、每轮seed=2026101500+round，历史思考不回传。采用引擎gfx1151默认内核与匹配hipBLASLt调优表，不开启改变数值的实验开关。Unsloth两档分别采用setup给出的55/71GiB专家主存预算，GSQ采用完整原生专家arena；预算不等同文件大小，实际resident/file-tier分配与内存峰值另行报告。保持共同硬件和GPU缓存预算，不强制较小权重浪费内存来模拟较大文件。

每次调用前检查仅有当前注册模型的Strata前后端进程、前台生产路由已隔离、实际模型别名与配置摘要不变、无并行请求、MemAvailable>=8GiB。换档先停止原服务，确认引擎退出及主存/GTT回落后再启动。发生重启或驱动错误先保留诊断，再决定是否续测。原失败和输出一律保留，不选最好结果、不换设置补分。

### 任务、工具与预算

题面、夹具、可见测试、独立断言与参考解见tasks.json、task-cards.md、short-suite与long-horizon。7类短题由浅入深：D01 L1严格JSON筛选、C01 L1金额函数（9测试）、W01 L1限事实100–180字短评、A01 L2库存查询与一次预留（禁止付款）、C03 L3按定义ID优先贪心调度（13测试，非全局最优）、A02 L3日志故障/临时读取失败重试/注入指令拒绝、W03 L3 600–900字决策备忘录。每档每题两轮；D01/W01总输出4096，其他8192（含思考）。每调用240秒、整题480秒，Agent最多6次回复且每次只一个工具。任务是L1–L3合成小样本，不代表生产仓库或全能力榜单。

长程LH01采用1.1.2验收，在同一会话、工具与工作区连续四阶段：S1修复金额对账；S2截止时间/退款/四舍五入变更且兼容v1；S3发布、注入一次ENOSPC、保留旧发布并恢复；S4迟到退款R04、最终产物与400–900字报告。每档两次独立episode，每阶段最多12次回复（含结束说明），每调用8192/240秒，episode累计65536输出/2400秒。工具仅可改workflow.py与delivery.md，纯函数worker3秒CPU/512MiB、外层6秒；隐藏测试不反馈。首次模型调用前验证坏实现失败、参考解全部通过。

过度思考诊断：D01每档额外两轮关闭思考，比较准确率、完整等待、生成token、思考字符与截断；不把思考字符换成token。长程另列各阶段工具轮数、结束说明、思考/生成量与完整交付，合理故障恢复不自动判作过度思考。

速度探针每档短输入、约4K、约32K，各固定生成512token、三轮、关闭思考、每调用300秒，具体payload见speed-prompts.json。每种长度/轮次的标识前缀不同，避免4K与32K复用同一长正文前缀；实际新计算/缓存token仍按引擎返回列出，不宣称清空操作系统页缓存或冷SSD。速度探针不计能力分。三档按r1/r2轮次分块轮换，各档内部次序相同；第三轮只跑速度探针。首档顺序GSQ、Unsloth IQ4_XS、Unsloth Q4_K_XL，第二轮倒序，第三轮同首轮。每次启动做同一段不计分短预热；启动与加载耗时单列，不混入请求计时。

### 评分、计时与结论门槛

严格JSON与字段须全对、代码独立功能测试须全过、Agent实际动作与权限须全过。写作硬格式独立判分；代理编辑按事实/完整/清楚/可用各0–5，>=16且事实>=3才通过。编造关键事实或将未测能力当实证，事实<=2。该审读不盲，不称真人验收。长程完整交付须四阶段硬验收全过、预算内有非空结束说明、最终文件/回归正确、报告硬条件全过且编辑>=16。两轮都完整交付才称该受控任务合格；双方失败不能因差距小称可用。

每题、长程每阶段、episode整体与短题整套、思考诊断、速度探针均列Prefill/Decode token/s、完整等待、生成/输入/缓存token、完成度与资源采样。每轮先sum(prompt_n)*1000/sum(prompt_ms)与sum(predicted_n)*1000/sum(predicted_ms)，再跨轮取中位。Prefill仅新计算输入，cache_n另列；Decode含引擎原生思考、正文、工具参数生成数。显式0token/0ms调用计为零工作覆盖，该调用自身速率未知；缺计时、不正计时或整项无计算速率保持未知，不用墙钟反推。保留引擎原生rate作为交叉核对，原生小数ms可能有舍入误差。

API首事件/首思考/首正文/首工具、API完整等待、工具执行和整个交付等待分开；隐藏验收不算交付等待。保存原始SSE、usage/timings、调用payload、工具轨迹、每阶段快照及2秒资源采样。先比完整交付、长程完成与严重错误，再比较相同任务完整等待/token/内存。给出本轮综合最优的明确推荐，并说明其他档的具体适用条件；两轮小样本不作统计等效、全天稳定或量化普遍优劣证明。

主测42短题、6长程episode、6关闭思考诊断、27速度探针，共81案例。每例由活跃会话单独发起和审读，不把兼容预检计分。凭据、内网地址、SSH与私密音色不入公开库。

## 来源

- https://huggingface.co/ISTA-DASLab/Qwen3.8-Flash-Next-GSQ-RCO-GGUF
- https://huggingface.co/unsloth/Qwen3.8-Flash-Next-GGUF
- https://github.com/Niko1221/Strata/tree/v0.1.44.1
- https://github.com/gufo-org/gufo/blob/main/docs/models/qwen3.8-flash-next/README.md
