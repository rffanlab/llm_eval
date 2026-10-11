# Halogen 与 Gufo：长程订单对账任务补测

本研究测同一台本地 Ryzen AI Max+395 上，两套本地模型部署连续维护一个小型订单对账项目的表现。任务包含基础修复、需求变更、发布故障恢复和最终交付四个阶段；每个 episode 使用持续会话和工作区，单模型串行运行。

## 冻结版本与范围

正式结果使用本期实际冻结的 **v1.0.1 frozen-suite**。首轮诊断中旧 AST 评分器误拒正常单下划线命名，诊断记录保留但不计正式结果；修正后的题面、夹具、工具、参考实现和评分规则见 [`observations.md`](observations.md) 与 [`protocol.md`](protocol.md)。

每套部署运行两次独立 episode；Gufo 与 Halogen 不同时加载，按固定顺序串行运行。模型加载、服务切换、隐藏验收和编辑审读不计正式请求等待。原始诊断和中止记录只用于解释运行边界，不改写正式结果。

未来的 canonical v1.1.1 尚未用于本期测试；[`future-suite-revision.json`](future-suite-revision.json) 只记录未来修订信息，不能当成本期结果。

## 复跑入口

本期题面、完整提示词、工具和冻结材料位于 [`frozen-suite/`](frozen-suite/README.md)。从仓库根目录复跑下面的命令；不要改用后续的 [`long_horizon/`](../../long_horizon/README.md) 覆盖本期条件：

```powershell
# 先在进程环境设置 LOCAL_BASE_URL、LOCAL_MODEL、LOCAL_API_KEY。
# LOCAL_GUARD_COMMAND 是每请求检查单模型与资源状态的 JSON 命令数组。
python studies/2026-10-12-halogen-gufo-long-horizon/frozen-suite/runner.py --profile gufo-q4xl-mtp --round 1 --output ./private-long-horizon-results
```

runner 会在输出根目录下创建 `profile/r1`，已存在的目录拒绝覆盖。两端各执行 round 1、2，切换部署前停止上一模型并确认资源释放。模型接口和准入配置详见冻结题面的运行段落。runner 每阶段自动调用独立验收；离线参考与评分器实现见 [`frozen-suite/grade.py`](frozen-suite/grade.py)。研究协议、硬门槛及资源边界见 [`protocol.md`](protocol.md)；其中历史的共享题库路径以本目录的 frozen-suite 为准。

## 记录与审读

- 汇总指标与四个 episode 的阶段结果：[`summary.json`](summary.json)
- 报告事实、长度与编辑审读：[`editor-review.json`](editor-review.json)
- 运行限制、评分器修正和未测因素：[`observations.md`](observations.md)
- 初始冻结与未来修订记录：[`freeze-v1.json`](freeze-v1.json)、[`freeze.json`](freeze.json)、[`future-suite-revision.json`](future-suite-revision.json)
- Gufo 原始记录：[`results/gufo-q4xl-mtp`](results/gufo-q4xl-mtp)
- Halogen 原始记录：[`results/halogen-w4b`](results/halogen-w4b)
- 164次正式请求与发布文件核验：[`audit.json`](audit.json)
- 公众号文章：[`publication/wechat-article.md`](publication/wechat-article.md) · [可复制富文本](publication/wechat-richtext.html)
- B站：[脚本](publication/bilibili-script.md) · [发布文案与实际章节](publication/bilibili-release.md) · [镜头与来源](publication/director-plan.md)
- 成片SHA256、时长与音频核验：[`publication/final-media-audit.json`](publication/final-media-audit.json)
- 配置与权重来源：[`environment.json`](environment.json)

本期只有两套部署各两次 episode，属于受控小样本；结果不宣称统计等效、生产可靠性或全天稳定性。正式交付结论必须同时考虑四阶段硬验收、预算内结束说明和最终报告编辑门槛。
