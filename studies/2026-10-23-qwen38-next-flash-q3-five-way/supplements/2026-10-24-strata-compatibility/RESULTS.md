# 实际兼容结果：Qwen3.8 Next Flash Q3 / Strata0.1.47 HIP

README保留排队前的记录。实际结果见[逐项兼容证据](../../compatibility-outcomes.json)和[完整报告](../../report.md)：Unsloth UD-Q3_K_XL完成29项，真实109186输入两轮；OrcaRouter Q3_K_L被layer0 Q3_K/Q5_1专家内核检查拒绝，未进入model-ready，未发任务请求，不赋速度/质量零。

小PLE_value也属于Q8_0→BF16兼容转换，不能把此前“PLE源字节保持”扩写成所有PLE相关运行张量位相同。原GGUF源文件不变，48层专家和大PLE/ngram查表直接读取原权重。195个小投影的BF16最大绝对舍入误差0.014404296875，另小PLE卷积F32→F16最大误差2.98e-8。
