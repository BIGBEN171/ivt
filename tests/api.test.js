/** Verify the HTTP boundary without a camera or any real patient data. */
import test from 'node:test';
import assert from 'node:assert/strict';
import { uploadPhoto } from '../src/services/api.js';
const photo = { id: 'sample-id', capturedAt: '2026-11-04T00:00:00Z', filename: 'capture.png', blob: new Blob(['png'], { type: 'image/png' }) };
const success = () => Response.json({ photo: { id: photo.id, size_bytes: photo.blob.size }, duplicate: false });

test('upload maps the original photo into multipart and preserves identity on retry', async () => {
  const calls = [];
  const fetcher = async (url, options) => { calls.push({ url, options }); return success(); };
  await uploadPhoto(photo, fetcher);
  await uploadPhoto(photo, fetcher);
  for (const { url, options } of calls) {
    assert.equal(url, '/api/v1/photos');
    assert.equal(options.method, 'POST');
    assert.equal(options.body.get('photo_id'), photo.id);
    assert.equal(options.body.get('captured_at'), photo.capturedAt);
    assert.equal(await options.body.get('file').text(), 'png');
    assert.equal(options.headers, undefined);
  }
});
test('HTTP failure and a network failure never become saved receipts', async () => {
  await assert.rejects(uploadPhoto(photo, async () => new Response('', { status: 503 })), /could not save/);
  await assert.rejects(uploadPhoto(photo, async () => { throw new Error('offline'); }), /interrupted/);
});
test('a response for another image is rejected', async () => {
  await assert.rejects(uploadPhoto(photo, async () => Response.json({ photo: { id: 'wrong', size_bytes: 3 } })), /unexpected receipt/);
});
