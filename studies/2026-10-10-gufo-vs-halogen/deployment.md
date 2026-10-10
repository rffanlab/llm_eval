# 部署身份与复跑条件

本期 Linux 主线 Gufo0.11.0，Git提交 `2a3b09e187208c3895eee7391ca0a6a3179a2efc`，未改上游源码。Windows分支存在，但本期不测Windows。

## 环境

Ryzen AI Max+395、128GB、内置Radeon8060S gfx1151、Ubuntu24.04.5、ROCm7.2.1、GCC13、CMake3.28.3、Ninja1.11.1。USB4外卡保持接入，但本期修正后的共同启动未枚举出7900XTX，实际计算与资源记录只有8060S。上游合格工具链GCC15.3/ROCm7.2.3与实际环境不同，未升级驱动。编译为官方release preset；仅安装两个缺失的开发包。

首次加载在原62.47GiB GPU分配上限失败，尚未推理。批准修改并重启后，ttm.pages_limit=30408704（116GiB）；主内存实际约124.93GiB，上限不提前分配内存。保留同一7.0.0-31-generic内核；page_pool_size未提高。两端最终统计只用phase-freeze.json中这一共同启动，原始失败与旧启动Halogen数据另外保留。

## 权重

Unsloth/Qwen3.8-Flash-Next-GGUF，revision `38bb39ee97821de2c9009abb7e93950eec396e66`。UD-Q4_K_XL四分片111,334,654,784字节，复用既有原始GGUF，不用Strata转换包。shared-Q8_0 MTP辅助2,786,568,256字节。逐文件完整SHA见environment中的candidate_preparation。

## 启动模板

先停前一推理服务，确认无模型进程、MemAvailable>=100GiB、两GPU旧VRAM<2GiB/GTT<4GiB。以下路径和API密钥变量由操作者配置：

```bash
git checkout 2a3b09e187208c3895eee7391ca0a6a3179a2efc
cmake --preset release
cmake --build --preset release --target gufo --parallel 8
ROCR_VISIBLE_DEVICES=0 HIP_VISIBLE_DEVICES=0 \
GPU_MAX_ALLOC_PERCENT=100 GPU_SINGLE_ALLOC_PERCENT=100 build/release/gufo serve \
  --host 127.0.0.1 --port 8735 --sessions 1 --api-key "$LOCAL_API_KEY" \
  llm --model "$Q4_FIRST_SHARD" --served-model-name Qwen/Qwen3.8-Flash-Next \
  --speculative mtp --mtp-model "$MTP_SHARED_Q8" --context 262144 \
  --reasoning-effort medium --preserve-thinking off --cache-ram-bytes 1073741824
```

GPU索引需先核对物理PCI与gfx1151，不按其它机器编号照搬。请求前再确认单模型、ready与可用内存>=8GiB。RAM快照事前设1GiB，未开磁盘快照；大前缀是否命中以实际cache_n为准。

Halogen对照保留原0.9.1/HGN W4B+overlay、MTP、262144上下文、110MB缓存。两者量化/MTP/实现不同，是部署交付对照，无法据此证明原BF16数值精度。

正式消费者部署在文字测试身份上增加同一HF固定版本的BF16视觉投影与16384默认输出上限；主测均显式提供预算，未改其计分记录。实际原网关、模型别名、鉴权、图片与工具检查见consumer-api.md。保留原Halogen及网关完整配置，可回滚服务；本期没有再次重启验证自启动，也没有测试全天稳定性。

## 资料

- https://github.com/gufo-org/gufo/tree/2a3b09e187208c3895eee7391ca0a6a3179a2efc
- https://github.com/gufo-org/gufo/blob/2a3b09e187208c3895eee7391ca0a6a3179a2efc/docs/models/qwen3.8-flash-next/README.md
- https://github.com/pixmaate/gufo
