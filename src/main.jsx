/** Local kiosk flow: start -> camera readiness -> countdown -> burst -> durable save.
 * The synchronous lock prevents double clicks before React re-renders.
 * A failed save retains the original batch in memory for an idempotent retry.
 */
import React, { useEffect, useRef, useState } from 'react';
import { createRoot } from 'react-dom/client';
import { openCamera, closeCamera } from './services/camera';
import { captureBatch } from './services/burst';
import { uploadBatch } from './services/api';
import './styles.css';

function App() {
  const video = useRef(null), stream = useRef(null), locked = useRef(false), abort = useRef(null);
  const [phase, setPhase] = useState('start'), [countdown, setCountdown] = useState(3);
  const [count, setCount] = useState(0), [batch, setBatch] = useState(null), [receipt, setReceipt] = useState(null), [error, setError] = useState('');
  const busy = ['connecting', 'countdown', 'capturing', 'saving'].includes(phase);
  useEffect(() => () => { abort.current?.abort(); closeCamera(stream.current); }, []);
  useEffect(() => {
    // Browser warnings are best effort; memory does not survive a page reload.
    const warn = event => { if (busy || batch && phase === 'failed') { event.preventDefault(); event.returnValue = ''; } };
    window.addEventListener('beforeunload', warn);
    return () => window.removeEventListener('beforeunload', warn);
  }, [busy, batch, phase]);

  async function save(current) {
    setPhase('saving');
    try { setReceipt(await uploadBatch(current)); setPhase('done'); setBatch(null); }
    catch (err) { setError(err.message); setPhase('failed'); }
  }

  async function start() {
    if (locked.current) return;
    locked.current = true; setError(''); setCount(0); setReceipt(null); setPhase('connecting');
    abort.current = new AbortController();
    try {
      stream.current = await openCamera();
      if (abort.current.signal.aborted) throw new Error('Capture cancelled.');
      video.current.srcObject = stream.current;
      await video.current.play();
      // Start the three-second countdown only after camera permission and playback.
      setPhase('countdown');
      for (let remaining = 3; remaining > 0; remaining--) {
        setCountdown(remaining);
        await new Promise(resolve => setTimeout(resolve, 1000));
        if (abort.current.signal.aborted || document.hidden) throw new Error('Capture interrupted. Keep this window visible and start again.');
      }
      setPhase('capturing');
      const captured = await captureBatch(video.current, { signal: abort.current.signal, onProgress: setCount });
      setBatch(captured); closeCamera(stream.current);
      await save(captured);
    } catch (err) { setError(err.message); setPhase('start'); }
    finally { closeCamera(stream.current); locked.current = false; }
  }

  async function retry() {
    if (locked.current || !batch) return;
    locked.current = true; setError('');
    try { await save(batch); } finally { locked.current = false; }
  }

  return <main>
    <header className="page-header"><h1>Clarity <span>Capture</span></h1><span className="status">Local capture</span></header>
    {/* Keep the video mounted while connecting; hide it only with presentation styles. */}
    <section className="viewfinder" hidden={!busy || phase === 'saving'}>
      <video ref={video} autoPlay muted playsInline aria-label="Live camera preview" />
      <div className="burst-overlay" role="status">{phase === 'connecting' ? 'Connecting…' : phase === 'countdown' ? countdown : `${count} / 15`}</div>
    </section>
    {phase === 'start' && <section className="start-screen"><h2>Ready when you are.</h2><p>3 seconds. 15 photos.</p><button className="capture-button" onClick={start}>Start</button></section>}
    {phase === 'saving' && <section className="start-screen" role="status"><h2>Saving 15 photos…</h2><p>Keep this window open.</p></section>}
    {phase === 'failed' && <section className="start-screen"><h2>Photos not yet confirmed saved</h2><button className="capture-button" onClick={retry}>Retry save</button></section>}
    {phase === 'done' && <section className="start-screen"><h2>15 photos saved.</h2><p className="filename">{receipt.id}</p><button className="capture-button" onClick={() => setPhase('start')}>Next session</button><div className="photo-grid">{receipt.photos.map(photo => <img key={photo.id} src={`/api/v1/batches/${receipt.id}/photos/${photo.id}`} alt={`Photo ${photo.sequence}`} />)}</div></section>}
    {error && <div className="alert" role="alert">{error}</div>}
  </main>;
}
createRoot(document.getElementById('root')).render(<App />);
