/** Operator-only browsing flow, separate from the patient capture state machine.
 * Search is read-only: opening groups never renames images or changes the index.
 */
import React, { useEffect, useRef, useState } from 'react';
import { getHistory, searchParameters, photoTime } from '../services/history';

function PhotoPreview({ group, index, onClose, onChange }) {
  const dialog = useRef(null);
  const photo = group.photos[index];
  useEffect(() => { dialog.current.showModal(); }, []);
  return <dialog ref={dialog} className="photo-dialog" onCancel={onClose} aria-label="Photo preview">
    <div className="history-heading"><h2>Photo {photo.sequence} / {group.photos.length}</h2><button className="text-button" onClick={onClose}>Close</button></div>
    <img src={`/api/v1/batches/${group.id}/photos/${photo.id}`} alt={`Photo ${photo.sequence}`} />
    <p>{photoTime(photo.captured_at)}</p><p className="filename">{group.id}</p>
    <div className="pagination"><button disabled={index === 0} onClick={() => onChange(index-1)}>Previous photo</button><button disabled={index === group.photos.length-1} onClick={() => onChange(index+1)}>Next photo</button></div>
  </dialog>;
}

export default function History({ onBack }) {
  const [draft, setDraft] = useState({ group: '', from: '', to: '' });
  const [query, setQuery] = useState({ ...draft, page: 1 });
  const [results, setResults] = useState(null), [selected, setSelected] = useState(null);
  const [detail, setDetail] = useState(null), [preview, setPreview] = useState(null);
  const [error, setError] = useState(''), [loading, setLoading] = useState(true), [revision, setRevision] = useState(0);
  useEffect(() => {
    // Abort the old request on navigation so slow responses cannot replace newer data.
    const controller = new AbortController();
    setLoading(true); setError(''); setDetail(null); setPreview(null);
    if (!selected) setResults(null);
    const path = selected ? `/api/v1/batches/${selected}` : `/api/v1/batch-search?${searchParameters(query)}`;
    getHistory(path, controller.signal).then(data => {
      if (!controller.signal.aborted) selected ? setDetail(data) : setResults(data);
    }).catch(err => { if (!controller.signal.aborted) setError(err.message); })
      .finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [query, selected, revision]);

  function search(event) {
    event.preventDefault();
    try { searchParameters(draft); setError(''); setQuery({ ...draft, page: 1 }); }
    catch (err) { setError(err.message); }
  }
  return <section className="history" aria-label="Photo library">
    <div className="history-heading"><h2>{selected ? 'Capture group' : 'Photo library'}</h2><button className="text-button" onClick={selected ? () => setSelected(null) : onBack}>{selected ? 'Back to results' : 'Back to capture'}</button></div>
    {!selected && <form className="history-filters" onSubmit={search}>
      <label>Group ID<input value={draft.group} maxLength={100} placeholder="Full or partial ID" onChange={e => setDraft({ ...draft, group: e.target.value })} /></label>
      <label>From<input type="date" value={draft.from} onChange={e => setDraft({ ...draft, from: e.target.value })} /></label>
      <label>Through<input type="date" value={draft.to} onChange={e => setDraft({ ...draft, to: e.target.value })} /></label>
      <button className="capture-button" type="submit">Search</button>
      <button className="text-button" type="button" onClick={() => { const empty = { group: '', from: '', to: '' }; setDraft(empty); setQuery({ ...empty, page: 1 }); }}>Clear</button>
    </form>}
    {!selected && <p className="history-note">Dates use this computer’s local time and the first photo in each group.</p>}
    {loading && <p role="status">Loading…</p>}
    {error && <div className="alert" role="alert">{error} <button className="text-button" onClick={() => setRevision(revision+1)}>Retry</button></div>}
    {!loading && !selected && results && <>
      <p role="status">{results.total} {results.total === 1 ? 'group' : 'groups'} found</p>
      {!results.items.length && <div className="empty-library">No groups found. Try a different ID or date range.</div>}
      <div className="group-list">{results.items.map(group => <button className="group-card" key={group.id} onClick={() => setSelected(group.id)}>
        <strong>{photoTime(group.captured_at)}</strong><span>{group.photo_count} photos</span><span className="filename">{group.id}</span><span className="group-open">View group →</span>
      </button>)}</div>
      {results.total > 0 && <nav className="pagination" aria-label="Search result pages"><button disabled={query.page === 1} onClick={() => setQuery({ ...query, page: query.page-1 })}>Previous</button><span>Page {query.page} / {Math.ceil(results.total/results.page_size)}</span><button disabled={query.page*results.page_size >= results.total} onClick={() => setQuery({ ...query, page: query.page+1 })}>Next</button></nav>}
    </>}
    {!loading && detail && <>
      <p className="filename">{detail.id}</p><p>{detail.photos.length} photos · {photoTime(detail.photos[0].captured_at)}</p>
      <div className="history-photos">{detail.photos.map((photo, index) => <button className="photo-card" key={photo.id} onClick={() => setPreview(index)}>
        <img loading="lazy" src={`/api/v1/batches/${detail.id}/photos/${photo.id}`} alt={`Photo ${photo.sequence}`} />
        <strong>Photo {photo.sequence}</strong><time dateTime={photo.captured_at}>{photoTime(photo.captured_at)}</time>
      </button>)}</div>
    </>}
    {detail && preview !== null && <PhotoPreview group={detail} index={preview} onChange={setPreview} onClose={() => setPreview(null)} />}
  </section>;
}
