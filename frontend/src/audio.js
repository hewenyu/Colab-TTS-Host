export function wavBlob(samples, rate = 16000) {
  const buffer = new ArrayBuffer(44 + samples.length * 2);
  const view = new DataView(buffer);
  const word = (offset, value) =>
    [...value].forEach((c, i) => view.setUint8(offset + i, c.charCodeAt(0)));
  word(0, "RIFF");
  view.setUint32(4, buffer.byteLength - 8, true);
  word(8, "WAVE");
  word(12, "fmt ");
  view.setUint32(16, 16, true);
  view.setUint16(20, 1, true);
  view.setUint16(22, 1, true);
  view.setUint32(24, rate, true);
  view.setUint32(28, rate * 2, true);
  view.setUint16(32, 2, true);
  view.setUint16(34, 16, true);
  word(36, "data");
  view.setUint32(40, samples.length * 2, true);
  samples.forEach((v, i) =>
    view.setInt16(
      44 + i * 2,
      Math.round(Math.max(-1, Math.min(1, v)) * (v < 0 ? 32768 : 32767)),
      true,
    ),
  );
  return new Blob([buffer], { type: "audio/wav" });
}

export async function normalizeAudio(file, maxMB, minSeconds = 1) {
  if (file.size > maxMB * 1024 * 1024)
    throw new Error(`文件超过 ${maxMB} MB，请先切成更短的片段。`);
  // Check container metadata before allocating decoded PCM for a long compressed recording.
  const url = URL.createObjectURL(file);
  try {
    const duration = await new Promise((resolve, reject) => {
      const media = new Audio();
      const timer = setTimeout(
        () => finish(new Error("无法读取音频，请转换为 WAV 后重试。")),
        10000,
      );
      function finish(error) {
        clearTimeout(timer);
        const duration = media.duration;
        media.removeAttribute("src");
        media.load();
        error ? reject(error) : resolve(duration);
      }
      media.preload = "metadata";
      media.onloadedmetadata = () => finish();
      media.onerror = () =>
        finish(new Error("浏览器无法读取这段音频，请转换为 WAV 后重试。"));
      media.src = url;
    });
    if (Number.isFinite(duration) && (duration < minSeconds || duration > 30.1))
      throw new Error(`录音需为 ${minSeconds}–30 秒，请先裁剪后上传。`);
  } finally {
    URL.revokeObjectURL(url);
  }
  const context = new AudioContext();
  try {
    let decoded;
    try {
      decoded = await context.decodeAudioData(await file.arrayBuffer());
    } catch {
      throw new Error("浏览器无法解码这段音频，请转换为 WAV 或 FLAC 后重试。");
    }
    if (decoded.duration < minSeconds || decoded.duration > 30.1)
      throw new Error(`录音需为 ${minSeconds}–30 秒，请先裁剪后上传。`);
    const render = new OfflineAudioContext(
      1,
      Math.round(decoded.duration * 16000),
      16000,
    );
    const source = render.createBufferSource();
    source.buffer = decoded;
    source.connect(render.destination);
    source.start();
    const mono = await render.startRendering();
    return { blob: wavBlob(mono.getChannelData(0)), duration: mono.duration };
  } finally {
    await context.close();
  }
}

export class PCMDecoder {
  constructor() {
    this.tail = null;
  }
  decode(bytes) {
    if (this.tail !== null) {
      const joined = new Uint8Array(bytes.length + 1);
      joined[0] = this.tail;
      joined.set(bytes, 1);
      bytes = joined;
    }
    const count = Math.floor(bytes.length / 2);
    this.tail = bytes.length % 2 ? bytes[bytes.length - 1] : null;
    const view = new DataView(bytes.buffer, bytes.byteOffset, count * 2);
    return Float32Array.from(
      { length: count },
      (_, i) => view.getInt16(i * 2, true) / 32768,
    );
  }
  finish() {
    if (this.tail !== null) throw new Error("音频流不完整，请重新生成。");
  }
}

export class AudioPlayer {
  constructor() {
    this.context = new AudioContext();
    this.next = 0;
    this.sources = new Set();
  }
  async start() {
    await this.context.resume();
  }
  get pending() {
    return Math.max(0, this.next - this.context.currentTime);
  }
  push(samples, rate) {
    if (!samples.length) return;
    const buffer = this.context.createBuffer(1, samples.length, rate);
    buffer.copyToChannel(samples, 0);
    const node = this.context.createBufferSource();
    node.buffer = buffer;
    node.connect(this.context.destination);
    this.next = Math.max(this.next, this.context.currentTime + 0.04);
    node.start(this.next);
    this.next += buffer.duration;
    this.sources.add(node);
    node.onended = () => this.sources.delete(node);
  }
  async stop() {
    for (const node of this.sources) {
      try {
        node.stop();
      } catch {}
    }
    this.sources.clear();
    if (!this.closing && this.context.state !== "closed")
      this.closing = this.context.close();
    await this.closing;
  }
}
