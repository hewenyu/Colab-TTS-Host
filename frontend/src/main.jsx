import React, { useEffect, useState } from "react";
import { createRoot } from "react-dom/client";
import Voices from "./Voices.jsx";
import Materials from "./Materials.jsx";
import Training from "./Training.jsx";
import { Icon, ErrorText } from "./common.jsx";
import {
  useStudio,
  connect,
  disconnect,
  refresh,
  patch,
  notify,
  guard,
  errorText,
  sessionNow,
} from "./store.js";
import "./style.css";
const pages = {
  voices: "音色工作室",
  material: "训练素材",
  training: "训练任务",
};
const currentPage = () =>
  Object.hasOwn(pages, location.hash.slice(1))
    ? location.hash.slice(1)
    : "voices";
function Connection({ open, setOpen }) {
  const s = useStudio(),
    [key, setKey] = useState(""),
    [error, setError] = useState("");
  async function submit(e) {
    e.preventDefault();
    if (s.connecting) return;
    setError("");
    const value = key.trim();
    setKey("");
    try {
      await connect(value);
      setOpen(false);
    } catch (e) {
      setError(errorText(e));
    }
  }
  return (
    <section
      id="connection-panel"
      className="connect-panel"
      aria-labelledby="connection-title"
      hidden={!open}
    >
      <div>
        <h2 id="connection-title">连接你的语音服务</h2>
        <p>
          输入服务的 API
          Key，即可管理音色和训练素材。密钥只在本页内存中使用，刷新后需要重新连接。
        </p>
      </div>
      <form id="connect-form" onSubmit={submit}>
        <label htmlFor="api-key">API Key</label>
        <div className="input-action">
          <input
            id="api-key"
            type="password"
            autoComplete="off"
            placeholder="输入服务端配置的密钥"
            required
            value={key}
            onChange={(e) => setKey(e.target.value)}
          />
          <button className="primary" type="submit" disabled={s.connecting}>
            {s.connecting ? "连接中…" : "连接服务"}
          </button>
        </div>
        <ErrorText id="connect-error">{error}</ErrorText>
      </form>
      <button
        id="disconnect"
        className="text-button"
        hidden={!s.connected}
        onClick={() => {
          disconnect();
          setKey("");
          setError("");
          notify("已清除本页密钥与数据。");
        }}
      >
        断开连接并清除当前页面数据
      </button>
    </section>
  );
}
function Workspace({ page }) {
  return (
    <>
      <Voices hidden={page !== "voices"} />
      <Materials hidden={page !== "material"} />
      <Training hidden={page !== "training"} />
    </>
  );
}
function App() {
  const s = useStudio(),
    [page, setPage] = useState(currentPage),
    [connectionOpen, setConnectionOpen] = useState(true);
  useEffect(() => {
    const change = () => setPage(currentPage());
    window.addEventListener("hashchange", change);
    return () => window.removeEventListener("hashchange", change);
  }, []);
  useEffect(() => {
    const timer = setInterval(() => {
      if (
        s.connected &&
        !document.hidden &&
        (page === "training" ||
          s.jobs.some((j) => ["queued", "running"].includes(j.status)))
      ) {
        const current = sessionNow();
        refresh().catch((e) => {
          if (current === sessionNow()) patch({ pollError: errorText(e) });
        });
      }
    }, 5000);
    return () => clearInterval(timer);
  }, [s.connected, s.jobs, page]);
  useEffect(() => {
    const leave = () => disconnect();
    window.addEventListener("beforeunload", leave);
    return () => window.removeEventListener("beforeunload", leave);
  }, []);
  const pending = s.jobs.filter((j) =>
    ["queued", "running"].includes(j.status),
  ).length;
  return (
    <>
      <a
        className="skip-link"
        href="#main"
        onClick={(e) => {
          e.preventDefault();
          document.getElementById("main").focus();
        }}
      >
        跳到工作区
      </a>
      <div className="shell">
        <aside className="sidebar">
          <a className="brand" href="#voices" aria-label="声间，音色工作室">
            <Icon />
            <span>
              声间<small>VOICE STUDIO</small>
            </span>
          </a>
          <nav aria-label="工作区">
            {Object.entries(pages).map(([id, label]) => (
              <a
                key={id}
                href={`#${id}`}
                data-page={id}
                aria-current={page === id ? "page" : undefined}
              >
                <Icon type={id === "voices" ? "voice" : id} />
                {label}
                {id === "training" && pending > 0 && (
                  <span id="job-count" className="nav-count">
                    {pending}
                  </span>
                )}
              </a>
            ))}
          </nav>
          <div className="sidebar-bottom">
            <p>
              属于你的声音，
              <br />
              留在你的服务里。
            </p>
            <button
              id="connection-open"
              className="connection"
              onClick={() => setConnectionOpen(!connectionOpen)}
            >
              <span
                id="connection-dot"
                className={`status-dot ${s.connected ? "connected" : ""}`}
              />
              <span id="connection-label">
                {s.connected ? "服务已连接" : "连接服务"}
              </span>
              <Icon type="arrow" />
            </button>
          </div>
        </aside>
        <div className="workspace">
          <header className="topbar">
            <span id="breadcrumb">工作区 / {pages[page]}</span>
            <div>
              <span className="private-label">
                <Icon type="lock" />
                私有工作区
              </span>
              <button
                id="refresh"
                className="icon-button"
                aria-label="刷新工作区"
                disabled={!s.connected}
                onClick={guard(async () => {
                  await refresh();
                  notify("工作区已更新。", "success");
                })}
              >
                <Icon type="refresh" />
              </button>
            </div>
          </header>
          <main id="main" tabIndex={-1}>
            <div
              id="notice"
              className={`notice ${s.notice?.type || ""}`}
              role="status"
              hidden={!s.notice}
            >
              {s.notice?.text}
            </div>
            <Connection open={connectionOpen} setOpen={setConnectionOpen} />
            <Workspace key={s.epoch} page={page} />
            <footer className="page-footer">
              <span>声间 · Colab TTS Host</span>
              <a href="/docs" target="_blank" rel="noopener">
                API 文档
              </a>
            </footer>
          </main>
        </div>
      </div>
      {s.previewURL && (
        <audio
          key={s.previewURL}
          id="preview-audio"
          src={s.previewURL}
          controls
          autoPlay
          aria-label="素材试听播放器"
        />
      )}
    </>
  );
}
createRoot(document.getElementById("root")).render(<App />);
