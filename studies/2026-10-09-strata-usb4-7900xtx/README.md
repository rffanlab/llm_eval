# 本地 AI Max+395 外接7900XTX：Strata跑千问，能跑多大、多快？

## 一、为什么做

测本地Ryzen AI Max+395通过USB4连接RX7900XTX后，用Strata运行Qwen3.8-Flash-Next能处理多大真实输入、运行哪些量化文件，以及同一套代码、Agent、写作工作能否交付。当天重跑Halogen0.9.1内置GPU部署作对照；框架、量化和设备同时不同，不作单因素因果结论。

## 二、怎么测

[完整协议](protocol.md) · [完整提示词与评分卡](task-cards-current.md) · [冻结SHA与参数](freeze.json) · [模型身份与完整文件SHA](model-manifest.json) · [实际环境](environment)

十类小型合成题，由入门到进阶；每套16主会话，C03/A02/E01各三次。代码跑功能测试，Agent检查权限、工具与严格JSON，写作先查硬规则再做编辑审读。温度0、medium思考，原预算包含思考，无格式修复、无失败自动重跑。另测固定512输出、开关思考以及32K至YaRN2的524K容量梯度；每容量点一组，不能证明全天稳定、并发或硬件绝对上限。

本地机器一次只加载一个模型；换档确认进程退出及RAM/VRAM/GTT释放，每条请求前检查实际服务、模型身份与可用内存。故障重启先诊断再续跑未记录项。

## 三、结果

| 部署 | 硬验收 | 合格交付 | 固定512解码中位 | 主测已知token |
|---|---:|---:|---:|---:|
| 内置GPU / HGN | 15/16 | 14/16 | 55.6token/s | 86,073 |
| 7900XTX / IQ2_XS | 8/16 | 8/16 | 109.4token/s | 111,085 |
| 7900XTX / UD-IQ4 | 13/16 | 12/16 | 44.8token/s | 84,573＋未知用量 |
| 7900XTX / UD-Q4XL | 13/16 | 12/16 | 32.7token/s | 88,624 |

[逐题文章及即时比较](publication/wechat-article.md) · [富文本HTML](publication/wechat-richtext.html) · [视频文稿](publication/bilibili-script.md)

[原始工作首答](results) · [写作编辑复核](editor-review.json) · [完整统计](summary.json) · [容量结果](capacity) · [同步资源](resources) · [审计与token台账](audit.json)

### 故障与统计边界

IQ4一次A02主测HTTP503/verify layer31失败保留，后续用量未知。外卡之后出现MES队列错误和GPU reset失败；第一次verify错误的触发原因未确证。Windows控制端另一次0x116重启中断了512K记录，原资源和日志保留，该次不评分、用量未知；另行登记相同输入与参数的完整冷重启补测。初次512K HTTP400是8token安全余量校验拒绝，没有开始推理；另17条未到达服务的连接失败独立归档。

[远端运行故障和恢复](runtime-recovery.md) · [控制端中断和补测](capacity-client-interruption.md) · [安全余量修正](capacity-reserve-correction.md) · [单模型准入](diagnostics/single-model-admission.jsonl) · [原Halogen恢复验证](restored-service.json)

文章的合格交付含代理编辑审读，不冒充本人验收。视频为本人授权VoxCPM2新旁白，无背景音乐与音效；源文件节选和测量回放不冒充现场录像。私有参考音频、内网地址、密钥和大型模型文件未入库。
