# 计时探针与能力题的参数口径

冻结协议的“固定环境”段统一写了 temperature=0.3、seed=2026101600+round，表述范围过宽。能力题与长程确实使用这组值；速度探针始终使用同样已经冻结的 `speed-prompts.json`，其中明确为 temperature=0、seed=2026101500+round、max_tokens=512，并由 `speed_runner.py` 关闭思考。所有候选使用完全相同的速度探针参数。原始 payload 是最终执行依据。

本补充保留原协议、冻结文件和全部结果字节，不将文字澄清冒充新的事前设定，不补跑替换原始样本。表格与文章分别注明“贪心、关闭思考的512-token速度探针”和“temperature=0.3的能力任务”。速度探针不承担质量评分，也不能代表 medium/low 思考时的完整交付耗时。

`execution-support/warmup.py` 是单独保存每个校准/确认区块未评分 D01 暖机的启动包装；它未修改冻结题面、预算、工具、评分、transport 或测量 runner，未将暖机计入能力成绩。每次仍由会话明确发起，记录独立工作目录与资源准入。

冻结协议第三阶段将D01也列为“未用于参数选择”，但D01此前已用于全部候选的未评分暖机。这道题不用于速度/思考选优的质量分，却不能称为未见过的盲测；文章和结果保留这一限制。C01/W01/A01和整个长程未用于选参。

`profiles.json`及`environments.json`中configured_profile.selection字符串沿用了上一期量化研究的选型背景，提及GSQ与不同量化精度。它不是本轮候选定义。本轮所有候选均固定同一份Unsloth UD-IQ4_XS和MTP；实际候选以candidates.json、arm、expert_cache_units、prefill、extra_args与env字段为准。
