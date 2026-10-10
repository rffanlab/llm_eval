# 现有服务兼容性与替换

文字计分、容量和运行门槛见summary.json及operational-review.json。正式替换结论见adoption.json。

## 模型身份

正式消费者服务使用同一Gufo0.11.0二进制、UD-Q4_K_XL主权重与shared-Q8_0 MTP，增加BF16视觉投影，并设置默认输出16384。主测显式预算不受该默认值影响。投影来自同一HF revision38bb39ee97821de2c9009abb7e93950eec396e66，907542944字节，SHA256为2e788f8c511d8093c7b43cb87b2fd7e14228340318057f8fb20c86df2efe2355。

此处只测两张公开合成色块的接口契约，没有测完整视觉理解质量。红蓝图、图片SHA、同一提示词和预冻结验收见compatibility-vision-fixtures/。

## 接口差异与处理

Gufo后端健康路由要求鉴权，原Halogen网关后端请求不带鉴权。gateway-adapter.py增加可选MODEL_BACKEND_AUTH_FORWARD=1；复用从环境读取的LLAMA_API_KEY向回环后端鉴权，健康检查使用MODEL_BACKEND_HEALTH_PATH=/ready。不打印、保存或公开密钥。

原网关的模型元数据路由允许公开访问，错误key访问GET /v1/models因此仍得到元数据；真实访问控制使用POST，错误key返回401。原来的六路由记录全部保留，未把这个历史差异改成全部通过。

compatibility/consumer-halogen.json和consumer-preview.json各10项全部通过：无客户端key健康检查、模型与262144容量、两个已有别名、错误key POST、流式OK及DONE/usage、严格schema、Responses、红蓝两张图片。

## 第一次正式接入失败

依赖列表无法用drop-in空值删除。第一次切换断言发现Wants同时含旧Halogen和Gufo，停在网关重启前；网关仍指向已停止的旧后端。失败记录保留在consumer-final.json及service-tools-final/，属于接入故障，未改写主测答案。

随后保存并修改完整网关单元，将旧Halogen依赖改为Gufo；保留API转发drop-in。依据是[systemd官方单元文档](https://github.com/systemd/systemd/blob/main/man/systemd.unit.xml)的依赖覆盖说明。原机器已有固定7.0.0-31内核配置保持不变，删除了本期重复的内核默认配置。

修正后compatibility/consumer-final-r2.json为10/10，service-tools-final-r2/的冻结A01/A02两类工具流程通过。原有地址、key、模型ID和两个别名保留，正式Gufo启用，Halogen禁用；网关只依赖Gufo。Gufo单元设置Conflicts=ai-llm-halogen.service并在加载前检查单模型与资源释放。

## 回滚

原Halogen单元内容未修改，原网关完整片段有备份。本机回滚入口与最终单模型快照见adoption.json。服务回滚先停止Gufo，确认内存释放，再恢复原网关和Halogen开机状态。116GiB启动上限是已批准的独立配置；恢复启动内存参数需单独重启，不伪称服务回滚已经复原内核环境。

本期核验加载、请求、自启动依赖与enablement，未再次重启做完整开机演练，不声称长期稳定性已验证。
