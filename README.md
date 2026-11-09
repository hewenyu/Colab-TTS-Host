# Colab-TTS-Host

可配置的语音服务平台：**ASR、文本翻译、TTS、音色克隆与训练、流式同声传译**。**Python/FastAPI 后端 + React 前端**；代码在 GitHub，Colab 用于开发和模型实验，Docker 用于独立服务器部署。内置「声间」工作室，浏览器上传录音、标注素材、管理训练并试听所选音色，原有独立 API 继续可用。

## 已实现与边界

| 能力 | 实现方式 |
| --- | --- |
| 独立语音识别 | Paraformer 在线模型；文件上传和 WebSocket，当前适配器支持中文 |
| 独立文本翻译 | 本地 Transformers 或 OpenAI-compatible chat/completions 服务 |
| 独立 TTS | CosyVoice3；HTTP 音频流和 WebSocket 文本输入/音频输出双向流 |
| 同声传译 | 在线 ASR → 句子确认 → 翻译 → CosyVoice3 原生流式音频 |
| 上传音色 | 3–30 秒参考录音和准确文本；返回独立 voice_id，直接做零样本克隆 |
| 训练音色 | 上传标注音频 → 持久化异步任务 → 官方 CosyVoice3 LLM SFT → 新版本 voice_id |
| 权重存储 | 固定基座 revision；训练产物可单独上传至私有 Hugging Face 模型仓库 |
| 部署 | CPU / NVIDIA GPU Docker Compose，模型和用户数据使用持久卷 |

这是首个开发版本。训练代码已接入官方 recipe，但 **GPU 训练、训练后音质以及 Docker 镜像构建仍需在对应环境验收**。测试证据见 [docs/validation.md](docs/validation.md)，不把协议测试的替身模型算作真实推理。

已在用户提供的 Colab T4 上通过真实 ASR、翻译、双向 TTS 和组合同传验收，19 项协议测试通过。一次预热 TTS 测得首包 3.28 秒、RTF 1.24；功能通过，但仍需优化才能承诺持续实时输出。首次加载耗时另计，不把冷启动和预热数据混用。

默认本地翻译模型 Qwen2.5-0.5B 用于低资源功能验证，翻译质量需要另行评测。可换更大且兼容的指令模型，或接你的现有模型网关。当前 ASR 适配器是中文模型；英语音频输入需要添加多语言 ASR 适配器，不能只改语言参数。

同声传译以语句为提交单位：临时识别可以变化，已经确认的句子才会被翻译和朗读。默认用简单能量阈值静音检测和 15 秒上限断句；这是可用的基线，不等于专门训练的 VAD。客户端可主动发送 `input.commit`。不承诺零延迟，不会把整段语音合成完再伪装为流式。

## 一键部署

首版目标：Linux **amd64**。GPU 模式另需兼容 CUDA 12.1 的 NVIDIA 驱动、NVIDIA Container Toolkit 和支持 `gpus` 的 Docker Compose。CPU 模式用于开发/验收；不保证实时速度。ARM/macOS 原生推理还未验证。

```bash
git clone https://github.com/hewenyu/Colab-TTS-Host.git
cd Colab-TTS-Host
bash scripts/deploy.sh gpu
# 无 GPU：bash scripts/deploy.sh cpu
```

脚本生成权限为 `0600` 的 `.env`，其中 `SPEECH_API_KEYS` 保存客户端密钥。首次构建会安装模型依赖，首次启动会下载 `models.lock.json` 指定的模型，需网络和充足磁盘。权重不进入 Git 或镜像层。默认只监听宿主机 `127.0.0.1:8000`；远程客户端应通过 HTTPS/WSS 反向代理接入。API 文档 `/docs`，存活探针 `/health/live`，模型配置能力 `/v1/capabilities`。

如果只接远程翻译服务/只启用部分功能，把对应 backend 改为 `disabled`，将 `.env` 中 `DOWNLOAD_MODELS=0`，自行提供所需的模型目录。`health/live` 只表示进程存活，模型按需加载，不能当作模型已加载的证明。

不要在 GPU 单卡上同时跑训练和推理，二者会争抢显存。Compose 的 `training` profile 默认不启动。启用训练前先准备模型和数据、在配置里设 `training.enabled: true`，随后用独立 GPU/独立运行时启动 `speech-worker`。

## 可视化工作室

部署后打开 `http://127.0.0.1:8000/`，输入 `.env` 里的 owner API Key。Colab 中的 localhost 属于 **Colab 运行时**；使用自己的 CF Tunnel 时，将源站指向同一运行时的 `http://127.0.0.1:8000`，浏览器打开对应的 HTTPS 域名。

- **音色工作室**：上传 3–30 秒参考录音，自动识别并校对原文，创建音色；选中音色后流式生成与播放，下载 WAV 或导出音色配置。
- **训练素材**：拖入多个 1–30 秒片段、编辑逐段原文、保存并选择训练集。浏览器在上传前转换为 16 kHz 单声道 WAV。
- **训练任务**：选择音色、轮数与学习率，查看实际任务阶段、取消任务，完成后选择新版本试听。需要启用训练并另起 worker；没有 worker 时不会虚构进度。

音频与权重在 `data/`、`models/` 中，不进入 Git，也不会随 React 打包。API Key 仅保留在页面内存；刷新后重新连接。音色 JSON 导出包含 ID 和版本，**不包含权重**。完整使用与 React 开发说明见 [docs/studio.md](docs/studio.md)。

## 自定义模型

编辑 `config/server.yaml`（CPU）或 `config/gpu.yaml`（GPU），通过 `CONFIG_FILE` 也可以挂载自己的配置：

```yaml
asr:
  backend: paraformer
  model: /app/models/asr
  device: cuda
tts:
  backend: cosyvoice3
  device: cuda
  source_dir: /app/vendor/CosyVoice
  model_dir: /app/models/cosyvoice3
  revision: 29e01c4e8d000f4bcd70751be16fa94bf3d85a18
  fp16: true
translation:
  backend: openai
  model: your-translation-model
  base_url: https://your-gateway.example/v1
  api_key_env: TRANSLATION_API_KEY
```

远程翻译密钥通过环境变量提供（Compose 中也要显式传入该变量）。模型名称、目录、设备和 revision 均由服务管理员配置；API 客户端不能上传可执行 Python/YAML 或选择任意服务器路径。不同架构的 ASR/TTS 模型需要实现适配器，目前注册表只包含已写好的类型，错误类型在启动时失败。

`SPEECH_API_KEYS` 是 JSON，如 `{"alice":"至少24字符的随机密钥","bob":"另一个随机密钥"}`。音色、训练数据与任务按身份隔离。默认不允许无密钥启动；只有显式 `development: true` 才允许本地开发免鉴权。不要将这个选项用于公网部署。

## 独立 HTTP API

所有 `/v1/*` 请求均使用 `Authorization: Bearer <key>`。

```bash
# 在自己的终端中设置 API_KEY；不要将密钥提交到仓库
curl -H "Authorization: Bearer $API_KEY" \
  -F file=@speech.wav http://127.0.0.1:8000/v1/asr/transcriptions

curl -H "Authorization: Bearer $API_KEY" -H 'Content-Type: application/json' \
  -d '{"text":"你好，世界","source_language":"zh","target_language":"en"}' \
  http://127.0.0.1:8000/v1/translations

curl -H "Authorization: Bearer $API_KEY" -F file=@my-voice.wav \
  -F 'transcript=录音中逐字准确的内容' -F name=my-voice -F consent=true \
  http://127.0.0.1:8000/v1/voices

# 把返回的 voice id 填入请求；stream=false 返回完整 WAV
curl -H "Authorization: Bearer $API_KEY" -H 'Content-Type: application/json' \
  -d '{"text":"你好，欢迎使用语音服务。","voice_id":"返回的ID","stream":false}' \
  http://127.0.0.1:8000/v1/tts/speech -o result.wav
```

TTS 默认 `stream=true` 返回 PCM16 原始音频流，采样率见 `X-Sample-Rate`，单声道见 `X-Audio-Channels`。HTTP 中途断流意味着本次响应不完整，应由客户端丢弃或标记，不能当作完整 WAV。输入文件为 WAV/FLAC；普通 ASR 最长 120 秒。上传样本的 transcript 必须与录音对应。零样本克隆不改变模型权重。

## 双向流式

统一入口 `/v1/stream`；也有 `/v1/asr/stream`、`/v1/tts/stream`、`/v1/interpret/stream`。完整协议和异步客户端示例见 [docs/protocol.md](docs/protocol.md)、[scripts/client_stream.py](scripts/client_stream.py)。

- `mode=asr`：音频 → 临时/最终识别文字。
- `mode=translate`：音频 → 识别和翻译字幕。
- `mode=interpret`：音频 → 识别、翻译和目标语音。
- `mode=tts`：逐步输入文字 → 逐块返回语音。

接收、识别、后续合成、发送各自独立工作，队列有上限。输入过快返回 `input_overflow` 并关闭会话，不会无限累积内存。TTS 模型按单任务串行使用；客户端连接数量不等于 GPU 推理并发数。`input.end` 会排空剩余输出；`session.cancel` 或断线会取消本次任务。CosyVoice 取消时重启其子进程，下一次需要重新加载模型。

首版不支持断线续传，也不会自动重播旧音频；重连建立新会话，客户端负责去重。没有音频抢话/自动打断逻辑，不会因下一块输入音频到达而取消当前翻译。

## 在 Colab 开发

使用 [notebooks/develop.ipynb](notebooks/develop.ipynb)，或在已连接的 Colab MCP session 中执行相同步骤：

```bash
bash scripts/bootstrap_colab.sh cpu # GPU 运行时改为 gpu
npm ci --prefix frontend
npm run build --prefix frontend
.venv/bin/pytest -q
.venv/bin/python scripts/smoke_models.py --config config/server.yaml
```

脚本建立隔离的 Python 3.10 环境，不覆盖 Colab 自带 Python。真实模型验收仅监听 `127.0.0.1`，使用上游公开样本，不创建公网隧道、不运行保活绕过程序。免费 GPU 配额和运行时可用性由 Colab 决定；Google Cloud 赠金不应视为 Colab GPU 已分配。

Colab 磁盘会丢失。代码及时推回 GitHub；训练后显式运行上传脚本。ChatGPT 连接器里的 Hugging Face 授权不会自动变成 Python 进程中的 `HF_TOKEN`，请通过 Colab Secrets 或自己的安全环境变量提供令牌，不要粘贴到代码单元/日志中。

## 训练与 Hugging Face

详见 [docs/training.md](docs/training.md)。训练使用有授权的、同一个说话人的干净录音和准确标注，至少 5 个不重复片段才能建立独立验证集。5 个片段只是接口下限，不能保证声音质量；实际应准备覆盖日常表达的更多录音并听测验证。

训练产物不会覆盖基座或原 voice_id。任务成功后返回新的 `output_voice_id`；原音色仍可用于对比。当前训练范围是 CosyVoice3 的 **LLM SFT**，不是 LoRA，也不是整套声码器训练。代码遵循锁定版本的官方 recipe，尚无本项目的 GPU 训练成功记录。

## 运行和维护

默认单 API 进程 + 单训练 worker，SQLite WAL 持久化任务。不要把同一个数据卷挂到多台机器，不要启动多个 Uvicorn workers。要横向扩展时，需将任务目录、队列、数据库和模型执行器改为独立服务。

限制包括上传大小、时长、文本长度、空闲超时、会话上限和有界队列。ASR/翻译的线程调用采用有界输入和输出；超时后底层当前算子可能继续到返回。CosyVoice 使用进程级终止，可以回收上游后台线程。应用日志/数据卷含用户数据，宿主机需控制访问与备份期限。

测试：先 `npm ci --prefix frontend && npm run build --prefix frontend`，再 `pip install -e '.[test]' && pytest -q`；音频单元测试 `npm test --prefix frontend`；真实模型测试需要另外安装模型依赖。`scripts/smoke_models.py` 不训练声音、不需要用户音频。项目代码采用 MIT；基础模型和第三方源代码分别遵循其原有许可证。
