# 声间工作室

Python/FastAPI 提供 API 和 React 的生产静态文件，同一端口、同源鉴权。部署后不需要 Node 服务、不需要额外 Nginx。Docker 在 Node 构建阶段生成前端，再复制到 Python 镜像和 wheel 中。

## 开发与本地启动

需要 Node 22.12+（推荐 Node 22 LTS）和项目 Python 环境。

```bash
npm ci --prefix frontend
npm run build --prefix frontend
python scripts/configure.py
# GPU 环境已经按 bootstrap_colab.sh 安装好后：
bash scripts/start_studio.sh gpu
```

`start_studio.sh` 只监听 `127.0.0.1:8000`，读取本地 `.env` 而不输出密钥。CPU 模式传 `cpu`；自定义配置用 `SPEECH_CONFIG=/absolute/path/config.yaml`。若没有构建前端，它会构建一次。之后改 React 源码需重新 `npm run build --prefix frontend`。

开发热更新：Python 保持 8000 端口，另开终端 `npm run dev --prefix frontend`，打开 `http://127.0.0.1:5173/studio/`。Vite 把 `/v1` 和 `/health` 代理到 Python；这个开发服务不用于公网部署。生产构建不依赖 CDN。

在 Colab 单元格里可以用 `subprocess.Popen` 在后台启动脚本，stdout/stderr 写到私有日志文件。随后将自己的 CF Tunnel 源站设为同一个运行时的 `http://127.0.0.1:8000`。不要把运行时 localhost 误当成个人电脑的 localhost；远程浏览器通过 HTTPS 域名访问，以使用浏览器音频和剪贴板 API。

## 从录音到音色

1. 在页面输入 `.env` 中 `SPEECH_API_KEYS` 的 owner 值。密钥不会写入 localStorage、sessionStorage、URL 或音色导出。
2. 添加参考音色，上传 3–30 秒清晰单人录音；原文可以自动识别后校对。参考录音只用于零样本克隆，不改变权重。
3. 选中音色，输入要读的文字，点击「生成并试听」。响应到达时就分块播放；完整接收后才开放 WAV 下载。停止未完成的生成不会输出假装完整的 WAV。
4. 需要微调时，在素材页上传多个 1–30 秒的片段并填写逐字原文。浏览器支持其自身可解码的音频格式；不支持的格式会明确报错。每批最多 50 段，每文件大小按服务配置限制。
5. 选中至少 5 段互不重复的素材，再到训练页选择参考音色和参数。真实任务阶段来自服务端，页面每 5 秒查询；切换页面不影响服务器训练，关闭浏览器也不会取消服务器任务。
6. 成功任务可以选择新音色并试听。导出 JSON 是当前服务中的 voice_id 配置；权重保存和私有 Hugging Face 上传见 [training.md](training.md)。

## 开启训练

默认推理模式 `training.enabled: false`。单张 T4 可以停止当前 studio 进程，再切换到训练模式：

```bash
DS_BUILD_OPS=0 uv pip install --python .venv/bin/python deepspeed==0.15.1
bash scripts/start_studio.sh train
```

训练模式沿用 GPU 配置和数据目录，生成临时配置，开启管理 API 与独立 worker，禁用 API 的 ASR/TTS/翻译模型。浏览器仍可上传、手动标注、提交/取消训练和查看结果；不能自动转写或试听。训练完成后，停止该进程并运行 `bash scripts/start_studio.sh gpu`，再连接页面试听新版本。启动脚本不会覆盖自己的配置，也不会自动杀死占用 8000 端口的旧服务。

这避免同一工作室的训练与推理争抢显存；同一 GPU 上的其他 notebook / 外部进程仍需自己停止。单张 T4 不保证容纳完整 LLM SFT；没有实际个人数据训练成功前，不把参考音色或接口成功称为已训练权重。

有独立训练 GPU 时，可以在自己的 GPU 配置中设 `training.enabled: true`，API 与 `speech-worker` 使用相同密钥和数据目录，按 [training.md](training.md) 独立启动。

## 数据边界

用户数据在配置的 `data_dir` 中，静态文件路由只挂载前端构建目录。素材音频下载、音色、训练任务都校验当前身份；不同身份互不可见。断开连接会中断本页请求、停止播放、清空文本/草稿/结果和 Blob URL。已上传到服务器的数据保留。Colab 临时磁盘需由自己备份，网页上传不等于持久备份。

## 验证

```bash
npm ci --prefix frontend && npm run build --prefix frontend
.venv/bin/pytest -q
npm test --prefix frontend
# 安装浏览器测试依赖（不影响生产）：
npm install --prefix frontend --no-save playwright
npx --prefix frontend playwright install chromium
PLAYWRIGHT_MODULE="$PWD/frontend/node_modules/playwright" node tests/studio-browser.mjs
```

浏览器测试会自行启动仅绑定 localhost 的 Python 测试服务，用临时目录和合成音频覆盖登录、流式播放、上传/转写、素材选择、训练提交/取消/结果选择、手机布局和退出清理。它不是实际 GPU 训练或音质验收。`CHROMIUM_PATH` 可指定已有 Chromium，`STUDIO_TEST_URL` 可指向手动启动的同一测试夹具。
