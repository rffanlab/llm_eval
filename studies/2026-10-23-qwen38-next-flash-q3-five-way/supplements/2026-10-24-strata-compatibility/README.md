# Qwen3.8 Next Flash：追加Strata兼容性验证

原始研究的题面、预算、评分与已生成结果保持冻结。本补充记录重新验证Unsloth UD-Q3_K_XL及OrcaRouter Q3_K_L的部署路径；原始安装器按文件名排除它们，不能直接作为底层不支持的实测结论。

实际已下载GGUF头显示：Unsloth的专家是IQ3_XXS/IQ4_XS和IQ4_NL/Q8_0混合布局；OrcaRouter的专家是Q3_K/Q5_1。两者已通过原版打包工具的48层、每层512专家布局校验。这仅是文件结构检查，尚不是GPU推理或速度成绩。

追加协议：使用原始固定revision/SHA权重、原0.1.47 HIP引擎与265W，原版打包工具加--compat-bf16；保持专家及PLE源字节，小投影转换的BF16舍入与conversions.json单独说明。逐个加载，成功后执行原冻结29项套件，包含长程及真实100K以上长上下文；失败保留实际部署日志，不赋零质量分或零速度。两组最多追加58个执行项，原9条Q4对照不重复。

Unsloth路径有[上游PR844](https://github.com/Niko1221/Strata/pull/844)的外部实跑记录；该PR因仓库历史重写关闭，并没有合并标志。OrcaRouter须核对专家分组内核，不能由普通投影的Q3_K支持推断。[固定上游源码](https://github.com/Niko1221/Strata/blob/8183c6b67162340c09b67360860177c577a65f2e/src/kernels/cuda/iq_kernels.cu)作为排查依据。

状态：追加测试已排队，GPU实测结果待补。本文件不代表两个候选已获得部署或质量推荐。
