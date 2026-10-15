# 运行分配与协议单位更正

正式测试开始后核对原生启动日志时，发现冻结协议及profiles.json将 `--expert-cache 9015` 误标为MiB，并称为相同GPU缓存预算。这是单位和实验解释错误。实际三档均使用同一CLI值9015，没有修改配置或重跑已记录题目；该值按各自最大专家块换算，不能当作相同字节预算。

三档实际GPU专家缓存分别为GSQ IQ3_S的11781槽/22.35GiB、Unsloth UD-IQ4_XS的12944槽/29.23GiB、UD-Q4_K_XL的11484槽/33.53GiB。完整原生行和发现时案例数保存在runtime-allocations.json。GSQ另有完整46.84GiB主存专家arena；Unsloth分别使用26.20/38.20GiB专家缓存补集。统一内存下这些分配会共同占用主存，不与文件大小等同。

因此本期比较三套实际Strata部署的交付、等待与资源效率，不能把结果解释成等内存预算或等bit数的量化算法对决。冻结协议原文保留便于审计；正文和视频采用本更正及真实采样。题面、预算、评分、模型参数和全部原始结果均未改动。

来源：[Strata 0.1.44.1 DETAILS](https://github.com/Niko1221/Strata/blob/v0.1.44.1/docs/DETAILS.md)，运行分配见[runtime-allocations.json](runtime-allocations.json)。
