# 手工复跑

## 模型和环境

从`candidates.json`所列固定revision下载所选完整GGUF分片，保留原名。共同对照使用`deployment-freeze.json`所列引擎与参数，替换引擎、GGUF首分片和聊天模板三个占位路径；同一次五方对照不要混用引擎。下载和哈希校验完成后再计时。

共同引擎不启用MTP。Strata另建对应模型的pack，不能替换GGUF路径却沿用别的模型pack；具体版本与参数见部署冻结文件。先停止上一模型，确认主存、VRAM/GTT释放，再启动下一模型。本文不自动修改正在使用的模型服务。

## 注册条件

服务单会话绑定本地回环地址。将以下占位替换为真实PID和目录；Strata有前端、引擎两个PID，应一并传入。注册时会完整检查权重SHA256，需要等待；条件文件只留在本次运行目录。

```sh
python3 admission_guard.py register --registration condition-private.json \
  --pid ENGINE_PID --candidate gsq-iq3s --model-dir MODEL_DIRECTORY
export EVAL_GUARD_COMMAND='["python3","admission_guard.py","verify","--registration","condition-private.json"]'
export EVAL_BASE_URL='http://127.0.0.1:8763/v1'
export EVAL_API_KEY=''
export EVAL_MODEL='Qwen/Qwen3.8-Flash-Next'
export EVAL_PROFILE='common-gsq-iq3s'
export PYTHONPATH="$PWD"
```

已有服务有鉴权时从私密环境设置EVAL_API_KEY，不将密钥写入题库或结果。新建回环评测服务无需添加鉴权。不得让下载、哈希校验或其他模型和正式请求争用资源。

## 请求与验收

每个输出目录必须为空；脚本拒绝覆盖已有尝试。失败记录保留，恢复另记。

```sh
python3 short_runner.py --provider local --task C01 --round 1 --output results/short
python3 long-horizon/runner.py --provider local --profile common-gsq-iq3s --round 1 --output results/long
python3 long-context/runner.py --provider local --task LC01 --round 1 --output results/context
python3 speed_runner.py --profile common-gsq-iq3s --kind prompt32k --round 1 --output results/speed
```

七道短题各两轮；D01的`--variant depth`另跑两轮；长程和LC01各两轮；三个吞吐探针各三轮。写作及交付说明另按协议量表审读，自动格式或关键词通过不能代替编辑审读。

原生速度按`native-timing-contract.json`聚合。该版llama.cpp的第一个生成token来自最后一次Prefill logits，因此原生Decode步数为`predicted_n-1`；保留原始输出token和计数字段，不能用墙钟反推原生速度。
