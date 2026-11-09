# 验收记录

日期：2026-11-09。实现分支 `feat/streaming-speech-server`。原始结果：[t4-smoke.json](t4-smoke.json)。

## 自动化测试

本地 Python 3.12 和 Colab Python 3.10：各 19 项测试通过。覆盖 HTTP/WS 鉴权、音色跨身份隔离、未配置后端、ASR cache 隔离、PCM 格式校验、排空顺序、TTS 输入结束前输出、取消关闭生成器及实际子进程回收、有界队列溢出、实际 chunked body 大小限制、音频时长/重采样、持久化任务原子领取及重复音频检测。

这些单元测试使用注入的测试替身验证服务协议，不代表模型质量或速度。配置、notebook JSON、Python 编译和 shell 语法检查通过。

## Colab 真实模型验收

最初通过 MCP 创建 T4 返回 `INVALID_ARGUMENT / Precondition check failed`，因此先用 CPU 调通 ASR 和翻译。随后用户手动申请的 T4 已被 MCP 发现并成功使用，`nvidia-smi` 确认 Tesla T4、15360 MiB 显存。未申请付费资源或升级账号。CPU 测试在切换 T4 时主动终止，不计为完整链路通过。

T4 使用隔离的 Python 3.10.22、torch 2.3.1+cu121。模型 revision 与 CosyVoice 源码版本全部记录在 [models.lock.json](../models.lock.json)。ASR 的 ModelScope 下载在该运行时速度过慢，最终切换 FunASR 官方 Hugging Face 仓库，锁定 commit；三个模型都已下载成功。

通过真实 HTTP / WebSocket 访问 localhost Uvicorn 服务，无模型替身。输入为 CosyVoice 上游公开的 3.48 秒参考音频，不是用户录音，不涉及训练。完整脚本退出码 0。

| 项目 | 结果 |
| --- | --- |
| HTTP ASR | “希望你以后能够做的比我还好哟” |
| WebSocket ASR | 4 次临时结果，最终文本与 HTTP 一致 |
| 翻译 | “Hope you can do even better than me in the future.” |
| 双向 TTS 冷请求 | 在 input.end 之前返回音频；5 个分块；首包 52.38 秒，包含模型加载 |
| 双向 TTS 预热请求 | 在 input.end 之前返回音频；5 个分块；首包 3.28 秒 |
| 预热 TTS 全程 | 18.88 秒生成 15.20 秒音频，RTF 1.24 |
| 组合同传 | 音频上传 → 临时/最终识别 → 英文译文 → 2 个合成音频分块，正常结束 |

这是单次功能验收，不是压测或延迟分位数。ASR 的 15.41 秒 HTTP 耗时也包含首次加载。RTF = 总耗时 / 输出音频时长；本次预热 RTF 大于 1，**尚不能承诺 T4 持续实时输出**。长会话稳定性、并发、端到端翻译延迟和主观音质仍需专项评测。推理前端的 ONNX 算子使用 CPU provider，神经网络主体使用 CUDA。

## 实测后修复

- 固定 setuptools，解决上游依赖对 pkg_resources 的要求；隔离 Colab 的 matplotlib inline backend。
- 生成器模式不用 wetext，移除它的隐式模型下载依赖。
- CosyVoice 子进程加载 checkpoint 时使用 mmap，降低 CPU 内存峰值；异常/取消会终止整个子进程。
- 将输入文字分为中文字符与完整拉丁词，推动上游 bistream 解码，避免单个长 delta 等下一次输入才继续。
- 每次合成重置上游可变的初始分块大小，避免后续请求首包等待变长。

## 仍未验证

- 用户真实录音的 GPU 微调、训练后听感和泛化；当前没有用户训练数据，未生成个人音色权重。
- Docker 镜像实际构建和容器内推理；当前开发环境没有 Docker daemon。Compose 与镜像配方已提供，但不将脚本检查等同于镜像验收。
- 持续实时性能、并发容量、长期运行、ARM/macOS 原生部署、多机器扩展、多语言 ASR。
