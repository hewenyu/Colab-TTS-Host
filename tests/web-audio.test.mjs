import { test } from "node:test";
import assert from "node:assert/strict";
import { PCMDecoder, wavBlob } from "../frontend/src/audio.js";

test("PCM decoder carries odd network boundaries across reads", () => {
  const decoder = new PCMDecoder();
  assert.deepEqual([...decoder.decode(new Uint8Array([0]))], []);
  assert.deepEqual(
    [...decoder.decode(new Uint8Array([128, 255, 127, 0]))],
    [-1, 32767 / 32768],
  );
  assert.deepEqual([...decoder.decode(new Uint8Array([0]))], [0]);
  decoder.finish();
});
test("truncated audio is rejected instead of exported", () => {
  const decoder = new PCMDecoder();
  decoder.decode(new Uint8Array([1]));
  assert.throws(() => decoder.finish(), /不完整/);
});
test("downloadable WAV has accurate byte lengths and clipping", async () => {
  const view = new DataView(
    await wavBlob(new Float32Array([-2, 0, 2]), 24000).arrayBuffer(),
  );
  assert.equal(view.byteLength, 50);
  assert.equal(view.getUint32(24, true), 24000);
  assert.equal(view.getUint32(40, true), 6);
  assert.equal(view.getInt16(44, true), -32768);
  assert.equal(view.getInt16(48, true), 32767);
});
