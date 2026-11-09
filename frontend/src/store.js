import { useSyncExternalStore } from "react";
import { AudioPlayer, PCMDecoder, wavBlob } from "./audio.js";

export const exampleText =
  "你好，欢迎来到我的声音工作室。每一个文字，都可以有属于自己的表达。";
const initial = () => ({
  connected: false,
  connecting: false,
  voices: [],
  samples: [],
  jobs: [],
  selected: "",
  selectedSamples: [],
  caps: {},
  config: { limits: { upload_mb: 20, text_chars: 4000, audio_seconds: 120 } },
  notice: null,
  pollError: "",
  generating: false,
  generationText: "",
  speechError: "",
  output: null,
  waveform: null,
  previewURL: "",
  epoch: 0,
});
let state = initial(),
  key = "",
  session = new AbortController(),
  generation = null,
  player = null,
  refreshPromise = null;
const listeners = new Set();
export const snapshot = () => state;
export const patch = (update) => {
  state = { ...state, ...update };
  listeners.forEach((fn) => fn());
};
const subscribe = (fn) => {
  listeners.add(fn);
  return () => listeners.delete(fn);
};
export const useStudio = () => useSyncExternalStore(subscribe, snapshot);
export const notify = (text, type = "") => patch({ notice: { text, type } });
export const errorText = (e) =>
  e.name === "AbortError" ? "操作已取消。" : e.message || "操作失败，请重试。";
export const sessionNow = () => session;
export const assertSession = (expected) => {
  if (expected !== session || expected.signal.aborted)
    throw new DOMException("Aborted", "AbortError");
};
export const guard =
  (fn) =>
  (...args) =>
    Promise.resolve()
      .then(() => fn(...args))
      .catch((e) => {
        if (e.name !== "AbortError") notify(errorText(e), "error");
      });

export async function request(path, options = {}) {
  const response = await fetch(path, {
    ...options,
    cache: "no-store",
    signal: options.signal
      ? AbortSignal.any([options.signal, session.signal])
      : session.signal,
    headers: { Authorization: `Bearer ${key}`, ...options.headers },
  });
  if (!response.ok) {
    let body;
    try {
      body = await response.json();
    } catch {
      body = {};
    }
    const detail =
      typeof body.detail === "string"
        ? body.detail
        : Array.isArray(body.detail)
          ? body.detail
              .map((e) => `${e.loc?.slice(1).join(".")}: ${e.msg}`)
              .join("；")
          : "";
    if (response.status === 401)
      throw new Error("密钥无效或已过期，请重新连接服务。");
    if (response.status === 413)
      throw new Error("文件或生成音频超过服务限制，请缩短内容后重试。");
    if (response.status === 429)
      throw new Error("服务繁忙或已达到配额，请稍后重试。");
    throw new Error(
      detail || `服务返回 ${response.status}，请检查服务日志后重试。`,
    );
  }
  return response;
}
export const get = async (path) => (await request(path)).json();
export const post = async (path, body) =>
  (
    await request(path, {
      method: "POST",
      body: JSON.stringify(body),
      headers: { "Content-Type": "application/json" },
    })
  ).json();
export async function transcribe(blob) {
  const form = new FormData();
  form.append("file", blob, "recording.wav");
  return (
    await (
      await request("/v1/asr/transcriptions", { method: "POST", body: form })
    ).json()
  ).text;
}
export async function refresh() {
  if (!state.connected) return;
  if (refreshPromise) return refreshPromise;
  const current = session;
  const run = (async () => {
    const [voices, samples, jobs] = await Promise.all([
      get("/v1/voices"),
      get("/v1/training/samples"),
      get("/v1/voice-training/jobs"),
    ]);
    assertSession(current);
    patch({
      voices: voices.voices,
      samples: samples.samples,
      jobs: jobs.jobs,
      selected: voices.voices.some((v) => v.id === state.selected)
        ? state.selected
        : voices.voices[0]?.id || "",
      selectedSamples: state.selectedSamples.filter((id) =>
        samples.samples.some((s) => s.id === id),
      ),
      pollError: "",
    });
  })();
  refreshPromise = run;
  try {
    await run;
  } finally {
    if (refreshPromise === run) refreshPromise = null;
  }
}
export function stopGeneration() {
  generation?.abort();
  void player?.stop();
}
export function disconnect() {
  session.abort();
  session = new AbortController();
  stopGeneration();
  generation = null;
  player = null;
  refreshPromise = null;
  key = "";
  if (state.output) URL.revokeObjectURL(state.output.url);
  if (state.previewURL) URL.revokeObjectURL(state.previewURL);
  const epoch = state.epoch + 1;
  state = { ...initial(), epoch };
  patch({});
}
export async function connect(newKey) {
  disconnect();
  key = newKey;
  const current = session;
  patch({ connecting: true });
  try {
    const [caps, config] = await Promise.all([
      get("/v1/capabilities"),
      get("/v1/studio/config"),
    ]);
    assertSession(current);
    patch({ caps, config, connected: true });
    await refresh();
    assertSession(current);
    notify("服务已连接，素材和音色只在当前身份下可见。", "success");
  } catch (e) {
    if (current === session) disconnect();
    throw e;
  } finally {
    if (current === session) patch({ connecting: false });
  }
}
export async function previewSample(id) {
  const current = session;
  const blob = await (
    await request(`/v1/training/samples/${encodeURIComponent(id)}/audio`)
  ).blob();
  assertSession(current);
  if (state.previewURL) URL.revokeObjectURL(state.previewURL);
  patch({ previewURL: URL.createObjectURL(blob) });
  notify("素材已加载，可使用页面底部播放器试听。");
}
export async function generate(text) {
  const voice = state.voices.find((v) => v.id === state.selected);
  if (state.generating || !voice || !text.trim()) return;
  const current = session,
    controller = new AbortController(),
    audioPlayer = new AudioPlayer();
  generation = controller;
  player = audioPlayer;
  if (state.output) URL.revokeObjectURL(state.output.url);
  patch({
    generating: true,
    generationText: "等待首段音频，首次加载可能较慢",
    speechError: "",
    output: null,
    waveform: null,
  });
  const parts = [];
  let total = 0,
    received = false,
    complete = false;
  const start = performance.now();
  const timer = setInterval(() => {
    if (current === session)
      patch({
        generationText: `${received ? "正在生成并播放" : "等待首段音频，首次加载可能较慢"} · ${Math.floor((performance.now() - start) / 1000)} 秒`,
      });
  }, 1000);
  try {
    await audioPlayer.start();
    assertSession(current);
    const response = await request("/v1/tts/speech", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        text: text.trim(),
        voice_id: voice.id,
        stream: true,
      }),
      signal: controller.signal,
    });
    const rate = Number(response.headers.get("X-Sample-Rate"));
    if (!Number.isFinite(rate) || rate < 8000 || rate > 96000)
      throw new Error("服务返回的音频采样率无效。");
    const reader = response.body.getReader(),
      decoder = new PCMDecoder();
    try {
      while (true) {
        const { value, done } = await reader.read();
        if (done) break;
        assertSession(current);
        const samples = decoder.decode(value);
        if (!samples.length) continue;
        total += samples.length;
        if (total / rate > state.config.limits.audio_seconds)
          throw new Error("试听已达到时长上限，请缩短文本后重试。");
        parts.push(samples);
        received = true;
        audioPlayer.push(samples, rate);
        patch({ waveform: samples });
        while (
          audioPlayer.pending > 3 &&
          !controller.signal.aborted &&
          !current.signal.aborted
        )
          await new Promise((r) => setTimeout(r, 100));
        assertSession(current);
        controller.signal.throwIfAborted();
      }
      decoder.finish();
    } finally {
      await reader.cancel().catch(() => {});
      reader.releaseLock();
    }
    assertSession(current);
    controller.signal.throwIfAborted();
    if (!total) throw new Error("服务没有返回音频，请检查音色或重试。");
    const samples = new Float32Array(total);
    let offset = 0;
    for (const part of parts) {
      samples.set(part, offset);
      offset += part.length;
    }
    const url = URL.createObjectURL(wavBlob(samples, rate));
    patch({
      output: { url, voice, seconds: total / rate, rate },
      waveform: samples,
    });
    complete = true;
    while (
      audioPlayer.pending > 0 &&
      !controller.signal.aborted &&
      !current.signal.aborted
    )
      await new Promise((r) => setTimeout(r, 100));
  } catch (e) {
    if (current === session)
      patch({
        speechError: errorText(e),
        ...(!complete ? { waveform: null } : {}),
      });
  } finally {
    clearInterval(timer);
    await audioPlayer.stop();
    if (current === session && generation === controller) {
      generation = null;
      player = null;
      patch({
        generating: false,
        generationText: complete ? "生成完成，可重播或下载" : "",
      });
    }
  }
}
export function exportVoice(voice) {
  const { id: voice_id, name, version, kind, base_revision } = voice;
  const url = URL.createObjectURL(
    new Blob(
      [
        JSON.stringify(
          { voice_id, name, version, kind, base_revision },
          null,
          2,
        ),
      ],
      { type: "application/json" },
    ),
  );
  const a = document.createElement("a");
  a.href = url;
  a.download = `voice-${voice_id.slice(0, 8)}.json`;
  a.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
