/**
 * Device service: creates/stops video streams and converts video frames to images.
 * It has no dependency on React, directory handles, or the storage service.
 * Errors propagate to App, which chooses the UI response.
 *
 * @typedef {Object} Photo
 * @property {string} id - UUID identifying this capture across save retries.
 * @property {string} capturedAt - UTC ISO timestamp recorded after PNG encoding.
 * @property {Blob} blob - Encoded PNG bytes held in browser memory.
 * @property {number} width - Actual source frame width in pixels.
 * @property {number} height - Actual source frame height in pixels.
 * @property {string} filename - Filesystem-friendly timestamp plus UUID and .png.
 */

/** @returns {Promise<MediaStream>} A permission-approved video-only stream. */
export async function openCamera() {
  // Camera access requires an eligible secure context (such as HTTPS or localhost).
  if (!window.isSecureContext || !navigator.mediaDevices?.getUserMedia) {
    throw new Error('Open this page using localhost or HTTPS to access the camera.');
  }
  // "ideal" requests a preferred resolution, not a guaranteed output size.
  // No microphone is requested. App attaches the returned stream to its video.
  return navigator.mediaDevices.getUserMedia({ audio: false, video: { width: { ideal: 1920 }, height: { ideal: 1080 }, facingMode: 'user' } });
}

/** @param {MediaStream|null|undefined} stream - A stream to release, if present. */
export function closeCamera(stream) {
  // Stop all tracks. Updating React's camera state remains the caller's job.
  stream?.getTracks().forEach(track => track.stop());
}

/**
 * Capture the current preview frame, without saving or uploading it.
 * @param {HTMLVideoElement} video - The mounted preview with available frame data.
 * @returns {Promise<Photo>} A data object shared with App and the storage service.
 */
export async function capturePhoto(video) {
  // readyState >= 2 means current frame data is available; dimensions must be valid.
  if (video.readyState < 2 || !video.videoWidth || !video.videoHeight) throw new Error('The camera preview is not ready. Please try again shortly.');
  const canvas = document.createElement('canvas');
  // Use intrinsic frame dimensions, not the CSS display size of the preview.
  canvas.width = video.videoWidth;
  canvas.height = video.videoHeight;
  // Copy the frame without mirroring, cropping, or beautification.
  canvas.getContext('2d').drawImage(video, 0, 0);
  // Wrap the callback API in a Promise so the coordinator can await PNG encoding.
  // PNG adds no lossy encoding, but cannot improve the camera's source quality.
  const blob = await new Promise(resolve => canvas.toBlob(resolve, 'image/png'));
  if (!blob) throw new Error('The photo could not be created. Please take another photo.');
  const id = crypto.randomUUID();
  const capturedAt = new Date().toISOString();
  // Remove colons/dots from the timestamp for filename compatibility, including
  // Windows. Keep the full UUID; retrySave reuses this filename and the same Blob.
  return { id, capturedAt, blob, width: canvas.width, height: canvas.height, filename: `capture_${capturedAt.replace(/[:.]/g, '-')}_${id}.png` };
}
