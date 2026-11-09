// Starts a private Python fixture unless STUDIO_TEST_URL is set. Synthetic audio only.
import { createRequire } from "node:module";
import { mkdir, writeFile } from "node:fs/promises";
import assert from "node:assert/strict";
import { spawn } from "node:child_process";
import { wavBlob } from "../frontend/src/audio.js";
const require = createRequire(import.meta.url);
const fixture = process.env.STUDIO_TEST_URL
  ? null
  : spawn(
      process.env.PYTHON_BIN || ".venv/bin/python",
      ["tests/studio_server.py"],
      { stdio: "ignore" },
    );
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || "playwright");
const browser = await chromium.launch({
  headless: true,
  executablePath: process.env.CHROMIUM_PATH || undefined,
  args: ["--no-sandbox", "--autoplay-policy=no-user-gesture-required"],
});
const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
const failures = [];
page.on("pageerror", (error) => failures.push(error.message));
page.on("console", (msg) => {
  if (msg.type() === "error" && /Content Security Policy/.test(msg.text()))
    failures.push(msg.text());
});
const root = process.env.STUDIO_TEST_URL || "http://127.0.0.1:8765";
const screenshots = ".impeccable/review";
await mkdir(screenshots, { recursive: true });
try {
  for (let i = 0; i < 100; i++) {
    try {
      if ((await fetch(root + "/health/live")).ok) break;
    } catch {}
    await new Promise((r) => setTimeout(r, 100));
  }
  await page.goto(root);
  await page.locator("#api-key").fill("incorrect");
  await page.locator("#connect-form button[type=submit]").click();
  await page
    .locator("#connect-error")
    .filter({ hasText: "密钥无效" })
    .waitFor();
  await page
    .locator("#api-key")
    .fill("studio-test-only-key-not-for-production");
  await page.locator("#connect-form button[type=submit]").click();
  await page.locator(".voice-row").first().waitFor();
  assert.equal(await page.locator("#api-key").inputValue(), "");
  await page.locator("#generate").click();
  await page.locator("#download-audio").waitFor({ state: "visible" });
  await page.getByText("生成完成，可重播或下载", { exact: true }).waitFor();
  assert.ok(
    (await page.locator("#result-audio").getAttribute("src")).startsWith(
      "blob:",
    ),
  );
  await page.screenshot({ path: `${screenshots}/desktop.png`, fullPage: true });
  // Decode browser upload, recognize its transcript, and persist a real API voice.
  const audio = new Float32Array(16000 * 4);
  for (let i = 0; i < audio.length; i++) audio[i] = Math.sin(i * 0.03) * 0.1;
  const wav = Buffer.from(await wavBlob(audio).arrayBuffer());
  await page.locator("#new-voice").click();
  await page.locator("#voice-name").fill("浏览器上传验证");
  await page
    .locator("#voice-file")
    .setInputFiles({
      name: "synthetic.wav",
      mimeType: "audio/wav",
      buffer: wav,
    });
  await page.locator("#voice-transcribe").click();
  await page.waitForFunction(
    () => document.querySelector("#voice-transcript").value === "你好",
  );
  await page.locator("#voice-consent").check();
  await page.getByRole("button", { name: "保存音色", exact: true }).click();
  await page
    .locator(".voice-row[aria-pressed=true]")
    .filter({ hasText: "浏览器上传验证" })
    .waitFor();
  await page.getByRole("link", { name: "训练素材", exact: true }).click();
  await page
    .locator("#material-files")
    .setInputFiles({
      name: "training.wav",
      mimeType: "audio/wav",
      buffer: wav,
    });
  await page.locator(".draft-row").waitFor();
  await page.locator("[data-transcript]").fill("浏览器素材上传验证。");
  await page.locator("#material-consent").check();
  await page.locator("#save-material").click();
  await page.locator("#draft-section").waitFor({ state: "hidden" });
  await page.locator("#select-all").check();
  await page.screenshot({
    path: `${screenshots}/materials.png`,
    fullPage: true,
  });
  await page.locator("#material-train").click();
  await page.locator("#start-training").click();
  await page.locator("[data-cancel]").first().waitFor();
  await page.locator("[data-cancel]").first().click();
  await page
    .getByText("已请求取消，等待 worker 确认", { exact: true })
    .waitFor();
  await page.screenshot({
    path: `${screenshots}/training.png`,
    fullPage: true,
  });
  await page.locator("[data-use-voice]").first().click();
  await page
    .locator(".voice-row[aria-pressed=true]")
    .filter({ hasText: "版本 2" })
    .waitFor();
  await page.setViewportSize({ width: 390, height: 844 });
  await page.screenshot({ path: `${screenshots}/mobile.png`, fullPage: true });
  assert.equal(
    await page.evaluate(
      () => document.documentElement.scrollWidth > innerWidth,
    ),
    false,
  );
  await page.getByRole("link", { name: "训练素材", exact: true }).click();
  await page.screenshot({
    path: `${screenshots}/mobile-materials.png`,
    fullPage: true,
  });
  assert.equal(
    await page.evaluate(
      () => document.documentElement.scrollWidth > innerWidth,
    ),
    false,
  );
  await page.locator("#connection-open").click();
  await page.locator("#disconnect").click();
  assert.equal(await page.locator(".voice-row").count(), 0);
  assert.equal(await page.locator("#sample-list tr").count(), 0);
  assert.equal(await page.locator("#download-audio").isVisible(), false);
  assert.equal(await page.locator("#generate").isDisabled(), true);
  assert.deepEqual(
    await page.evaluate(() => ({
      local: localStorage.length,
      session: sessionStorage.length,
    })),
    { local: 0, session: 0 },
  );
  assert.deepEqual(failures, []);
  console.log(
    "PASS: auth, streamed playback, upload/transcription, material selection, training/cancel/result, mobile overflow, disconnect privacy.",
  );
} finally {
  await browser.close();
  fixture?.kill("SIGTERM");
}
