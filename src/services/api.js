/** HTTP adapter: send a browser Photo to the Python storage API.
 * The browser owns capture; the server owns durable image storage.
 * Reuse the same ID and bytes on retries so a lost response cannot create duplicates.
 */
export async function uploadPhoto(photo, fetcher = fetch) {
  const form = new FormData();
  form.append('photo_id', photo.id);
  form.append('captured_at', photo.capturedAt);
  form.append('file', photo.blob, photo.filename);
  let response;
  try {
    // Do not set Content-Type: the browser must include its multipart boundary.
    response = await fetcher('/api/v1/photos', {
      method: 'POST', body: form, signal: AbortSignal.timeout(60000),
    });
  } catch {
    throw new Error('Upload interrupted. Keep this page open and retry saving.');
  }
  if (!response.ok) {
    const messages = {
      413: 'The photo is too large to save.',
      415: 'The server accepts PNG photos only.',
      409: 'This photo ID already belongs to different content.',
      422: 'The server could not validate this photo.',
    };
    throw new Error(messages[response.status] || 'The server could not save the photo. Please retry.');
  }
  const receipt = await response.json();
  // Display success only after a matching server receipt, never just an HTTP response.
  if (receipt?.photo?.id !== photo.id || receipt.photo.size_bytes !== photo.blob.size) {
    throw new Error('The server returned an unexpected receipt. Please retry saving.');
  }
  return receipt.photo;
}

/** Upload one complete batch. Reusing its identity makes save retries idempotent. */
export async function uploadBatch(batch, fetcher = fetch) {
  const form = new FormData();
  form.append('manifest', JSON.stringify({ id: batch.id, photos: batch.photos.map(({ blob, ...metadata }) => metadata) }));
  for (const photo of batch.photos) form.append('files', photo.blob, `${photo.id}.png`);
  let response;
  try {
    response = await fetcher('/api/v1/batches', { method: 'POST', body: form, signal: AbortSignal.timeout(120000) });
  } catch { throw new Error('Saving was interrupted. Keep this page open and retry.'); }
  if (!response.ok) throw new Error(response.status === 409 ? 'Batch identity conflict. Keep this page open and contact the operator.' : 'Could not save this batch. Keep this page open and retry.');
  const receipt = await response.json();
  if (receipt.id !== batch.id || receipt.photos?.length !== 15 || !receipt.photos.every((photo, i) => photo.id === batch.photos[i].id && photo.size_bytes === batch.photos[i].blob.size)) throw new Error('Unexpected save receipt. Please retry.');
  return receipt;
}
