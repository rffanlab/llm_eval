# 本地AI Max+395：Gufo与Halogen实测

同机Ubuntu、128GB、内置8060S，现有Halogen0.9.1 HGN W4B+overlay对照Gufo0.11.0 UD-Q4_K_XL+shared-Q8_0 MTP。最终采用同一次116GiB GPU分配上限修正后的启动数据，旧基线与首次加载失败保留。

## 结果

| 指标 | Halogen | Gufo |
| --- | --- | --- |
| 合格交付 | 14/16 | 15/16 |
| 固定512解码，三次中位 | 57.162token/s | 63.498token/s |
| 16次完整等待累计 | 504.0533秒 | 357.7342秒 |
| 主测输入／输出／总token | 63867／22206／86073 | 63731／19436／83167 |
| 复杂决策备忘录编辑分 | 15/20 | 15/20 |
| 最大完成检索输入 | 258028token | 258028token |

Gufo多通过的是来源格式短评。所有代码与合成Agent题两端都通过；复杂备忘录未达16分门槛。Gufo内存余量最低30.7GiB，Halogen86.1GiB，比较的是完整部署，不是纯量化精度证明。

质量、速度、容量、运行及最终现有网关契约达到事前门槛，本地服务已切到Gufo，保留Halogen与原网关配置回滚。首次加载失败、初次网关接入失败均保留，详见[替换记录](adoption.json)和[接口说明](consumer-api.md)。

## 复跑与材料

- [完整题面、系统提示词、输出预算与验收](tasks-and-reproduction.md)
- [事前协议与替换门槛](protocol.md) · [原冻结](freeze.json) · [共同启动冻结](phase-freeze.json)
- [部署与权重身份](deployment.md) · [严格评分实现](../../sandbox_grade.py) · [合成Agent工具](../../agent_sim.py)
- [逐题与总体指标](summary.json) · [写作审读及SHA](editor-review.json) · [完整用量审计](audit.json)
- [过度思考原回复](overthinking-native/) · [单次复杂关闭思考控制](thinking-complex/) · [固定512](speed-probes/) · [容量](capacity/)
- [公众号富文本](publication/wechat-richtext.html) · [文章](publication/wechat-article.md) · [B站脚本](publication/bilibili-script.md)
- [成片交付元数据](publication/delivery-metadata.json) · [B站标题、简介与章节](publication/bilibili-release.md) · [镜头表](publication/director-plan.md) · [编码后手机预览](publication/encoded-phone-contact.png)

十类合成工作题，每端16主会话；三个进阶题各三轮，其他单次。写作是代理编辑审读，不是盲审或本人验收。容量每档一组，未测真实仓库修复、生产Agent、并发、512K或全天稳定性。计时不含加载、重启、恢复及人工审读。主测总token不含预检、容量、思考控制与接入检查；全部共同phase40次模型记录/端共80条计时用量另见audit.json，合计1837799token。

不包含API key、内网地址、权重、本人声音参考或配音文件。成片在本地交付，公开仓库保留脚本、数据与制作元数据。

本期成片6分26秒，1280×720/24fps，新生成的本人授权VoxCPM2配音，无背景音乐和音效。17段音频已绑定脚本，做降噪、字幕对齐及编码后关键帧检查；最终AAC为−15.02LUFS、−2.55dBTP。技术检查不代替本人听审。公众号复制按钮完成静态检查，本期未实际粘贴到公众号编辑器。
