import test from 'node:test';
import assert from 'node:assert/strict';
import { collectFrames } from '../src/services/burst.js';

// Model the browser callback queue without using a real patient's camera.
test('burst ignores repeated media timestamps and records fifteen new frames', async () => {
  const callbacks = new Map(); let id = 0;
  global.document = { hidden: false, addEventListener() {}, removeEventListener() {}, createElement() {
    return { width: 0, height: 0, getContext: () => ({ drawImage() {} }) };
  } };
  const video = { videoWidth: 4, videoHeight: 3,
    requestVideoFrameCallback(fn) { callbacks.set(++id, fn); return id; },
    cancelVideoFrameCallback(key) { callbacks.delete(key); } };
  const promise = collectFrames(video);
  const deliver = time => { const [key, fn] = callbacks.entries().next().value; callbacks.delete(key); fn(time*1000, { mediaTime: time, presentedFrames: key }); };
  deliver(1); deliver(1);
  for (let i = 2; i <= 15; i++) deliver(i);
  const frames = await promise;
  assert.equal(frames.length, 15);
  assert.equal(frames[1].mediaTimeMs, 2000);
  assert.equal(callbacks.size, 0);
});

test('aborting a burst cancels its outstanding frame callback', async () => {
  global.document = { hidden: false, addEventListener() {}, removeEventListener() {} };
  let cancelled = false;
  const controller = new AbortController();
  const promise = collectFrames({ requestVideoFrameCallback() { return 7; }, cancelVideoFrameCallback(id) { cancelled = id === 7; } }, { signal: controller.signal });
  controller.abort();
  await assert.rejects(promise, /cancelled/);
  assert.equal(cancelled, true);
});
