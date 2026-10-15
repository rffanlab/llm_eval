# Qwen3.8 Next Flash：GSQ与Unsloth三档量化实测结果

- [公众号正文](publication/02-wechat-article.md)
- [可复制标题与富文本的HTML](publication/03-wechat-richtext.html)
- [B站视频](publication/video.mp4) · [视频旁白全文](publication/video-script.md)
- [逐题、逐阶段原始行表](measurements.csv) · [汇总](summary.json)
- [题目、工具、预算和验收](protocol.md) · [完整提示词](tasks.json)
- [协议缓存单位更正](reporting-clarifications.md) · [实际分配](runtime-allocations.json)
- [原始文件摘要](raw-manifest.json) · [最终文件补充核对](final-release-audit.json)

性能以原生新输入和生成计数分别除以对应计算时间，再跨轮取中位。缓存复用另列，完整等待包含API和工具。未知保持未知；截断的实际生成量另列，不算成功交付。写作编辑评分由主代理完成，未盲审；题目范围和失败均见正文。
