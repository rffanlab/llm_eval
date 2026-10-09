# 本地 AI Max+395＋USB4 RX7900XTX：Strata评测（进行中）

## 为什么做

测Qwen3.8-Flash-Next的量化容量、真实长输入与工作交付。对照为同日重跑的Halogen0.9.1 W4B内置GPU部署；不是单独显卡、框架或量化的因果实验。

## 怎么测

[冻结协议](protocol.md)、[本期完整任务卡](task-cards-current.md)、[模型与文件SHA](model-manifest.json)、[实际环境](environment)、[补充运行保护](pre-strata-amendments.md)、[524K安全余量修正](capacity-reserve-correction.md)。原任务字节与上一期相同，十类小型合成题，由入门到进阶；不是大型真实仓库或生产Agent认证。

## 已完成与未完成

- Halogen同日基线：16主会话，硬验收15/16，合格交付14/16，已知86,073token、累计模型会话521.936秒。固定512输出三次解码中位55.625token/s。
- Strata IQ2_XS：16主会话，硬验收与合格交付8/16，已知111,085token、累计会话684.9643秒。固定512输出三次解码中位109.4token/s。速度与交付是两种指标。
- IQ2真实容量梯度闭合：32K至原生262K，以及YaRN2的524K。最高检索实际输入520,190token，824.136秒；同前缀512探针复用507,904token、还需读12,271token，完整41.146秒、解码68.7token/s。每点仅一次，不能证明稳定性或硬件绝对上限。
- IQ4主测与控制已闭合：16个主会话，硬验收13/16、合格交付12/16；调度器三次13/13，来源短评合格，团队备忘录编辑15/20未达门槛。固定512解码中位44.8token/s。已知主测小计84,573token，另一次HTTP503的后续用量未知；累计请求870.884秒不含重启恢复流程。容量梯度进行中。
- Q4XL全部四片通过冻结SHA，但尚未启动或计分，不能说已经运行111.33GB量化。

[逐题当前汇总](summary.json)、[原始首答](results)、[写作审读](editor-review.json)、[容量与资源](capacity)、[运行故障与恢复记录](runtime-recovery.md)、[故障台账](runtime-incidents.json)。IQ4原失败保留，不重跑替换；框架加载控制尝试三次仍无ROCm设备，/dev/kfd打开异常。另17条未发送到模型的连接失败在独立诊断目录，性质不同。

用户现场重启后先取证：旧日志显示外卡MES不响应、自动GPU reset最终ret=-110；首次verify故障触发因素仍未确证，所查日志无OOM-kill，Halogen在IQ4原启动前已停止。重启后ROCm恢复，停掉开机自启的Halogen并核对无模型进程后，才启动原配置IQ4继续未测项。当前仅IQ4运行，换档前等待进程退出、内存/显存释放；[诊断](diagnostics/post-reboot-assessment.json)与[单模型准入观测](diagnostics/single-model-admission.jsonl)保留。原Halogen最终恢复尚未验证，Q4XL等待串行测量。公众号与视频仍待完整数据和服务恢复。
