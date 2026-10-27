import { test } from 'node:test';
import assert from 'node:assert/strict';
import { savePhoto } from '../src/services/localStorage.js';

const photo = { filename: 'capture_fixed-id.png', blob: new Blob(['photo']) };
test('只有写入并关闭成功才返回保存回执；重试使用同一文件名', async () => {
  const calls = [];
  const directory = {
    queryPermission: async () => 'granted',
    getFileHandle: async name => {
      calls.push(name);
      return { createWritable: async () => ({ write: async data => { assert.equal(data, photo.blob); calls.push('write'); }, close: async () => calls.push('close') }) };
    },
  };
  const receipt = await savePhoto(directory, photo);
  assert.equal(receipt.filename, photo.filename);
  await savePhoto(directory, photo);
  assert.deepEqual(calls, [photo.filename, 'write', 'close', photo.filename, 'write', 'close']);
});
test('权限失效不创建文件', async () => {
  await assert.rejects(savePhoto({ queryPermission: async () => 'denied', getFileHandle: () => assert.fail('不应创建文件') }, photo), /permission has expired/);
});
test('写入失败中止流并保留错误', async () => {
  let aborted = false;
  const directory = { queryPermission: async () => 'granted', getFileHandle: async () => ({ createWritable: async () => ({ write: async () => { throw new Error('disk full'); }, close: async () => assert.fail('不应关闭为成功'), abort: async () => { aborted = true; } }) }) };
  await assert.rejects(savePhoto(directory, photo), /disk full/);
  assert.equal(aborted, true);
});
test('关闭写入流失败不能返回成功', async () => {
  const directory = { queryPermission: async () => 'granted', getFileHandle: async () => ({ createWritable: async () => ({ write: async () => {}, close: async () => { throw new Error('commit failed'); }, abort: async () => {} }) }) };
  await assert.rejects(savePhoto(directory, photo), /commit failed/);
});
