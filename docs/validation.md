# 验收记录

日期：2026-11-09。实现分支 `feat/streaming-speech-server`。

## 自动化测试

本地 Python 3.12：18 项测试通过。覆盖 HTTP/WS 鉴权、音色跨身份隔离、未配置后端、ASR cache 隔离、PCM 格式校验、排空顺序、TTS 输入结束前输出、取消关闭生成器及实际子进程回收、有界队列溢出、实际 chunked body 大小限制、音频时长/重采样、持久化任务原子领取及重复音频检测。

这些测试使用注入的测试替身验证服务协议，不代表模型质量或速度。配置、notebook JSON、Python 编译和 shell 语法检查通过。

## Colab 资源

连接器能读取免费订阅并创建 CPU 运行时。资源列表显示 T4 eligible，但实际创建 T4 返回 `INVALID_ARGUMENT / Precondition check failed`。未申请付费资源、未升级账号。Python 3.10 隔离环境已安装，CosyVoice 与 FunASR 导入成功。

固定版本模型已下载：CosyVoice3 `29e01c4e8d000f4bcd70751be16fa94bf3d85a18`，Qwen2.5-0.5B `7ae557604adf67be50417f59c2c2f167def9a775`；CosyVoice 源码 `074ca6dc9e80a2f424f1f74b48bdd7d3fea531cc`。

真实 ASR HTTP、流式 ASR 和翻译已通过：3.48 秒公开参考音频返回“希望你以后能够做的比我还好哟”，WebSocket 返回 4 次临时结果；英文译文为“Hope you can do even better than me in the future.”。

真实 TTS/组合链路仍在验收。已修复 Colab 隔离环境中的 pkg_resources 缺失和 matplotlib inline backend 继承问题；生成器模式不使用 wetext，因此移除它的隐式下载依赖。普通加载在约 13 GB CPU 运行时发生子进程 SIGKILL，已加入 checkpoint mmap 降低加载时匿名内存峰值。

## 仍未验证

- CUDA/T4 首音频延迟、持续实时系数、并发容量。
- 用户真实录音的训练、训练后主观听感和泛化；当前没有用户数据。
- Docker 镜像实际构建和容器内推理；当前开发环境没有 Docker daemon。
- ARM/macOS 原生部署、多机器扩展、多语言 ASR。
