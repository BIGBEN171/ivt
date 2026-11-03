/**
 * Application entry point and UI coordinator.
 * App owns React state and decides when to call the three service modules.
 * Services perform device/file operations or explain errors; they do not render UI.
 * Photos and directory handles live in this page's memory. No upload occurs here.
 */
import React, { useEffect, useRef, useState } from 'react';
import { createRoot } from 'react-dom/client';
import { openCamera, closeCamera, capturePhoto } from './services/camera';
import { chooseDirectory, savePhoto, supportsDirectorySaving } from './services/localStorage';
import { explainError } from './services/errors';
import './styles.css';

function App() {
  // Refs retain mutable values between renders without causing a new render.
  // videoRef points to the mounted <video>; streamRef retains the device stream.
  const videoRef = useRef(null);
  const streamRef = useRef(null);
  // Unlike a state update, this synchronous lock blocks a second click immediately.
  const lock = useRef(false);
  // An outstanding permission request may resolve after the component unmounts.
  const mounted = useRef(true);
  // State changes schedule React renders, updating labels and disabled controls.
  // Camera state: off | starting | ready. This is separate from saving state.
  const [camera, setCamera] = useState('off');
  // A FileSystemDirectoryHandle grants access to one user-selected directory.
  // It is not a path string and is not persisted across page sessions.
  const [directory, setDirectory] = useState(null);
  const [selecting, setSelecting] = useState(false);
  // Operation state: idle | capturing | saving | saved | failed.
  const [phase, setPhase] = useState('idle');
  // Photo is the object returned by capturePhoto; photoUrl is a temporary Blob URL.
  // A visible preview does not imply that the file has been saved successfully.
  const [photo, setPhoto] = useState(null);
  const [photoUrl, setPhotoUrl] = useState('');
  // An empty string hides the error alert. Services never set this state directly.
  const [error, setError] = useState('');

  // Derived conditions are recomputed on every render instead of stored separately.
  // API support is different from permission: writing still requires authorization.
  const supported = supportsDirectorySaving();
  const busy = phase === 'capturing' || phase === 'saving';
  // Preserve a failed photo for retry rather than allowing a new capture to replace it.
  const pending = photo && phase === 'failed';
  const ready = camera === 'ready' && directory && supported && !busy && !pending && !selecting;

  // Register unmount cleanup: invalidate late requests and release camera tracks.
  useEffect(() => () => { mounted.current = false; closeCamera(streamRef.current); }, []);
  // React runs this effect after photo changes. Revoke the previous URL when the
  // photo is replaced or App unmounts so its browser-managed reference is released.
  useEffect(() => {
    if (!photo) return;
    const url = URL.createObjectURL(photo.blob);
    setPhotoUrl(url);
    return () => URL.revokeObjectURL(url);
  }, [photo]);
  // Ask the browser to warn before leaving with work in progress or a failed save.
  // The browser controls whether/how this appears; it is not durable data storage.
  // Re-register when these conditions change so the handler sees current values.
  useEffect(() => {
    const warn = event => { if (busy || pending) { event.preventDefault(); event.returnValue = ''; } };
    window.addEventListener('beforeunload', warn);
    return () => window.removeEventListener('beforeunload', warn);
  }, [busy, pending]);

  /** Start preview and translate device failures into UI state and readable text. */
  async function startCamera() {
    if (camera === 'starting') return;
    setError(''); setCamera('starting');
    closeCamera(streamRef.current);
    try {
      // openCamera may wait for user permission. Do not keep its stream if the
      // page component disappeared while that request was pending.
      const stream = await openCamera();
      if (!mounted.current) { closeCamera(stream); return; }
      streamRef.current = stream;
      // Handle externally ended tracks, such as a device being disconnected.
      stream.getVideoTracks()[0].addEventListener('ended', () => { setCamera('off'); setError('The camera was disconnected. Please turn it on again.'); });
      // srcObject accepts a live MediaStream; it is not a file or a network URL.
      // Only mark the camera ready after playback has successfully started.
      videoRef.current.srcObject = stream;
      await videoRef.current.play();
      setCamera('ready');
    } catch (err) { closeCamera(streamRef.current); setCamera('off'); setError(explainError(err)); }
  }

  /** Choose a directory from a user gesture and retain the returned handle. */
  async function selectDirectory() {
    setSelecting(true);
    try { const chosen = await chooseDirectory(); setDirectory(chosen); setError(''); }
    // Cancelling the picker is not an application error; keep any previous handle.
    catch (err) { if (err.name !== 'AbortError') setError(explainError(err)); }
    finally { setSelecting(false); }
  }

  /**
   * Shared save coordinator for new captures and retries.
   * @param {import('./services/camera').Photo} currentPhoto - The photo to write.
   * Consumes savePhoto's success/failure but does not retain its receipt.
   * Save errors are handled here, not rethrown: phase becomes failed and the
   * in-memory photo remains available for retrySave.
   */
  async function persist(currentPhoto) {
    setPhase('saving');
    try { await savePhoto(directory, currentPhoto); setPhase('saved'); }
    catch (err) { setPhase('failed'); setError(explainError(err)); }
  }

  /** Handle the capture button: validate readiness, create a Photo, then save it. */
  async function takePhoto() {
    if (!ready || lock.current) return;
    lock.current = true; setError(''); setPhase('capturing');
    // Pass the local captured value directly to persist. setPhoto schedules a
    // render; reading photo immediately afterwards would still see the old state.
    try { const captured = await capturePhoto(videoRef.current); setPhoto(captured); await persist(captured); }
    // Capture failures return to idle; save failures are already handled in persist.
    catch (err) { setPhase('idle'); setError(explainError(err)); }
    // Always release the synchronous guard, whether capture succeeded or failed.
    finally { lock.current = false; }
  }

  /** Retry the same Blob/id/filename without requesting another video frame. */
  async function retrySave() {
    if (lock.current || selecting) return;
    lock.current = true; setError('');
    try { await persist(photo); } finally { lock.current = false; }
  }

  // Status priority: in progress, unsaved photo, device setup, folder setup, ready.
  // The current UI uses "Saving…" for both capturing and saving phases.
  const status = busy ? 'Saving…' : pending ? 'Not saved' : camera !== 'ready' ? 'Camera off' : !directory ? 'Choose a folder' : 'Ready';
  return <main>
    {/* JSX describes the UI for the current state; event handlers perform work. */}
    <header className="page-header">
      <h1>Clarity <span>Capture</span></h1>
      <span className={'status ' + (ready ? 'ready' : '')} role="status"><i aria-hidden="true"/>{status}</span>
    </header>
    <section className="capture-section" aria-label="Photo capture">
      <div className="viewfinder">
        {/* Keep the video mounted so startCamera can assign its stream through the ref. */}
        <video ref={videoRef} autoPlay muted playsInline aria-label="Live camera preview"/>
        {camera !== 'ready' && <div className="camera-placeholder">
          <svg viewBox="0 0 80 64" fill="none" aria-hidden="true"><path d="M9 17h15l5-9h22l5 9h15v39H9z" stroke="currentColor" strokeWidth="2" strokeLinejoin="round"/><circle cx="40" cy="36" r="12" stroke="currentColor" strokeWidth="2"/></svg>
          <p>{camera === 'starting' ? 'Connecting…' : 'Camera off'}</p>
        </div>}
      </div>
      <div id="setup" className="toolbar" aria-label="Camera and folder setup">
        {/* Setup controls are locked while capture/save or folder selection is active. */}
        <button className="text-button" disabled={camera === 'starting' || busy || selecting} onClick={() => {
          if (camera === 'ready') { closeCamera(streamRef.current); setCamera('off'); }
          else startCamera();
        }}>{camera === 'ready' ? 'Turn off camera' : camera === 'starting' ? 'Connecting…' : 'Turn on camera'}</button>
        <div className="folder-control">
          {/* Display only the directory's name, not a filesystem path. */}
          {directory && <span className="folder-name" title={directory.name}>{directory.name}</span>}
          <button className="text-button" onClick={selectDirectory} disabled={!supported || busy || selecting}>{selecting ? 'Choosing…' : directory ? 'Change folder' : 'Choose folder'}</button>
        </div>
      </div>
      {/* The disabled state guides the UI; takePhoto also checks readiness internally. */}
      <div className="capture-action"><button className="capture-button" onClick={takePhoto} disabled={!ready}>{busy ? 'Saving…' : 'Take photo'}</button></div>
      {!supported && <div className="alert" role="alert">Use desktop Chrome or Edge over HTTPS or localhost to save photos.</div>}
      {error && <div className="alert" role="alert">{error}{pending && ' Keep this page open until saved.'}</div>}
    </section>
    {/* A preview can appear while saving. Only phase === 'saved' confirms success.
        aria-live announces result changes without moving the user's focus. */}
    {photoUrl && <section className="result" aria-label="Latest photo" aria-live="polite">
      <img src={photoUrl} alt="Latest capture"/>
      <div className="result-detail">
        <h2>{phase === 'saved' ? 'Saved to folder' : phase === 'failed' ? 'Not saved' : 'Saving…'}</h2>
        <p className="filename">{photo.filename}</p>
        {pending && <button className="text-button" onClick={retrySave} disabled={selecting}>Retry save</button>}
      </div>
    </section>}
  </main>;
}

// Mount the single App component into the container declared in index.html.
createRoot(document.getElementById('root')).render(<App />);
