import React, { useState } from "react";
import { Icon, Empty, ErrorText, Waveform } from "./common.jsx";
import { normalizeAudio } from "./audio.js";
import {
  useStudio,
  patch,
  notify,
  guard,
  errorText,
  exampleText,
  sessionNow,
  assertSession,
  request,
  transcribe,
  refresh,
  generate,
  stopGeneration,
  exportVoice,
} from "./store.js";

function VoiceForm({ onClose }) {
  const s = useStudio(),
    [name, setName] = useState(""),
    [file, setFile] = useState(null),
    [text, setText] = useState(""),
    [consent, setConsent] = useState(false),
    [busy, setBusy] = useState(""),
    [error, setError] = useState("");
  async function run(action) {
    const current = sessionNow();
    setBusy(action);
    setError("");
    try {
      const normalized = await normalizeAudio(
        file,
        s.config.limits.upload_mb,
        3,
      );
      assertSession(current);
      if (action === "recognize") {
        const value = await transcribe(normalized.blob);
        assertSession(current);
        setText(value);
      } else {
        const form = new FormData();
        form.append("file", normalized.blob, "reference.wav");
        form.append("name", name.trim());
        form.append("transcript", text.trim());
        form.append("consent", String(consent));
        const voice = await (
          await request("/v1/voices", { method: "POST", body: form })
        ).json();
        assertSession(current);
        patch({ selected: voice.id });
        await refresh();
        assertSession(current);
        onClose();
        notify("音色已添加，现在可以生成第一段试听。", "success");
      }
    } catch (e) {
      setError(errorText(e));
    } finally {
      setBusy("");
    }
  }
  return (
    <form
      id="voice-form"
      className="upload-panel"
      onSubmit={(e) => {
        e.preventDefault();
        void run("save");
      }}
    >
      <div className="section-heading">
        <div>
          <h2>添加参考音色</h2>
          <p>上传 3–30 秒的清晰人声，即可先试听，无需训练。</p>
        </div>
        <button
          id="voice-close"
          type="button"
          className="text-button"
          disabled={!!busy}
          onClick={onClose}
        >
          收起
        </button>
      </div>
      <fieldset disabled={!!busy}>
        <div className="form-grid">
          <div>
            <label htmlFor="voice-name">音色名称</label>
            <input
              id="voice-name"
              maxLength={100}
              required
              placeholder="例如：我的日常声音"
              autoFocus
              value={name}
              onChange={(e) => setName(e.target.value)}
            />
            <label htmlFor="voice-file">参考录音</label>
            <input
              id="voice-file"
              type="file"
              accept="audio/*"
              required
              onChange={(e) => setFile(e.target.files[0])}
            />
            <p className="hint">
              WAV、FLAC，或浏览器可解码的 MP3 / M4A。上传前会转为单声道 WAV。
            </p>
          </div>
          <div>
            <div className="label-line">
              <label htmlFor="voice-transcript">录音中的原文</label>
              <button
                id="voice-transcribe"
                type="button"
                className="text-button"
                disabled={!file || !s.caps.asr?.enabled}
                onClick={() => run("recognize")}
              >
                {busy === "recognize" ? "识别中…" : "自动识别"}
              </button>
            </div>
            <textarea
              id="voice-transcript"
              rows={4}
              maxLength={1000}
              required
              placeholder="请逐字核对，与录音保持一致。"
              value={text}
              onChange={(e) => setText(e.target.value)}
            />
            <p className="hint">
              自动识别结果可修改，准确的原文会帮助音色克隆。
            </p>
          </div>
        </div>
        <label className="check">
          <input
            id="voice-consent"
            type="checkbox"
            required
            checked={consent}
            onChange={(e) => setConsent(e.target.checked)}
          />
          这是我的声音，或我已获得使用与克隆授权。
        </label>
        <div className="form-footer">
          <ErrorText id="voice-error">{error}</ErrorText>
          <button className="primary" type="submit">
            {busy === "save" ? "保存中…" : "保存音色"}
          </button>
        </div>
      </fieldset>
    </form>
  );
}
export default function Voices({ hidden }) {
  const s = useStudio(),
    [adding, setAdding] = useState(false),
    [query, setQuery] = useState(""),
    [text, setText] = useState(exampleText);
  const voice = s.voices.find((v) => v.id === s.selected),
    voices = s.voices.filter((v) =>
      v.name.toLocaleLowerCase().includes(query.toLocaleLowerCase()),
    );
  const maxText = Math.min(4000, s.config.limits.text_chars),
    output = s.output;
  const hint = s.generating
    ? s.generationText
    : s.generationText ||
      (!s.connected
        ? "连接后开始试听"
        : !s.caps.tts?.enabled
          ? "TTS 后端尚未启用"
          : voice
            ? "按所选音色生成语音"
            : "先选择一个音色");
  return (
    <section id="page-voices" className="page" hidden={hidden}>
      <div className="page-heading">
        <div>
          <h1>让文字，带上你的声音。</h1>
          <p>选一个音色，写下一段话，听听它的表达。</p>
        </div>
        <button
          id="new-voice"
          className="secondary"
          disabled={!s.connected}
          onClick={() => setAdding(true)}
        >
          添加音色 <span aria-hidden="true">+</span>
        </button>
      </div>
      {adding && <VoiceForm onClose={() => setAdding(false)} />}
      <div className="studio-grid">
        <section className="voice-library" aria-labelledby="voices-title">
          <div className="section-heading">
            <h2 id="voices-title">
              我的音色{" "}
              <span id="voice-count" className="count">
                {s.voices.length}
              </span>
            </h2>
          </div>
          <label className="sr-only" htmlFor="voice-search">
            搜索音色
          </label>
          <input
            id="voice-search"
            type="search"
            placeholder="搜索音色名称"
            disabled={!s.connected}
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />
          <div id="voice-list" className="voice-list">
            {voices.length ? (
              voices.map((v) => (
                <button
                  key={v.id}
                  className="voice-row"
                  data-voice={v.id}
                  aria-pressed={v.id === s.selected}
                  onClick={() => patch({ selected: v.id })}
                >
                  <span className="voice-mark">
                    <Icon />
                  </span>
                  <span className="voice-info">
                    <strong>{v.name}</strong>
                    <small>
                      {v.kind === "finetuned" ? "微调音色" : "参考音色"} · 版本{" "}
                      {v.version}
                    </small>
                  </span>
                  {v.id === s.selected && <Icon type="check" />}
                </button>
              ))
            ) : (
              <div className="empty">
                <h3>{query ? "没有匹配的音色" : "从你的第一段录音开始"}</h3>
                <p>
                  {query
                    ? "换个名称搜索，或清空搜索条件。"
                    : s.connected
                      ? "添加一段清晰人声，先听听零样本克隆的效果。"
                      : "连接服务后，添加一段参考人声。你的音色会显示在这里。"}
                </p>
                {s.connected && !query && (
                  <button className="secondary" onClick={() => setAdding(true)}>
                    添加第一个音色
                  </button>
                )}
              </div>
            )}
          </div>
        </section>
        <section className="composer" aria-labelledby="composer-title">
          <div className="section-heading">
            <h2 id="composer-title">声音试听</h2>
            <span id="selected-badge" className="badge">
              {voice ? `${voice.name} · v${voice.version}` : "未选择音色"}
            </span>
          </div>
          <label htmlFor="speech-text">想让它说些什么？</label>
          <textarea
            id="speech-text"
            rows={7}
            maxLength={maxText}
            value={text}
            onChange={(e) => setText(e.target.value)}
          />
          <div className="editor-meta">
            <span>保留自然标点，让语气更流畅。</span>
            <span id="char-count">
              {text.length} / {maxText}
            </span>
          </div>
          <div className="generate-actions">
            <button
              id="generate"
              className="primary"
              disabled={
                !s.connected ||
                !voice ||
                !s.caps.tts?.enabled ||
                s.generating ||
                !text.trim() ||
                text.length > maxText
              }
              onClick={() => generate(text)}
            >
              <Icon type="play" />
              生成并试听
            </button>
            <button
              id="stop"
              className="secondary"
              hidden={!s.generating}
              onClick={stopGeneration}
            >
              停止生成
            </button>
            <span id="generation-state" role="status">
              {hint}
            </span>
          </div>
          <div className="output">
            <div className="section-heading">
              <h3>生成结果</h3>
              <span id="output-meta" className="hint">
                {output
                  ? `${output.voice.name} · v${output.voice.version} · ${output.seconds.toFixed(1)} 秒 · ${output.rate / 1000} kHz`
                  : "音频将在这里出现"}
              </span>
            </div>
            <Waveform samples={s.waveform} />
            <audio
              key={output?.url || "empty"}
              id="result-audio"
              controls
              src={output?.url}
              hidden={!output}
              aria-label="生成结果播放器"
            />
            <div className="output-actions">
              <a
                id="download-audio"
                className="text-button"
                hidden={!output}
                href={output?.url}
                download={
                  output
                    ? `voice-${output.voice.id.slice(0, 8)}.wav`
                    : undefined
                }
              >
                下载 WAV
              </a>
              <button
                id="copy-voice"
                className="text-button"
                disabled={!voice}
                onClick={guard(async () => {
                  await navigator.clipboard.writeText(voice.id);
                  notify("已复制音色 ID。", "success");
                })}
              >
                复制音色 ID
              </button>
              <button
                id="export-voice"
                className="text-button"
                disabled={!voice}
                onClick={() => exportVoice(voice)}
              >
                导出音色配置
              </button>
            </div>
            <ErrorText id="speech-error">{s.speechError}</ErrorText>
          </div>
        </section>
      </div>
    </section>
  );
}
