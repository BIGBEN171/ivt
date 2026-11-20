import test from 'node:test';
import assert from 'node:assert/strict';
import { searchParameters } from '../src/services/history.js';

test('date filters use local midnight and include the entire last day', () => {
  const params = searchParameters({ group: ' abcd ', from: '2026-11-20', to: '2026-11-20', page: 2 });
  assert.equal(params.get('start'), new Date(2026, 10, 20).toISOString());
  assert.equal(params.get('end'), new Date(2026, 10, 21).toISOString());
  assert.equal(params.get('group'), 'abcd');
  assert.equal(params.get('page'), '2');
});

test('empty date filters impose no time restriction and reversed dates are rejected', () => {
  assert.equal(searchParameters({}).has('start'), false);
  assert.equal(searchParameters({}).has('end'), false);
  assert.throws(() => searchParameters({ from: '2026-11-21', to: '2026-11-20' }), /End date/);
});
