/** React coordinates browser capture and HTTP persistence.
 * Camera hardware remains in the browser. The Python API stores the resulting PNG.
 * An unsaved photo stays in memory for retry; refreshing would discard that copy.
 */
import React, { useEffect, useRef, useState } from 'react';
import { createRoot } from 'react-dom/client';
import { openCamera, closeCamera, capturePhoto } from './services/camera';
import { uploadPhoto } from './services/api';
import { explainError } from './services/errors';
import './styles.css';

function App() {
  const videoRef = useRef(null);
  const streamRef = useRef(null);
  // React state updates are asynchronous; this lock prevents overlapping clicks.
  const lock = useRef(false);
  const mounted = useRef(true);
  const [camera, setCamera] = useState('off');
  const [phase, setPhase] = useState('idle');
  const [photo, setPhoto] = useState(null);
  const [photoUrl, setPhotoUrl] = useState('');
  const [receipt, setReceipt] = useState(null);
  const [error, setError] = useState('');
  const busy = phase === 'capturing' || phase === 'saving';
  const pending = photo && phase === 'failed';
  const ready = camera === 'ready' && !busy && !pending;

  useEffect(() => () => { mounted.current = false; closeCamera(streamRef.current); }, []);
  useEffect(() => {
    if (!photo) return;
    const url = URL.createObjectURL(photo.blob);
    setPhotoUrl(url);
    return () => URL.revokeObjectURL(url);
  }, [photo]);
  useEffect(() => {
    // This warning is best-effort; the browser does not durably queue failed uploads.
    const warn = event => { if (busy || pending) { event.preventDefault(); event.returnValue = ''; } };
    window.addEventListener('beforeunload', warn);
    return () => window.removeEventListener('beforeunload', warn);
  }, [busy, pending]);

  async function startCamera() {
    if (camera === 'starting') return;
    setError(''); setCamera('starting');
    closeCamera(streamRef.current);
    try {
      const stream = await openCamera();
      if (!mounted.current) { closeCamera(stream); return; }
      streamRef.current = stream;
      stream.getVideoTracks()[0].addEventListener('ended', () => {
        setCamera('off'); setError('The camera was disconnected. Please turn it on again.');
      });
      videoRef.current.srcObject = stream;
      await videoRef.current.play();
      setCamera('ready');
    } catch (err) {
      closeCamera(streamRef.current); setCamera('off'); setError(explainError(err));
    }
  }

  /** Wait for the server to confirm durable storage before showing success. */
  async function persist(currentPhoto) {
    setPhase('saving'); setReceipt(null);
    try {
      const saved = await uploadPhoto(currentPhoto);
      setReceipt(saved); setPhase('saved');
    } catch (err) { setPhase('failed'); setError(err.message); }
  }

  async function takePhoto() {
    if (!ready || lock.current) return;
    lock.current = true; setError(''); setReceipt(null); setPhase('capturing');
    try {
      const captured = await capturePhoto(videoRef.current);
      setPhoto(captured);
      await persist(captured);
    } catch (err) { setPhase('idle'); setError(explainError(err)); }
    finally { lock.current = false; }
  }

  /** Retry the original ID, timestamp and Blob without taking another photograph. */
  async function retrySave() {
    if (lock.current || !pending) return;
    lock.current = true; setError('');
    try { await persist(photo); } finally { lock.current = false; }
  }

  const status = busy ? 'Saving…' : pending ? 'Not saved' : camera !== 'ready' ? 'Camera off' : 'Ready';
  return <main>
    <header className="page-header">
      <h1>Clarity <span>Capture</span></h1>
      <span className={'status ' + (ready ? 'ready' : '')} role="status"><i aria-hidden="true"/>{status}</span>
    </header>
    <section className="capture-section" aria-label="Photo capture">
      <div className="viewfinder">
        <video ref={videoRef} autoPlay muted playsInline aria-label="Live camera preview"/>
        {camera !== 'ready' && <div className="camera-placeholder">
          <svg viewBox="0 0 80 64" fill="none" aria-hidden="true"><path d="M9 17h15l5-9h22l5 9h15v39H9z" stroke="currentColor" strokeWidth="2" strokeLinejoin="round"/><circle cx="40" cy="36" r="12" stroke="currentColor" strokeWidth="2"/></svg>
          <p>{camera === 'starting' ? 'Connecting…' : 'Camera off'}</p>
        </div>}
      </div>
      <div id="setup" className="toolbar" aria-label="Camera setup">
        <button className="text-button" disabled={camera === 'starting' || busy} onClick={() => {
          if (camera === 'ready') { closeCamera(streamRef.current); setCamera('off'); }
          else startCamera();
        }}>{camera === 'ready' ? 'Turn off camera' : camera === 'starting' ? 'Connecting…' : 'Turn on camera'}</button>
      </div>
      <div className="capture-action"><button className="capture-button" onClick={takePhoto} disabled={!ready}>{busy ? 'Saving…' : 'Take photo'}</button></div>
      {error && <div className="alert" role="alert">{error}{pending && ' Keep this page open until saved.'}</div>}
    </section>
    {photoUrl && <section className="result" aria-label="Latest photo" aria-live="polite">
      <img src={photoUrl} alt="Latest capture"/>
      <div className="result-detail">
        <h2>{phase === 'saved' && receipt ? 'Saved to server' : phase === 'failed' ? 'Not saved' : 'Saving…'}</h2>
        <p className="filename">{receipt ? receipt.id : photo.filename}</p>
        {pending && <button className="text-button" onClick={retrySave}>Retry save</button>}
      </div>
    </section>}
  </main>;
}

createRoot(document.getElementById('root')).render(<App />);
