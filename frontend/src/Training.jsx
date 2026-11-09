import React, { useState, useEffect } from "react";
import { Empty, ErrorText, date } from "./common.jsx";
import {
  useStudio,
  patch,
  notify,
  errorText,
  sessionNow,
  assertSession,
  post,
  refresh,
} from "./store.js";
const statuses = {
  queued: "排队中",
  running: "训练中",
  succeeded: "已完成",
  failed: "失败",
  cancelled: "已取消",
  interrupted: "已中断",
};
const stages = {
  queued: "等待训练 worker 领取",
  preparing: "准备训练",
  checking_gpu: "检查 GPU",
  train_embeddings: "提取训练集音色特征",
  train_tokens: "提取训练集语音 token",
  train_parquet: "整理训练集",
  valid_embeddings: "提取验证集音色特征",
  valid_tokens: "提取验证集语音 token",
  valid_parquet: "整理验证集",
  training: "微调模型",
  complete: "新版本音色已生成",
  worker_restarted: "worker 重启，任务已中断",
};
export default function Training({ hidden }) {
  const s = useStudio(),
    [voice, setVoice] = useState(""),
    [epochs, setEpochs] = useState(1),
    [rate, setRate] = useState("0.00001"),
    [busy, setBusy] = useState(""),
    [error, setError] = useState("");
  useEffect(() => {
    if (!hidden) setVoice(s.selected || s.voices[0]?.id || "");
  }, [hidden, s.selected]);
  const duration = s.samples
    .filter((x) => s.selectedSamples.includes(x.id))
    .reduce((n, x) => n + x.duration, 0);
  async function submit(e) {
    e.preventDefault();
    if (busy) return;
    setBusy("submit");
    setError("");
    const current = sessionNow();
    try {
      await post("/v1/voice-training/jobs", {
        voice_id: voice,
        sample_ids: s.selectedSamples,
        epochs: Number(epochs),
        learning_rate: Number(rate),
      });
      assertSession(current);
      await refresh();
      notify("训练任务已创建，进度会自动更新。", "success");
    } catch (e) {
      setError(errorText(e));
    } finally {
      setBusy("");
    }
  }
  async function jobAction(job, action) {
    if (busy) return;
    setBusy(job.id);
    const current = sessionNow();
    try {
      if (action === "cancel")
        await post(
          `/v1/voice-training/jobs/${encodeURIComponent(job.id)}/cancel`,
          {},
        );
      await refresh();
      assertSession(current);
      if (action === "use") {
        patch({ selected: job.output_voice_id });
        location.hash = "voices";
      }
    } catch (e) {
      if (e.name !== "AbortError") notify(errorText(e), "error");
    } finally {
      setBusy("");
    }
  }
  return (
    <section id="page-training" className="page" hidden={hidden}>
      <div className="page-heading">
        <div>
          <h1>给你的音色，再多一点细节。</h1>
          <p>使用已标注素材微调，完成后保留原音色，生成新版本。</p>
        </div>
      </div>
      <div id="training-unavailable" className="notice">
        {!s.connected
          ? "连接服务后可查看训练能力。"
          : s.config.training_enabled
            ? "训练已启用。请确保独立 worker 已启动，避免在同一张 GPU 上同时训练与试听。"
            : "此服务尚未启用训练。可以先准备素材和试听音色；启用 training.enabled 并启动 speech-worker 后再提交任务。"}
      </div>
      <form id="training-form" className="training-form" onSubmit={submit}>
        <fieldset disabled={!!busy}>
          <div className="form-grid">
            <div>
              <label htmlFor="training-voice">参考音色</label>
              <select
                id="training-voice"
                required
                value={voice}
                onChange={(e) => setVoice(e.target.value)}
              >
                {s.voices.length ? (
                  s.voices.map((v) => (
                    <option key={v.id} value={v.id}>
                      {v.name} · v{v.version}
                    </option>
                  ))
                ) : (
                  <option value="">先添加一个音色</option>
                )}
              </select>
              <p className="hint">新版本会沿用这个音色的参考录音。</p>
            </div>
            <div>
              <span className="field-label">训练素材</span>
              <p id="training-selection" className="selection-summary">
                {s.selectedSamples.length
                  ? `${s.selectedSamples.length} 段 · ${duration.toFixed(1)} 秒`
                  : "尚未选择素材"}
              </p>
              <a href="#material" className="text-button">
                前往素材库选择
              </a>
            </div>
          </div>
          <details>
            <summary>训练参数</summary>
            <div className="form-grid">
              <div>
                <label htmlFor="epochs">训练轮数</label>
                <input
                  id="epochs"
                  type="number"
                  min={1}
                  max={20}
                  required
                  value={epochs}
                  onChange={(e) => setEpochs(e.target.value)}
                />
              </div>
              <div>
                <label htmlFor="learning-rate">学习率</label>
                <select
                  id="learning-rate"
                  value={rate}
                  onChange={(e) => setRate(e.target.value)}
                >
                  <option value="0.00001">0.00001（默认）</option>
                  <option value="0.000005">0.000005</option>
                  <option value="0.00002">0.00002</option>
                </select>
              </div>
            </div>
          </details>
          <div className="form-footer">
            <ErrorText id="training-error">{error}</ErrorText>
            <button
              id="start-training"
              className="primary"
              type="submit"
              disabled={
                !s.connected ||
                !s.config.training_enabled ||
                s.selectedSamples.length < 5 ||
                !voice
              }
            >
              {busy === "submit" ? "提交中…" : "创建训练任务"}
            </button>
          </div>
        </fieldset>
      </form>
      <div className="section-heading">
        <h2>任务记录</h2>
        <span id="poll-state" className="hint">
          {s.pollError
            ? `更新失败：${s.pollError}`
            : s.connected
              ? "每 5 秒检查任务"
              : "连接后自动更新"}
        </span>
      </div>
      <div id="job-list">
        {s.jobs.length ? (
          s.jobs.map((j) => (
            <article key={j.id} className="job">
              <div className="job-top">
                <div className="job-title">
                  <h3>
                    {s.voices.find((v) => v.id === j.voice_id)?.name || "音色"}
                  </h3>
                  <span className={`state ${j.status}`}>
                    {statuses[j.status] || j.status}
                  </span>
                </div>
                <span className="hint">{date(j.created_at)}</span>
              </div>
              <div className="job-details">
                <span>{j.sample_ids.length} 段素材</span>
                <span>{j.epochs} 轮训练</span>
                <span>任务 {j.id.slice(0, 8)}</span>
              </div>
              <p className="job-stage">
                {j.cancel_requested && ["queued", "running"].includes(j.status)
                  ? "已请求取消，等待 worker 确认"
                  : stages[j.stage] || j.stage}
              </p>
              {j.error && <ErrorText>{j.error}</ErrorText>}
              {j.status === "queued" && !j.cancel_requested && (
                <p className="hint">
                  若一直排队，请在服务端启动 speech-worker。
                </p>
              )}
              {["queued", "running"].includes(j.status) && (
                <button
                  className="text-button"
                  data-cancel={j.id}
                  disabled={!!busy || j.cancel_requested}
                  onClick={() => jobAction(j, "cancel")}
                >
                  {busy === j.id ? "正在取消…" : "取消任务"}
                </button>
              )}
              {j.status === "succeeded" && j.output_voice_id && (
                <button
                  className="text-button"
                  data-use-voice={j.output_voice_id}
                  disabled={!!busy}
                  onClick={() => jobAction(j, "use")}
                >
                  选择新音色并试听
                </button>
              )}
            </article>
          ))
        ) : (
          <Empty title="还没有训练任务">
            选好参考音色和素材后，在上方创建任务。
          </Empty>
        )}
      </div>
    </section>
  );
}
