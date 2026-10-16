# 社区说法与源码适用性

外部评论由用户提供，量化/完整提示词/图片原始计时未提供；2030峰值、+519%等均不作本机实测结论。

1. 本机原先已是prefill auto（上限8192），没有显式--mmap-experts，但resident-budget-gib隐含映射路径；实际日志确认GPU未持有的26.20GiB专家已复制为page-locked缓存补集，不能仅靠参数字面判断。395具有AVX-512F；不能套用双E5/7900XTX从512起步的提升倍数。
2. STRATA_PREFILL_AUTO_MAX只影响裸auto，显式auto:N优先。32768是上限，实际块受缓存/缓冲规划约束。src/program/generate.cpp:2044–2049。
3. STRATA_HIP_PROMPT_F16改变FP16输入/输出与舍入；RDNA2文档的收益不能外推gfx1151，须单独实测并验质量。sycl/src/prefill/gemm.dp.cpp:360–377。
4. STRATA_HIP_WMMA是prompt attention开关；STRATA_WMMA_GEMM是dense GEMM，不可混名。PF_GEMM优先尝试，随后才WMMA_GEMM，不是简单互斥断言。gemm.dp.cpp:838–846。
5. IO_THREADS为Linux文件队列线程数，默认16、限制1–64；常驻专家不代表PLE等文件读取消失，不预设一定有7%收益。src/platform/direct_file.cpp:61–66。
6. 当前KV resident32768会关闭KV grow。GPU端KV常驻变化小不等于主存不增长；官方DETAILS.md说明KV streaming有每token主存成本。没有本轮262K实际推理，不称免费或已验证262K质量。

来源：
- https://github.com/Niko1221/Strata/blob/v0.1.44.1/docs/STRIX_HALO.md
- https://github.com/Niko1221/Strata/blob/v0.1.44.1/docs/AMD_HIP.md
- https://github.com/Niko1221/Strata/blob/v0.1.44.1/docs/DETAILS.md
- 本机对应源码与实际二进制/配置摘要另保存；源码目录不是Git checkout，以BUILD的src标识和二进制完整SHA报告，不把空git输出当已核对clean工作树。
