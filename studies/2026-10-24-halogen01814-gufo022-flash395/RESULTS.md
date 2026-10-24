# Qwen3.8 Next Flash：Halogen0.18.14 vs Gufo0.22.0

[实测文章](report.md) · [逐题/逐阶段原生计时](metrics-reviewed.json) · [原始回复与工具轨迹](results/) · [实际编辑审读](editorial-review.json) · [最终文件校验](final-artifact-audit.json) · [缓存/评分/资源边界](analysis-limitations.json) · [HTTP累计等待](http-wait-supplement.json)。

58/58测量完成，Gufo UD-Q4_K_XL与Halogen原生v2 HGN是完整部署对照。原始README、协议与29个冻题文件保留测前字节。两者严格短题均10/14，未达12/14常规门槛；长程均2/2、实际109186-token题Gufo2/2/Halogen1/2。32K Halogen两轮缓存4032，不能描述为三轮无缓存。

用 `python recompute_reviewed.py --output recomputed.json` 本地复算（只读公开文件，不调用模型）。另有按原始HTTP计时汇总的等待补充表；完整等待包含准入检查与工具，不事后修改原记录。
