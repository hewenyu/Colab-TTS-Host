# 流式协议 v1

连接 `ws[s]://host/v1/stream`，握手头携带 `Authorization: Bearer <key>`。服务只提供 server API；浏览器不能直接设置 WebSocket Authorization header 时，应通过自己的后端代理，不能将长期 API key 放在 URL 中。

第一条必须是 JSON：

```json
{"type":"session.start","mode":"interpret","source_language":"zh","target_language":"en","voice_id":"your-voice-id","sample_rate":16000}
```

`mode` 为 `asr`、`translate`、`interpret` 或 `tts`。TTS/interpret 必须提供自己的 voice_id。等待 `session.ready` 后再送输入。

## 输入

| 输入 | 格式/作用 |
| --- | --- |
| 音频 | WebSocket binary frame，PCM signed 16-bit little-endian，16 kHz，单声道；每帧不超过 1 秒，建议 100–200 ms |
| 文本 | `{"type":"text.delta","text":"继续说的文字"}`，只用于 mode=tts |
| 句子确认 | `{"type":"input.commit"}`，音频模式，提交目前收到的音频；不关闭输入 |
| 输入结束 | `{"type":"input.end"}`，不再输入，等待所有结果和 session.done |
| 取消 | `{"type":"session.cancel"}`，终止当前会话；与正常结束的排空行为不同 |

发送与读取输出必须并行。音频按实时速率发送；如果不读输出或瞬间倾倒整段录音，有限队列可能溢出并关闭连接。文件批量识别应使用 HTTP API。

## 输出

正常事件包含 `session_id` 和单调递增的 `seq`。每个确认语句有 `segment_id`，其语音块还有 `chunk_index`。

| type | 主要字段 | 含义 |
| --- | --- | --- |
| session.ready | mode, sample_rate, resume_supported=false | 已接受会话，模型可能仍需冷启动 |
| asr.partial | segment_id, text, revision | 当前语句临时文字，客户端应替换该语句字幕 |
| asr.final | segment_id, text | 此语句确认，后续不会修改；静音可能为空 |
| translation.final | segment_id, source_text, text | 已确认源句对应的完整译文 |
| audio.chunk | segment_id, chunk_index, audio, sample_rate, channels, encoding | audio 为 base64 编码的 PCM16，按序拼接 |
| audio.done | segment_id, chunks | 此语句音频排空 |
| session.done | — | 整个会话排空；随后正常关闭 |
| session.cancelled | — | 用户主动取消，随后关闭 |
| error | message | 协议/容量/模型错误，随后关闭；本次未完成结果应标记不完整 |

终止事件 `error` 和 `session.cancelled` 可能发生在会话初始化阶段，不保证具有 session_id/seq。正常流的 `seq` 用于检测重复/缺块，并不提供恢复游标。禁止把重连当作自动续播。WebSocket close 1008 表示参数/鉴权/限制问题，1011 表示后端执行失败。

ASR 每 600 ms 推进一次模型 cache。每条连接 cache 独立，确认语句后重置。解释链路在确认语句后翻译；TTS 则会边生成边发送音频。独立 TTS 将多个 `text.delta` 接到同一次 CosyVoice3 的 `inference_bistream`，不是每个 delta 重新生成。模型必须累积足够文本 token 才能输出首块，极短输入可能需要 input.end 才出声。

服务没有默认“听到新音频就打断朗读”的行为；语音输入和翻译输出可重叠。一个会话结束时会释放其任务。CosyVoice 上游生成包含不可安全中断的后台线程，所以异常终止会杀掉专用模型子进程；下一请求重新加载，延迟会高于热运行。


## 完整文本与双向文字输入

HTTP `/v1/tts/speech` 已收到完整文本，使用 CosyVoice 的完整文本解码路径，`stream=true` 仍逐块输出音频，不等待整段音频生成。组合同传中已经提交的翻译句子也使用该路径。

WebSocket `mode=tts` 的 `text.delta` 是真正增量文字，保留原生 `inference_bistream`。在本项目锁定的上游版本中，某些参考录音配短目标句会复述参考文本末尾；修复完整文本调用不等于修复上游所有双向流式组合。若已持有完整句子，使用 HTTP 接口以避免此次复现的前缀问题。不能用固定剪掉开头几秒来掩盖，因为正常目标语音也可能被剪掉。
