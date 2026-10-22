# 7900 XTX跑Qwen3.8 Next Flash：Gufo、Halogen与Strata

日期：2026-10-22。硬件：Xeon W-2133、128GB DDR4、RX7900XTX 24GB（gfx1100），驱动功耗上限配置265W。主机上游PCIe3.0×16；显卡后端内部桥接段为4.0×16。上下文与模型大小不等同于显存占用。

## 为什么做

确认AI Max+395专用推理引擎能否迁移到独立7900XTX机器，替代Strata运行Qwen3.8 Next Flash。先判断运行资格，符合条件才进行同机速度排名。

## 怎么做

协议在新检查前冻结：[protocol.md](protocol.md)、[freeze.json](freeze.json)。主权重为Unsloth UD-Q4_K_XL。

- Gufo v0.20.0，commit `0c03748a271eab895befc0d2343aa50ca4b6d836`。使用未修改的已校验二进制与现有ROCm库执行GPU诊断，没有加载模型。
- Halogen v0.18.13，commit `3f2adcfca6be623c8ec4f69331cbf97beff55251`。原样提取其入口脚本的`host_preflight()`，在真实系统独立执行，没有启动完整容器。
- Strata发行v0.2.2，内部engine/Control0.1.47。沿用现有权重与配置，另启隔离服务完成一次D01新请求，与同日既有成绩分列。
- 保持单模型，不升功耗、不改固件或驱动、不伪装GPU架构。

复核程序：[reproduce_compatibility.py](reproduce_compatibility.py)。程序只接受本地已安装文件，不下载或加载模型。Halogen入口文件需与固定SHA一致；函数执行不同于完整引擎实测。

## 测试结果

|指标|Qwen3.8 Next Flash / Gufo v0.20.0|Qwen3.8 Next Flash / Halogen v0.18.13|Qwen3.8 Next Flash / Strata v0.2.2|
|---|---|---|---|
|实机硬件检查|gfx1100 unsupported；exit1|实际110000，要求110501；exit1|可推理|
|本轮模型调用|未运行|未运行|D01新请求正确完成|
|Prefill token/s|不适用|不适用|46.54，单次|
|Decode token/s|不适用|不适用|32.91，单次|
|完整等待|不适用|不适用|8.527秒，单次|
|输入/生成/缓存token|不适用|不适用|149 / 175 / 0|

Gufo版本命令成功、实际GPU识别正确，架构检查拒绝gfx1100；其CMake也硬性要求gfx1151。Halogen当前官方版本同样限定gfx1151。因此没有三个引擎在同一机器上的可比速度，不填零、不计算倍数，也不借用395成绩代替。

Gufo诊断中的`memoryType/isUnified`、工具链版本和`engineRevision`等包含原项目的Strix-Halo预设值，不能作为这台独显机器的硬件／工具链实测。本研究仅采用可与HIP、sysfs交叉核对的实际GPU名称与架构；硬件配置以系统原始记录为准。

### 同日既有工作成绩

完整工作成绩引用[同日独立Strata复测](../2026-10-22-strata022-rx7900xtx-retest/)，不是本轮再次执行。按[source-references.json](source-references.json)逐文件校验哈希；新D01不混入既有两轮中位数。

- 七类短题14次：严格交付11/14。代码、基础抽取、事实短讯、受控库存通过；排障第二轮JSON加围栏，复杂写作两轮未过编辑门槛。
- 四阶段连续项目两轮：最终文件正确2/2，严格全程交付0/2，原因是S1没有阶段收尾。
- 真正长上下文：每轮API实际109148输入token，两个完整记录；语义决策正确，引用含DOC前缀，严格12/17。题面缺裸ID示例，存在验收契约歧义；原分保留，语义诊断不替换成绩。
- 所有短题、各长程阶段、整项和吞吐的Prefill、Decode、完整等待、token与交付均在[summary.json](summary.json)；指标是每轮汇总原生计数/计时后再取中位，缓存另列。缺失值不反推。

冻结提示词、工具和评分直接见[短题tasks.json](../2026-10-22-strata022-rx7900xtx-retest/tasks.json)、[短题工具与评分](../2026-10-22-strata022-rx7900xtx-retest/short-suite/)、[连续项目完整定义](../2026-10-22-strata022-rx7900xtx-retest/long-horizon/task.json)、[长上下文完整输入与评分](../2026-10-22-strata022-rx7900xtx-retest/long-context/)。原始回复、工具轨迹、阶段快照和失败保留在来源研究的`results/`，不修改原评分。

## 综合建议

在本机运行这份Qwen3.8 Next Flash量化，推荐Strata v0.2.2。它具备当前可验证的运行和交付路径，适合可验代码、简单抽取与受控工具；复杂写作、连续阶段收尾及严格引用仍需检查。Gufo v0.20.0与Halogen v0.18.13当前适用gfx1151设备，不能作为本7900XTX机器的替代方案。此结论不等于未来永远无法移植。

配置265W不代表每一瞬间都不超过265W，也不是插座功耗。

## 上游依据

- [Gufo固定commit编译约束](https://github.com/gufo-org/gufo/blob/0c03748a271eab895befc0d2343aa50ca4b6d836/CMakeLists.txt)
- [Halogen固定commit支持范围](https://github.com/peonist-ai/halogen-flash-server/blob/3f2adcfca6be623c8ec4f69331cbf97beff55251/docs/limits.md)
- [Halogen固定commit硬件预检](https://github.com/peonist-ai/halogen-flash-server/blob/3f2adcfca6be623c8ec4f69331cbf97beff55251/deploy/entrypoint.sh)

文章、视频脚本、封面和成片校验值见`publication/`。不包含模型权重、密钥、内网访问配置或私有音色参考。
