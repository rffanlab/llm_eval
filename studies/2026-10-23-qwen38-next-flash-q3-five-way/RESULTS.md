# Qwen3.8 Next Flash：五方Q3在RX7900 XTX的实测

[完整文章](report.md) · [逐题与逐阶段原生计时/完整等待](metrics-reviewed.json) · [全部允许公开的回复和工具轨迹](results/) · [精确SHA编辑审读](editorial-reviewed.json) · [最终文件](final-artifact-audit.json) · [兼容实证](compatibility-outcomes.json) · [完整提示词](full-prompts/) · [原始与公开文件SHA](result-file-manifest.json)。

原8组232项、Unsloth-Strata29项完成；OrcaRouter在当前Strata0.1.47加载专家时被原生内核拒绝，不计质量或速度零。五方共同llama.cpp与四方实际Strata分表，Q4仅9条吞吐参考。SC117/Orca去拒答、Swift后训练身份不混同于原版量化。

按冻结常规12/14门槛先筛，Unsloth UD-Q3_K_XL＋llama.cpp b11829质量95.5、12/14，为本轮常规综合选择；Strata-Swift虽快但11/14，只作有严格外部校验的受控路径。实际100K题均109186输入，没有部署两轮严格全过。18组最终文件均正确，原始长程严格闭环、通用回归和备忘录事实审读仍分别报告，不以文件正确掩盖失败。

运行 `python recompute_reviewed.py --output recomputed.json` 只读复算公开证据，不发模型请求。所有复算字段与最终审读指标相同。冻题、评分、预算、源代码和原始README保持测前字节。推理引擎的原生计数、缓存与EOS口径见native-timing-contract.json；HTTP累计等待另列。
