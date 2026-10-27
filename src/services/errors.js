export function explainError(error) {
  const messages = {
    NotAllowedError: 'Access was not granted. Check camera or folder permissions in your browser.',
    NotFoundError: 'The camera or folder could not be found. Check the connection and try again.',
    NotReadableError: 'The camera may be in use. Close other apps using it and try again.',
    QuotaExceededError: 'There is not enough storage space. Free up space and retry saving.',
    AbortError: 'The operation was interrupted. Please try again.',
    SecurityError: 'Access was blocked. Check your browser permissions and use HTTPS or localhost.',
    InvalidStateError: 'The device or file is not ready. Please try again.',
  };
  const message = error?.message;
  // Do not expose localized browser errors as untranslated application copy.
  return messages[error?.name] || (message && !/\p{Script=Han}/u.test(message) ? message : 'Something went wrong. Check your camera and folder access, then try again.');
}
