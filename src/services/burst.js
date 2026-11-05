/** Capture fifteen distinct presented frames, then encode them outside the burst.
 * requestVideoFrameCallback follows the video timeline rather than a wall-clock timer.
 * This does not guarantee sensor-frame completeness: the browser may drop frames.
 */
export function collectFrames(video, { count = 15, signal, onProgress = () => {} } = {}) {
  if (!video.requestVideoFrameCallback) throw new Error('Use a recent desktop Chrome or Edge for frame-based capture.');
  return new Promise((resolve, reject) => {
    const frames = [];
    let callback, lastTime = -Infinity, finished = false;
    const cleanup = () => {
      clearTimeout(timeout);
      video.cancelVideoFrameCallback(callback);
      signal?.removeEventListener('abort', abort);
      document.removeEventListener('visibilitychange', visibility);
    };
    const fail = error => { if (!finished) { finished = true; cleanup(); reject(error); } };
    const abort = () => fail(new Error('Capture cancelled. No complete batch was saved.'));
    const visibility = () => { if (document.hidden) fail(new Error('Keep this window visible during capture. Please start again.')); };
    // A stopped camera must not leave the patient waiting indefinitely.
    const timeout = setTimeout(() => fail(new Error('Camera frames stopped arriving. Please start again.')), 15000);
    signal?.addEventListener('abort', abort, { once: true });
    document.addEventListener('visibilitychange', visibility);
    const receive = (now, metadata) => {
      if (finished) return;
      try {
        if (metadata.mediaTime > lastTime) {
          const width = video.videoWidth, height = video.videoHeight;
          // Bound raw canvas memory before retaining a complete burst.
          if (!width || !height || width * height * 4 * count > 256 * 1024 ** 2) throw new Error('Camera resolution is too large for burst capture.');
          const canvas = document.createElement('canvas');
          canvas.width = width; canvas.height = height;
          const capturedAt = new Date().toISOString();
          canvas.getContext('2d').drawImage(video, 0, 0);
          frames.push({ canvas, capturedAt, mediaTimeMs: metadata.mediaTime * 1000, capturedMonotonicMs: now, presentedFrames: metadata.presentedFrames });
          lastTime = metadata.mediaTime;
          onProgress(frames.length);
        }
        if (frames.length === count) { finished = true; cleanup(); resolve(frames); }
        else callback = video.requestVideoFrameCallback(receive);
      } catch (error) { fail(error); }
    };
    if (signal?.aborted) abort();
    else if (document.hidden) visibility();
    else callback = video.requestVideoFrameCallback(receive);
  });
}

/** Encode captured canvases sequentially to limit peak PNG encoder memory usage. */
export async function captureBatch(video, options) {
  const frames = await collectFrames(video, options);
  const batch = { id: crypto.randomUUID(), photos: [] };
  try {
    for (const [index, frame] of frames.entries()) {
      if (options.signal?.aborted) throw new Error('Capture cancelled.');
      const blob = await new Promise(resolve => frame.canvas.toBlob(resolve, 'image/png'));
      if (!blob) throw new Error('Image encoding failed. Please start again.');
      const { canvas, ...timing } = frame;
      batch.photos.push({ id: crypto.randomUUID(), sequence: index + 1, ...timing, width: canvas.width, height: canvas.height, blob });
      canvas.width = canvas.height = 0;
    }
    return batch;
  } finally {
    // Release large raw buffers on both successful and interrupted encoding.
    for (const frame of frames) frame.canvas.width = frame.canvas.height = 0;
  }
}
