# 部署、权重与计时口径

## 本机实测环境

Ryzen AI Max+395、128GB统一内存、Radeon8060S / gfx1151，Ubuntu24.04.5、ROCm7.2.1、内核7.0.0-31-generic。TTM pages_limit=30408704，即116GiB。USB4保持连接，测量期间只枚举到8060S；7900XTX未参与。

Gufo0.11.0固定源码提交 `2a3b09e187208c3895eee7391ca0a6a3179a2efc`，GCC13、CMake3.28.3、Ninja1.11.1，采用现有release二进制，未在中途编译或升级。二进制SHA256：

`23be7b09b7f004c62768dcda6406b18971e18bb42b4563faf3cb76d1cc9bb9d2`

本机工具链与上游文档的GCC15.3/ROCm7.2.3不同，因此文章使用本机新测结果。上游速度不作为本次实测。

[本次Gufo源码](https://github.com/gufo-org/gufo/tree/2a3b09e187208c3895eee7391ca0a6a3179a2efc) · [27B部署文档](https://github.com/gufo-org/gufo/blob/2a3b09e187208c3895eee7391ca0a6a3179a2efc/docs/models/qwen3.8-27b/README.md)。

## 权重身份

| 部署 | 来源与revision | 文件 | 实际字节数 | SHA256 |
|---|---|---|---:|---|
| 27B主模型 | [Unsloth](https://huggingface.co/unsloth/Qwen3.8-27B-GGUF/tree/4ca720788d1e01f1bff70c033e0d0028fd02e502) | Qwen3.8-27B-UD-Q4_K_XL.gguf | 17559178144 | 3f227079003add2511437e5b1e94812e363385225bf6a9b47b0054a72bc8b01e |
| DFlash2辅助 | [z-lab](https://huggingface.co/z-lab/Qwen3.8-27B-DFlash2-GGUF/tree/2d9571f8ce46e151f61c6499c99dee6079e1d610) | Qwen3.8-27B-DFlash2-Q4_K_M.gguf | 1143006816 | 1a25c56858e1ebe93f2718ac1d49d1151f9323325c1bbfd6209370f4db131ebd |
| Next Flash主模型 | [Unsloth](https://huggingface.co/unsloth/Qwen3.8-Flash-Next-GGUF/tree/38bb39ee97821de2c9009abb7e93950eec396e66) | UD-Q4_K_XL，4个分片 | 合计111334654784 | 各分片见 environment/engine-and-next-weight-identity.json |
| MTP辅助 | 复用前一期已校验文件 | mtp-Qwen3.8-Flash-Next-shared-Q8_0.gguf | 2786568256 | 见同一身份文件 |

27B主文件与辅助文件均在Windows下载端和Linux运行端做完整SHA校验。上游历史加载日志的字节数可能是映射页统计，本表采用仓库文件大小与全文件校验。Windows大文件、缓存和临时目录全部在D盘；Linux权重使用现有模型卷。没有删除生产Next Flash权重。

## 启动参数示例

把占位路径改为自己的已校验文件；密钥只从环境注入，不提交配置或命令历史。

```bash
gufo serve --host 127.0.0.1 --port 8736 --sessions 1 \
  --api-key "$LOCAL_API_KEY" llm \
  --model /MODEL_VOLUME/Qwen3.8-27B-UD-Q4_K_XL.gguf \
  --speculative dflash2 \
  --dflash-model /MODEL_VOLUME/Qwen3.8-27B-DFlash2-Q4_K_M.gguf \
  --served-model-name Qwen/Qwen3.8-27B \
  --context 262144 --reasoning-effort medium --preserve-thinking off \
  --cache-ram-bytes 1073741824 --max-tokens 16384
```

AR对照删除 `--speculative dflash2` 和 `--dflash-model` 两项，其他参数相同。Next Flash替换主权重为第一分片、辅助模式为 `--speculative mtp --mtp-model ...`、served-model-name为 `Qwen/Qwen3.8-Flash-Next`。主测各请求仍采用题目自己的2048—8192输出预算，服务器16384只是上限。

## 测量与复跑

- API完整等待与引擎队列、prefill、decode、TTFT分别存档；缓存恢复和快照可能是嵌套工作，不能机械相加。
- 流式文件保留首SSE、首非空片段、首思考、首正文及完整流结束。关闭思考时首思考为空，表示未观察到，不补0。
- 新前缀与准确重复请求相邻执行。只有原生cache_tokens/cache_hit才能证明命中；长快照超过1GiB会跳过。
- Agent是模拟工具会话，完整等待含各次API及模拟工具处理。逐轮TTFT不求和为一个首字时间。
- 加载为发起服务到认证就绪，每部署一次；未控制文件页缓存，不称冷启动。下载和传输时间另记，早期未记录的网络耗时为未知。
- 原始答题失败不修复、不覆盖。W01关闭思考为观察失败后登记的单次诊断，不替换主测分数。
- 复跑请复制本study到新目录，清空该副本的结果目录，再遵照 tasks-and-reproduction.md；原档案不可覆盖。

公开档案不包含内网地址、API密钥、原始私人音色、权重、视频与音频大文件。
