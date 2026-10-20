# 渠道、冻结时间与保留的旧措辞

本次DeepSeek请求使用官方API `https://api.deepseek.com`，模型ID `deepseek-flash`；响应仍为别名，具体1017版本依据官方2026-10-17更新公告。OpenCode先前失败或成功回复均不计入本研究的DeepSeek成绩。MiniMax为官方中国区API `https://api.minimax.cn/v1`。

## 不改写冻结文件的两处说明

1. `protocol.md`“怎么测”仍有“DeepSeek反代是否完全遵从采样参数无法独立验证”的旧句。这是沿用协议时残留的渠道措辞，不是实际调用来源。实际官方thinking模式不按temperature=0固定温度；请求未显式指定top_p。MiniMax正式版有效temperature=1、top_p=0.95。两端不是严格等采样实验。
2. 冻结协议所记512条校准的45062/43911 token来自切换前的渠道兼容记录，不能用它证明当前官方输入长度。正式资格只取本轮API usage：LC01为130203/127280；LC02为130185/127265（DeepSeek/MiniMax），两轮各相同；8项正式记录全部超过100000。

## 研究先后与解释边界

协议于官方第一项计分请求前重新冻结；26份冻结文件中，除`protocol.md`外的25份题面、工具和评分源文件与此前版本逐字节相同（这是文件数，不是案例数）。MiniMax本日原始22项案例在冻结前已经可见，保留其提示词、预算和评分版本，不称独立双盲预注册。DeepSeek官方22项均在此冻结后新测。语义注释和low探索的选择均受已观察MiniMax结果影响，不能包装成事前全部规划的确认性结论。

初始MiniMax复制清单有306项源文件且逐字节相同。随后发现SCP合并目录可能留下不属于最终快照的`previous.txt`；通过最终远程目录tar准确重新抓取，移除两个本地合并残留。原始结果、回复、工具轨迹与评分未改，最终目录差异见`final-capture-audit.json`。这一修正不能被表述成模型多交了文件。

原生Prefill/Decode均无服务端计算计时；流式首事件和完整请求等待保留，但不是原生速度。云端硬件、量化、服务负载与实际扣费未知。

来源：[DeepSeek更新](https://api-docs.deepseek.com/updates/)、[DeepSeek思考模式](https://api-docs.deepseek.com/guides/thinking_mode/)、[MiniMax正式发布](https://www.minimax.io/blog/minimax-m31f)、[MiniMax兼容API参数](https://platform.minimax.io/docs/api-reference/text-openai-api)。
