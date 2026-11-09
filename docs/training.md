# 音色训练

先通过 `/v1/voices` 注册参考音频，即可尝试零样本克隆。只有需要基于多段录音微调时才启动训练。两者在接口中分别标记 `kind=zero_shot` / `kind=finetuned`，不混淆“音色特征”和“训练权重”。

## 提交

1. 将本人或已获授权的单人干净音频切成 1–30 秒 WAV/FLAC，每段附准确 transcript。至少 5 段互不重复的录音；训练/验证集确定性划分，重复音频会拒绝。片段数量下限不代表足够训练出高质量音色。
2. 对每段调用 `POST /v1/training/samples`，multipart 字段 `file`、`transcript`、`consent=true`，保存返回的 sample id。
3. 设置 `training.enabled: true` 并启动独立 `speech-worker`。训练依赖还需 `DS_BUILD_OPS=0 pip install deepspeed==0.15.1`。不要同时让推理占满同一 GPU。
4. 提交任务：

```http
POST /v1/voice-training/jobs
Authorization: Bearer <key>
Content-Type: application/json

{"voice_id":"reference-voice-id","sample_ids":["id1","id2","id3","id4","id5"],"epochs":1,"learning_rate":0.00001}
```

5. `GET /v1/voice-training/jobs/<job_id>` 查询 `status`、`stage` 和错误信息。`POST .../<job_id>/cancel` 请求取消。worker 在阶段内每秒检查，结束整个训练子进程组。

状态为 `queued → running → succeeded/failed/cancelled`；worker 重启后遗留 running 任务标为 interrupted，不假装继续完成。当前没有自动恢复优化器状态；重试需新建任务。检查点和日志保留在 `data/jobs/<id>/`，需要自己的备份/清理策略。

## 训练过程

锁定的 CosyVoice3 官方脚本生成说话人 embedding、离散 token、Parquet 数据；`torchrun --nproc_per_node=1` 训练 LLM。每个 epoch 有独立验证集损失和检查点。训练 YAML 由服务基于固定模板生成，仅暴露 epoch 和学习率等受限参数，客户端不能执行任意命令。

输出从训练检查点去掉 `epoch`/`step` 元数据，再以 `llm.pt` 覆盖新版本目录中的 LLM，复用相同 revision 的 flow/hift/前端。原始基座保持不变。任务返回新的 output_voice_id。参考音频仍被保留，供零样本提示和对比使用。

“训练任务成功”仅表示 recipe 完成且导出检查点；应另行验收音色相似度、发音、背景噪声、稳定性和实时速度。当前仓库还没有 GPU 训练成功的实际记录，不能宣称 T4 一定够用，也没有替你训练出个人音色（尚未收到你的录音）。

## 存入 Hugging Face

在 Colab Secrets 中保存自己的 `HF_TOKEN`，仅在内存里读取：

```python
import os
from google.colab import userdata
os.environ['HF_TOKEN'] = userdata.get('HF_TOKEN')
```

然后执行：

```bash
.venv/bin/python scripts/upload_weights.py \
  --job-dir data/jobs/<job-id> \
  --repo yuebanlaosiji/my-voice-v1
```

上传器会创建/检查私有模型仓库，只上传 `llm.pt` 和训练清单，不上传原始音频、transcript 或访问令牌。清单含 sample ID 和基座 revision。基座本身保留在官方 HF 仓库，不为每个音色重复存储整套模型。

推理服务器部署时先下载记录的基座，再将自己的 `llm.pt` 放到新的模型目录，配置该目录或迁移对应 voice/job 数据。只加载你信任的模型仓库和检查点。服务器用户数据、参考音频以及 catalog.sqlite3 也要一起备份；仅有权重不包含 voice_id 目录记录。
