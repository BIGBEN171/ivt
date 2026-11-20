"""Search respects capture timestamps, UTC offsets, literal IDs and page boundaries."""
from backend.config import Settings
from backend.main import create_app
from fastapi.testclient import TestClient
from test_batches import payload, send


def test_search_capture_time_offsets_and_id(tmp_path):
    early, image = payload()
    late, _ = payload()
    # Save the newer capture first to make insertion/save order misleading.
    for p in early['photos']:
        p['capturedAt'] = '2026-11-19T23:59:59+08:00'
    for p in late['photos']:
        p['capturedAt'] = '2026-11-20T00:00:00+08:00'
    with TestClient(create_app(Settings(data_dir=tmp_path))) as client:
        assert send(client, late, image).status_code == 201
        assert send(client, early, image).status_code == 201
        url = '/api/v1/batch-search'
        result = client.get(url, params={'page_size': 1}).json()
        assert result['total'] == 2
        assert result['items'][0]['id'] == late['id']
        assert result['items'][0]['photo_count'] == 15
        assert client.get(url, params={'page_size': 1, 'page': 2}).json()['items'][0]['id'] == early['id']
        assert client.get(url, params={'group': late['id'][:12].upper()}).json()['total'] == 1
        assert client.get(url, params={'group': "%' OR 1=1 --"}).json()['total'] == 0
        # Nov 20 in UTC+8 starts at Nov 19 16:00 UTC; upper bound is exclusive.
        window = {'start': '2026-11-19T16:00:00Z', 'end': '2026-11-20T16:00:00Z'}
        filtered = client.get(url, params=window).json()
        assert [r['id'] for r in filtered['items']] == [late['id']]
        assert client.get(url, params={'end': window['start']}).json()['items'][0]['id'] == early['id']
        assert client.get(url, params={'start': window['end'], 'end': window['start']}).status_code == 422
        assert client.get(url, params={'start': '2026-11-20T00:00:00'}).status_code == 422
        assert client.get(url, params={'page': 0}).status_code == 422
        assert client.get(url, params={'page_size': 101}).status_code == 422
        assert client.get(url, params={'group': late['id'], **window}).json()['total'] == 1
        assert client.get(url, params={'group': early['id'], **window}).json()['total'] == 0
