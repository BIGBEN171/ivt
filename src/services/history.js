/** Date filters use local calendar days, including the entire selected end day.
 * Convert to UTC at the browser boundary so backend host timezone is irrelevant.
 */
export function searchParameters({ group = '', from = '', to = '', page = 1 }) {
  if (from && to && from > to) throw new Error('End date must be on or after start date.');
  const params = new URLSearchParams({ group: group.trim(), page: String(page), page_size: '20' });
  for (const [value, name, extraDay] of [[from, 'start', 0], [to, 'end', 1]]) {
    if (value) {
      const [year, month, day] = value.split('-').map(Number);
      // Construct local midnight rather than parsing YYYY-MM-DD as UTC.
      const date = new Date(year, month - 1, day + extraDay);
      if (!Number.isFinite(date.getTime())) throw new Error('Please choose a valid date.');
      params.set(name, date.toISOString());
    }
  }
  return params;
}

export async function getHistory(path, signal) {
  const response = await fetch(path, { signal, cache: 'no-store' });
  if (!response.ok) throw new Error(response.status === 404 ? 'This group could not be found.' : 'Could not load photos. Check the local server and retry.');
  return response.json();
}

/** Display milliseconds, keeping sampling order visible even for fast bursts. */
export function photoTime(value) {
  return new Date(value).toLocaleString(undefined, {
    year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit',
    minute: '2-digit', second: '2-digit', fractionalSecondDigits: 3, hour12: false,
  });
}
