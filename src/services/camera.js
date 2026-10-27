export async function openCamera() {
  if (!window.isSecureContext || !navigator.mediaDevices?.getUserMedia) {
    throw new Error('Open this page using localhost or HTTPS to access the camera.');
  }
  return navigator.mediaDevices.getUserMedia({ audio: false, video: { width: { ideal: 1920 }, height: { ideal: 1080 }, facingMode: 'user' } });
}

export function closeCamera(stream) {
  stream?.getTracks().forEach(track => track.stop());
}

export async function capturePhoto(video) {
  if (video.readyState < 2 || !video.videoWidth || !video.videoHeight) throw new Error('The camera preview is not ready. Please try again shortly.');
  const canvas = document.createElement('canvas');
  canvas.width = video.videoWidth;
  canvas.height = video.videoHeight;
  canvas.getContext('2d').drawImage(video, 0, 0);
  const blob = await new Promise(resolve => canvas.toBlob(resolve, 'image/png'));
  if (!blob) throw new Error('The photo could not be created. Please take another photo.');
  const id = crypto.randomUUID();
  const capturedAt = new Date().toISOString();
  return { id, capturedAt, blob, width: canvas.width, height: canvas.height, filename: `capture_${capturedAt.replace(/[:.]/g, '-')}_${id}.png` };
}
