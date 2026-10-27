export function supportsDirectorySaving() {
  return window.isSecureContext && typeof window.showDirectoryPicker === 'function';
}

export async function chooseDirectory() {
  if (!supportsDirectorySaving()) throw new Error('Folder saving is not supported. Please use desktop Chrome or Edge.');
  return window.showDirectoryPicker({ mode: 'readwrite', id: 'capture-output' });
}

export async function savePhoto(directory, photo) {
  if (!directory) throw new Error('Please choose a save folder first.');
  const permission = await directory.queryPermission({ mode: 'readwrite' });
  if (permission !== 'granted') throw new Error('Folder permission has expired. Choose and authorize the folder again, then retry saving.');
  const file = await directory.getFileHandle(photo.filename, { create: true });
  const writable = await file.createWritable();
  try {
    await writable.write(photo.blob);
    await writable.close();
  } catch (error) {
    await writable.abort().catch(() => {});
    throw error;
  }
  return { filename: photo.filename, savedAt: new Date().toISOString() };
}
