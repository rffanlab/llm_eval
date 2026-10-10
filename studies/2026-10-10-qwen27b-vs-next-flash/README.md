# 本地 AI Max+395：Qwen3.8 27B 与 Next Flash 实测

实测与交付已完成。两套主部署各跑16次工作会话，另测预填充、流式首正文、缓存、固定解码、思考开关、长上下文及27B的AR对照，共107个记录。按事前标准评分，原始失败与事后登记诊断分别保存。

## 为什么做

比较较小的27B能否承担Next Flash同样的工作，省下内存的同时，首字等待、解码速度和完整交付要付出多少代价。前一期Gufo与Halogen的数据只作历史参考；本期Next Flash重新实测。

## 怎么测

本地Ryzen AI Max+395、128GB统一内存、内置Radeon8060S，Ubuntu24.04.5、ROCm7.2.1、内核7.0.0-31，Gufo0.11.0固定提交与同一GCC13二进制。USB4保持连接，本轮只枚举到8060S，7900XTX未参与。

- 主权重：两边均为Unsloth UD-Q4_K_XL；Next Flash配shared-Q8_0 MTP，27B配DFlash2 Q4_K_M。27B主文件17,559,178,144字节，辅助文件1,143,006,816字节，双端完整SHA校验。
- 文本任务，262144窗口，单会话，1GiB内存快照缓存。一次只运行一套主模型部署，换模型前检查释放，每个评测会话或控制请求前检查准入，运行中采样。
- 十类由浅入深的题，涵盖代码、模拟Agent、材料查证、写作。调度、日志调查和配置台账各三次，其余一次。温度0，medium思考，输出预算2048—8192且包含思考，限时60或240秒。
- 代码须全功能测试通过；Agent核对事实、权限、动作与严格JSON；写作须硬规则通过且代理编辑审读至少16/20。代理审读与本人批准分开。
- API/会话等待、引擎队列/prefill/decode/TTFT分别保存；流式首正文另记。下载、校验、加载不计入推理。未控制文件页缓存，加载不称冷启动。

[完整逐字提示词、工具事实与评分锚点](tasks-and-reproduction.md) · [事前协议](protocol.md) · [冻结记录](freeze.json) · [部署、文件身份与参数](deployment.md)。冻结提交`ccf8602`与命令围栏修正`6574c6b`均在推理前推送。

## 测试结果

| 指标 | Next Flash + MTP | 27B + DFlash2 |
|---|---:|---:|
| 主测合格交付 | 15/16 | 14/16 |
| 16次完整等待累计 | 360.33秒 | 828.36秒 |
| 主测输入token | 63,731 | 66,663 |
| 主测输出token，含思考 | 19,436 | 32,257 |
| 主测总token | 83,167 | 98,920 |
| 标准512token解码，三次中位 | 63.46 token/s | 52.38 token/s |
| 新20,246token输入预填充，单次 | 13.55秒 | 37.75秒 |
| 同档客户端首正文，单次 | 13.68秒 | 37.80秒 |
| 最大检索实际输入 | 258,028token，通过 | 258,028token，通过 |
| 该检索完整等待，单次 | 191.27秒 | 950.66秒 |
| 采样可用内存最低 | 30.58GiB | 83.76GiB |
| APU GTT峰值，系统内存分配 | 90.73GiB | 21.38GiB |

**逐题结果、差距和结论紧接每道题**，见[公众号文章](publication/wechat-article.md)与[B站视频脚本](publication/bilibili-script.md)。

两边13次非写作主测全部合格。27B短简讯与决策备忘录用尽2048/8192输出预算，最终正文为空；三段短评合格、编辑20/20，但等待152.78秒。Next Flash决策备忘录硬规则通过、编辑15/20，仍未达到交付线。

**本机继续以Next Flash为默认。**27B省内存，适合规则明确、可自动验收的小函数、对账、调度和受控只读查询。本轮完整等待更长，长材料和连续写稿尤其明显。复杂决策备忘录两边都未交出可直接使用的稿件。

### 额外控制与诊断

- 27B无DFlash2的AR标准解码12.74 token/s，带草稿52.38；两组固定探针共六对正文逐字相同。AR的C03/W03各一次均240秒客户端超时，不能据此评分其最终逻辑。
- AR两次没有终端usage；API用量为未知。服务端取消日志分别记录已生成3035与3038token，另列[取消计数](cancelled-server-counters.csv)，不把原始0累加器当成实际零消耗。
- 20K精确重复时Next Flash命中20239token缓存，首正文0.17秒；27B未命中，日志为超过1GiB的`byte_capacity`跳过。增大缓存未测。
- 短题思考开关均正确，思考增加等待与输出；缺少原生思考token细分时严格过度思考标签为未知。调度器关闭思考各一次仍13/13，等待18.06/45.95秒，不推广到所有代码。
- [登记后的W01关闭思考诊断](diagnostics/writing-mode/registration.json)：27B 3.36秒交出96字符，编辑19/20，低于100字符最低要求，仍失败。原主测14/16保持不变。
- 容量每档每端一条检索和一条512续写，三档均通过；最大窗口不等于复杂长材料可靠性。没有测512K或并发。

全档案已知API总token为1,971,640，另有2次终端usage缺失。服务端取消计数单独补充输入476、已生成6073；两类计数合计1,978,189。主测两边总token合计182,087。

## 原始档案与交付

- [所有主测轮次CSV](main-all-rounds.csv) · [逐轮API与引擎阶段CSV](all-main-and-control-turn-timings.csv) · [速度/流式/思考/容量CSV](all-native-and-stream-controls.csv)
- [完整汇总](summary.json) · [完整性审计](audit.json) · [原始主测输出](results) · [原生控制](speed-probes) · [流式请求](timing-probes) · [容量](capacity) · [编辑评分](editor-review.json)
- [准备耗时与失败历史](preparation-history.md) · [环境与释放、恢复记录](environment) · [资源采样](resources)
- [公众号可复制富文本](publication/wechat-richtext.html) · [独立富文本片段](publication/wechat-fragment.html) · [标题](publication/title.txt)
- [B站发布包与章节](publication/bilibili-release.md) · [成片镜头表](publication/director-plan.md) · [交付元数据](publication/delivery-metadata.json) · [证据绑定](publication/evidence-ledger.json)

成片使用新生成的本人授权VoxCPM2配音，降噪，无背景音乐与音效；画面为原始输出节选和实测数据回放。大视频与音频留在私有工作区，公开库只存元数据和小型资料。技术检查不代表本人试听批准，公众号实际粘贴和社交平台发布未执行。

本轮同一启动环境，未发现新的OOM或GPU恢复错误；结束后已恢复Next Flash生产服务与网关，并检查认证就绪和健康状态。模型、音色原录音、API密钥与内网地址不进入公开库。

## 复跑与离线复核

先读[复跑说明](tasks-and-reproduction.md)，复制本study到新目录执行，避免覆盖原始档案。推理需自行部署校验后的权重，接口凭据从环境提供；沿用原始题面、顺序与超时，不自动重试失败。

以下只核对已存档文件，不调用模型：

```bash
python studies/2026-10-10-qwen27b-vs-next-flash/summarize.py
python studies/2026-10-10-qwen27b-vs-next-flash/audit.py
```

同名量化等级不代表量化误差相同；本期不是BF16精度对照。模拟Agent不是生产工具操作，纯函数题不代表真实大型仓库修复，单次或三次样本不代表长期稳定性。
