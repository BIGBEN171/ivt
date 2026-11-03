// Unit tests for the storage service, using Node's built-in test runner.
// Mock handles implement only the browser methods needed by savePhoto. No real
// directory, permission dialog, camera, or network connection is used here.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { savePhoto } from '../src/services/localStorage.js';

// A minimal Photo-shaped fixture is enough: savePhoto reads only filename/blob.
// These bytes are arbitrary test data; image encoding belongs to camera.js.
const photo = { filename: 'capture_fixed-id.png', blob: new Blob(['photo']) };
// Verify the operation order and that retrying the same object targets the same
// filename. The write mock also checks that the original Blob is passed through.
test('只有写入并关闭成功才返回保存回执；重试使用同一文件名', async () => {
  const calls = [];
  const directory = {
    queryPermission: async () => 'granted',
    getFileHandle: async name => {
      calls.push(name);
      return { createWritable: async () => ({ write: async data => { assert.equal(data, photo.blob); calls.push('write'); }, close: async () => calls.push('close') }) };
    },
  };
  // Await the service rather than treating stream creation as completion.
  const receipt = await savePhoto(directory, photo);
  assert.equal(receipt.filename, photo.filename);
  await savePhoto(directory, photo);
  assert.deepEqual(calls, [photo.filename, 'write', 'close', photo.filename, 'write', 'close']);
});
// Denied permission must reject before any file handle is requested.
test('权限失效不创建文件', async () => {
  await assert.rejects(savePhoto({ queryPermission: async () => 'denied', getFileHandle: () => assert.fail('不应创建文件') }, photo), /permission has expired/);
});
// A write failure must attempt abort, preserve the failure, and never report a
// successful close. This tests cleanup behavior rather than a real disk failure.
test('写入失败中止流并保留错误', async () => {
  let aborted = false;
  const directory = { queryPermission: async () => 'granted', getFileHandle: async () => ({ createWritable: async () => ({ write: async () => { throw new Error('disk full'); }, close: async () => assert.fail('不应关闭为成功'), abort: async () => { aborted = true; } }) }) };
  await assert.rejects(savePhoto(directory, photo), /disk full/);
  assert.equal(aborted, true);
});
// Even after write resolves, close may fail. The service must reject instead of
// returning a receipt, so App cannot display a false local-save success.
test('关闭写入流失败不能返回成功', async () => {
  const directory = { queryPermission: async () => 'granted', getFileHandle: async () => ({ createWritable: async () => ({ write: async () => {}, close: async () => { throw new Error('commit failed'); }, abort: async () => {} }) }) };
  await assert.rejects(savePhoto(directory, photo), /commit failed/);
});
