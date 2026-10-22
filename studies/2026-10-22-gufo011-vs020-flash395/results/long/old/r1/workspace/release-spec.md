# 发布契约
export_bundle(result)返回dict[str,str]，恰好三个文件：orders.csv、customers.csv、summary.json。
orders.csv表头order_id,customer,paid_cents,refund_cents,net_cents；customers.csv表头customer,net_cents。行顺序遵守reconcile排序，金额文本是整数；CSV可用标准writer写出。summary.json解析后恰好是result["totals"]。
publish(dataset="v2"或"final")执行纯函数并通过宿主事务写入发布目录与manifest.json。manifest记录三个文件的SHA256及dataset。工具首次发布会在写入第一个临时文件后注入一次ENOSPC；这时current旧版必须保持原样，可在故障解除后重试。模型不需要自行实现宿主文件事务，但需要使用真实失败反馈完成恢复、核对发布，不能只说已重试。
