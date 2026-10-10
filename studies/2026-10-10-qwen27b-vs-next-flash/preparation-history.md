# 权重准备：过程与计时

最终两份权重已在Windows和Linux端完成全文件SHA256校验，并用于本期实测。以下保留原始网络失败与处理过程。

395直连Hugging Face停在连接阶段，尚未创建权重文件。本次独立下载任务已停止，改从Windows的D盘指定模型目录下载、完整SHA校验后传输到395已有模型盘，再作完整SHA核验。下载、校验与传输均不计入模型推理时间。

DFlash2首次Windows传输未达到预期字节数，保留.partial并按HTTP Range续传，最终完整SHA验证通过；没有将网络失败计为模型失败。

Linux端主模型传输加完整SHA校验686.54秒，DFlash2为46.09秒。Windows末次记录中，主文件已经下载完成，18.33秒为SHA校验；DFlash2断点续传加校验56.91秒。初始下载耗时未完整记录，不能把末次记录当成全部下载时间。见[Windows计时及边界](preparation-windows.json)与[Linux计时](preparation-remote.json)。
