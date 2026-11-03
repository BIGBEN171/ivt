/**
 * Presentation-independent error translator. App displays the returned string.
 * This function neither retries operations nor changes application state.
 * @param {Error|DOMException|undefined} error - A service/browser failure.
 * @returns {string} A user-facing message for the English application UI.
 */
export function explainError(error) {
  // Browser error names are more stable than their localized message strings.
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
  // Prefer a known mapping, then a non-empty message without Han characters.
  // The Han check avoids Chinese fallback text; it is not a full language detector.
  // Missing or rejected fallback messages use the generic English instruction.
  return messages[error?.name] || (message && !/\p{Script=Han}/u.test(message) ? message : 'Something went wrong. Check your camera and folder access, then try again.');
}
