# 部署复跑说明

本文件描述评测隔离部署；实际生成的参数与文件身份以environment下的快照为准。原系统服务不永久替换。

## 固定源码与存储

```bash
git clone https://github.com/Niko1221/Strata.git Strata
cd Strata
git checkout fb58e0dbc8399662c0e47c76578c6e878b14f6cf
```

Linux模型根目录用有足够空间的独立磁盘目录，所有TMPDIR/TMP/TEMP、HF_HOME/HF_HUB_CACHE、PIP_CACHE_DIR、UV_CACHE_DIR、XDG_CACHE_HOME显式指向该磁盘。Windows准备权重时这些目录必须在D:\weights；本期没有在Windows下载GGUF。按model-manifest.json下载完整分片，逐个校验完整SHA256。ModelScope同名仓库可作为镜像传输，但仍必须匹配冻结HF revision的哈希。

## HIP引擎

使用ROCm7.2.1、gfx1100。隔离Python3.12 venv，安装固定提交requirements.txt。setup.build_engine_hip({'arch':'gfx1100'}, setup.get_llama_cpp(), 'none')构建engine/strata。官方函数调用cmake时使用16个编译worker；本期外部CMAKE_BUILD_PARALLEL_LEVEL=2没有覆盖它，不宣称只开两线程。

构建选项包括STRATA_ENABLE_HIP=ON、STRATA_ENABLE_CUDA=OFF、STRATA_PREFILL_MMQ=ON、CMAKE_HIP_ARCHITECTURES=gfx1100；llama.cpp固定3cf03257f219afbe7334045ff7c6a06ac68c627d。保留BUILD.json、引擎完整SHA与编译日志。另构建strata-device，单GPU绑定后--selftest实测分配/写入GPU内存。

## 准备各量化

以下为命令模板。GPU编号必须通过strata-device --list-devices核对；不能照抄物理设备号。MODEL_ROOT和STRATA_ROOT由复跑者设置。

```bash
.venv/bin/python setup.py --setup --family qwen --model IQ2_XS \
  --context 262144 --kv int8 --vision none --backend hip --gpu 1 \
  --data-dir "$MODEL_ROOT" --gguf-dir "$MODEL_ROOT/models/strata-iq2" \
  --parallel 1 --host 127.0.0.1 --port 8734 --no-browser --yes --no-start
```

UD-IQ4_XS与UD-Q4_K_XL分别使用--family unsloth及对应--model；分片目录分别是strata-iq4、strata-q4xl。Q4_K_XL为AMD实验路径，显式尝试仅表示本期待验证，不能当作官方已经完成验证。

setup按官方工具准备native pack，Unsloth路径保留--compat-bf16对非专家投影的格式转换及conversions.json；不是重新量化专家。MTP使用原Qwen checkpoint固定de4b8e4d43b917e7706784d8bb445c9af86a3540的31个张量，范围下载且核对每个SHA256；按官方mtp_pack的q2_0与mtp_rt准备，三个量化共用同一MTP及cjk draft vocab。其文件和运行策略不同于Halogen，比较属于完整部署。

## 本期设备绑定和服务

硬件枚举：HIP原始device0为内置gfx1151，device1为外置gfx1100。使用ROCR_VISIBLE_DEVICES=GPU-75071f4312da648c后只剩外置卡并重新编号为0。实际测试配置同时设gpu=0及env中ROCR_VISIBLE_DEVICES为该UUID、HIP_VISIBLE_DEVICES=0。不尝试CPU/APU/eGPU多GPU层切分。

保留setup生成的expert-cache auto、prefill auto、spec4、spec-min-p0.5、MTP、单并发、INT8 KV及自动KV streaming；默认缓存/线程/调度以实际配置和引擎初始化输出为准。effort_position显式start。每个请求明确reasoning_effort=medium（开）或none（关），不依赖模板默认xhigh；旧enable_thinking字段也保留在请求审计中。

用instrument_strata.py为serve/server.py添加opt-in统计字段，STRATA_EVAL_REASONING_USAGE=1时将已有thinking_n透出至usage.completion_tokens_details.reasoning_tokens；telemetry-contract.json验证内容、tool_calls、计时与原字段不变。编译的C++引擎不改，原API源文件另存。若复跑原始未补统计的API，思考token缺失须标未知，不能拿字符数代填。

API只监听127.0.0.1并用STRATA_API_KEY环境变量验证Bearer。测试客户端通过已授权SSH转发到本机访问。原始密钥、SSH信息和私有音色不进此仓库。复跑只需自行设置LOCAL_BASE_URL、LOCAL_API_KEY、LOCAL_MODEL。

```bash
python runner.py --provider local --profile strata-iq2 \
  --study studies/2026-10-09-strata-usb4-7900xtx \
  --suite studies/2026-10-09-strata-usb4-7900xtx/tasks.json \
  --output studies/2026-10-09-strata-usb4-7900xtx/results/strata-iq2 \
  --task D01 --round 1 --thinking on --reasoning-effort medium
```

容量用独立capacity_runner.py（1800秒超时），不使用主runner的240秒截止。原生输入梯度保持262144服务配置；524288是单独YaRN factor2扩展配置。每点先保存空闲内存快照，低于8GiB则停；sample_resources.py每2秒采样一次，记录最小可用内存、引擎RSS、显存和swap差分。大于一次的稳定性结论不在本期容量设计中。

## 测试与恢复

下载/哈希/打包/编译全部暂停或结束后计分；暂停父下载器及所属子进程，并核对进程state为T。运行一个量化时停止原Halogen服务，避免占用内存；始终保持一组模型计分、单请求串行。保留失败首答，不自动修复输出。完成全部候选后终止仅本期Strata实例，启动原Halogen服务，核对原unit哈希、0.9.1健康、空闲和短题响应，保存restored-service.json。原权重保留。
