/**
 * Local filesystem service using the browser's File System Access APIs.
 * Despite this filename, this module does NOT use window.localStorage.
 * It receives Photo objects from App and has no camera or React dependency.
 */

/** @returns {boolean} Whether the required picker API is available in this context. */
export function supportsDirectorySaving() {
  return window.isSecureContext && typeof window.showDirectoryPicker === 'function';
}

/**
 * Called from the operator's button click so the browser can show its picker.
 * @returns {Promise<FileSystemDirectoryHandle>} The user-selected directory handle.
 * Cancellation rejects with AbortError; App decides to ignore that specific error.
 */
export async function chooseDirectory() {
  if (!supportsDirectorySaving()) throw new Error('Folder saving is not supported. Please use desktop Chrome or Edge.');
  // The id groups picker usage; it does not persist permission in application state.
  return window.showDirectoryPicker({ mode: 'readwrite', id: 'capture-output' });
}

/**
 * Write a PNG and resolve only after the writable stream closes successfully.
 * @param {FileSystemDirectoryHandle} directory - Previously selected directory.
 * @param {import('./camera').Photo} photo - Blob and stable filename to save.
 * @returns {Promise<{filename: string, savedAt: string}>} A completed-write receipt.
 * Failures reject; App retains the Photo in memory and offers an explicit retry.
 */
export async function savePhoto(directory, photo) {
  if (!directory) throw new Error('Please choose a save folder first.');
  // Permission can expire after selection. Query it before creating a file;
  // if absent, ask the operator to select/authorize again through the UI.
  const permission = await directory.queryPermission({ mode: 'readwrite' });
  if (permission !== 'granted') throw new Error('Folder permission has expired. Choose and authorize the folder again, then retry saving.');
  // create:true creates a missing file or obtains the existing one. Retrying a
  // Photo targets the same filename instead of creating a new capture identity.
  const file = await directory.getFileHandle(photo.filename, { create: true });
  const writable = await file.createWritable();
  try {
    await writable.write(photo.blob);
    // write() alone is insufficient: close() can also fail while committing data.
    await writable.close();
  } catch (error) {
    // Attempt cleanup, but preserve the original write/close failure even if abort
    // itself fails. Failure to obtain a handle/stream also propagates to the caller.
    await writable.abort().catch(() => {});
    throw error;
  }
  // This receipt is about local saving only; it says nothing about cloud storage.
  return { filename: photo.filename, savedAt: new Date().toISOString() };
}
