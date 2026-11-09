import React, { useState, useRef, useEffect } from "react";
import { Icon, Empty, ErrorText, date } from "./common.jsx";
import { normalizeAudio } from "./audio.js";
import {
  useStudio,
  patch,
  notify,
  guard,
  errorText,
  sessionNow,
  assertSession,
  request,
  transcribe,
  refresh,
  previewSample,
  snapshot,
} from "./store.js";

export default function Materials({ hidden }) {
  const s = useStudio(),
    [drafts, setDrafts] = useState([]),
    [busy, setBusy] = useState(""),
    [consent, setConsent] = useState(false),
    [error, setError] = useState(""),
    [dragging, setDragging] = useState(false);
  const urls = useRef(new Set()),
    lock = useRef(false),
    all = useRef();
  useEffect(
    () => () => {
      urls.current.forEach((url) => URL.revokeObjectURL(url));
      urls.current.clear();
    },
    [],
  );
  useEffect(() => {
    all.current.indeterminate =
      s.selectedSamples.length > 0 &&
      s.selectedSamples.length < s.samples.length;
  }, [s.selectedSamples, s.samples]);
  function update(id, changes) {
    setDrafts((items) =>
      items.map((d) => (d.id === id ? { ...d, ...changes } : d)),
    );
  }
  function release(url) {
    URL.revokeObjectURL(url);
    urls.current.delete(url);
  }
  async function addFiles(files) {
    if (!s.connected || lock.current) return;
    lock.current = true;
    setBusy("adding");
    const current = sessionNow();
    let added = 0;
    const errors = [];
    try {
      const capacity = 50 - drafts.length;
      if (files.length > capacity)
        errors.push(`每批最多 50 段，本次只准备前 ${capacity} 段。`);
      for (const file of Array.from(files).slice(0, capacity)) {
        try {
          const audio = await normalizeAudio(file, s.config.limits.upload_mb);
          assertSession(current);
          const url = URL.createObjectURL(audio.blob);
          urls.current.add(url);
          setDrafts((items) => [
            ...items,
            {
              id: crypto.randomUUID(),
              name: file.name,
              ...audio,
              url,
              text: "",
              error: "",
            },
          ]);
          added++;
        } catch (e) {
          if (e.name === "AbortError") throw e;
          errors.push(`${file.name}：${errorText(e)}`);
        }
      }
      assertSession(current);
      notify(
        errors.length
          ? errors.join("；")
          : `已准备 ${added} 段音频，请补充原文后保存。`,
        errors.length ? "error" : "success",
      );
    } catch (e) {
      if (e.name !== "AbortError") notify(errorText(e), "error");
    } finally {
      lock.current = false;
      setBusy("");
    }
  }
  async function recognize(d) {
    if (lock.current) return;
    lock.current = true;
    setBusy(d.id);
    const current = sessionNow();
    try {
      const text = await transcribe(d.blob);
      assertSession(current);
      update(d.id, { text, error: "" });
    } catch (e) {
      update(d.id, { error: errorText(e) });
    } finally {
      lock.current = false;
      setBusy("");
    }
  }
  async function save() {
    if (lock.current) return;
    setError("");
    if (!consent) {
      setError("请先确认录音的训练授权。");
      return;
    }
    const ready = drafts.filter((d) => d.text.trim());
    if (!ready.length) {
      setError("请至少为一段录音填写原文。");
      return;
    }
    lock.current = true;
    setBusy("saving");
    const current = sessionNow();
    let saved = 0;
    try {
      for (const d of ready) {
        assertSession(current);
        try {
          const form = new FormData();
          form.append("file", d.blob, "sample.wav");
          form.append("transcript", d.text.trim());
          form.append("consent", "true");
          const sample = await (
            await request("/v1/training/samples", {
              method: "POST",
              body: form,
            })
          ).json();
          assertSession(current);
          patch({
            selectedSamples: [...snapshot().selectedSamples, sample.id],
          });
          setDrafts((items) => items.filter((x) => x.id !== d.id));
          release(d.url);
          saved++;
        } catch (e) {
          if (e.name === "AbortError") throw e;
          update(d.id, { error: errorText(e) });
        }
      }
      await refresh();
      assertSession(current);
      notify(
        `已保存 ${saved} 段素材。${drafts.length > saved ? "剩余素材仍保留在待上传列表。" : ""}`,
        saved ? "success" : "error",
      );
    } catch (e) {
      setError(errorText(e));
    } finally {
      lock.current = false;
      setBusy("");
    }
  }
  const toggle = (id, checked) =>
    patch({
      selectedSamples: checked
        ? [...s.selectedSamples, id]
        : s.selectedSamples.filter((x) => x !== id),
    });
  return (
    <section id="page-material" className="page" hidden={hidden}>
      <div className="page-heading">
        <div>
          <h1>好声音，从好素材开始。</h1>
          <p>每段录音配上准确原文，选中后就能用于训练。</p>
        </div>
        <button
          id="material-train"
          className="primary"
          disabled={s.selectedSamples.length < 5}
          onClick={() => {
            location.hash = "training";
          }}
        >
          用所选素材训练
        </button>
      </div>
      <div
        id="dropzone"
        className={`dropzone ${dragging ? "dragging" : ""}`}
        onDragOver={(e) => {
          e.preventDefault();
          if (s.connected && !busy) setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={(e) => {
          e.preventDefault();
          setDragging(false);
          void addFiles(e.dataTransfer.files);
        }}
      >
        <Icon type="upload" />
        <h2>把录音拖到这里</h2>
        <p>每段 1–30 秒，可一次选择多段。文件只上传到当前服务。</p>
        <label className="secondary file-label">
          {busy === "adding" ? "准备音频中…" : "选择音频文件"}
          <input
            id="material-files"
            type="file"
            accept="audio/*"
            multiple
            disabled={!s.connected || !!busy}
            onChange={(e) => {
              void addFiles(Array.from(e.target.files));
              e.target.value = "";
            }}
          />
        </label>
      </div>
      <div id="draft-section" hidden={!drafts.length}>
        <div className="section-heading">
          <h2>待上传素材</h2>
          <span className="hint">先核对每段原文，再保存</span>
        </div>
        <fieldset disabled={!!busy}>
          <div id="draft-list">
            {drafts.map((d) => (
              <div key={d.id} className="draft-row" data-draft={d.id}>
                <div>
                  <strong>{d.name}</strong>
                  <p className="hint">
                    {d.duration.toFixed(1)} 秒 · 已转为 16 kHz WAV
                  </p>
                  <audio controls src={d.url} aria-label={`试听 ${d.name}`} />
                  <div className="draft-actions">
                    <button
                      className="text-button"
                      data-transcribe={d.id}
                      disabled={!s.caps.asr?.enabled}
                      onClick={() => recognize(d)}
                    >
                      {busy === d.id ? "识别中…" : "自动识别"}
                    </button>
                    <button
                      className="text-button"
                      data-remove={d.id}
                      onClick={() => {
                        release(d.url);
                        setDrafts((items) =>
                          items.filter((x) => x.id !== d.id),
                        );
                      }}
                    >
                      移除
                    </button>
                  </div>
                </div>
                <div>
                  <label htmlFor={`transcript-${d.id}`}>录音原文</label>
                  <textarea
                    id={`transcript-${d.id}`}
                    data-transcript={d.id}
                    maxLength={1000}
                    rows={3}
                    placeholder="输入或识别原文，再逐字核对。"
                    value={d.text}
                    onChange={(e) => update(d.id, { text: e.target.value })}
                  />
                  <ErrorText>{d.error}</ErrorText>
                </div>
              </div>
            ))}
          </div>
          <label className="check">
            <input
              id="material-consent"
              type="checkbox"
              checked={consent}
              onChange={(e) => setConsent(e.target.checked)}
            />
            我拥有这些录音的训练授权。
          </label>
          <div className="form-footer">
            <ErrorText id="material-error">{error}</ErrorText>
            <button id="save-material" className="primary" onClick={save}>
              {busy === "saving" ? "上传中…" : "保存已标注素材"}
            </button>
          </div>
        </fieldset>
      </div>
      <section className="material-library">
        <div className="section-heading">
          <h2>
            素材库{" "}
            <span id="sample-count" className="count">
              {s.samples.length}
            </span>
          </h2>
          <span id="selection-count" className="hint">
            已选择 {s.selectedSamples.length} 段
          </span>
        </div>
        <div className="table-scroll">
          <table>
            <thead>
              <tr>
                <th>
                  <input
                    id="select-all"
                    ref={all}
                    type="checkbox"
                    aria-label="选择全部素材"
                    checked={
                      s.samples.length > 0 &&
                      s.selectedSamples.length === s.samples.length
                    }
                    onChange={(e) =>
                      patch({
                        selectedSamples: e.target.checked
                          ? s.samples.map((x) => x.id)
                          : [],
                      })
                    }
                  />
                </th>
                <th>录音原文</th>
                <th>时长</th>
                <th>添加时间</th>
                <th>试听</th>
              </tr>
            </thead>
            <tbody id="sample-list">
              {s.samples.map((sample) => (
                <tr key={sample.id}>
                  <td>
                    <input
                      type="checkbox"
                      data-sample={sample.id}
                      aria-label={`选择素材：${sample.transcript.slice(0, 50)}`}
                      checked={s.selectedSamples.includes(sample.id)}
                      onChange={(e) => toggle(sample.id, e.target.checked)}
                    />
                  </td>
                  <td>{sample.transcript}<small className="mobile-meta">{sample.duration.toFixed(1)} 秒 · {date(sample.created_at)}</small></td>
                  <td>{sample.duration.toFixed(1)} 秒</td>
                  <td>{date(sample.created_at)}</td>
                  <td>
                    <button
                      className="text-button"
                      data-preview={sample.id}
                      onClick={guard(() => previewSample(sample.id))}
                    >
                      试听
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {!s.samples.length && (
          <Empty title="还没有训练素材">
            先上传录音并补充原文。训练至少需要 5 段不同的录音。
          </Empty>
        )}
      </section>
    </section>
  );
}
