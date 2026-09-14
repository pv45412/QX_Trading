export function csvCell(value) {
  if (value == null) return '';
  let text = String(value);
  // Prevent spreadsheet formulas in imported text while preserving numeric values.
  if (typeof value === 'string' && /^[\s]*[=+@-]/.test(text)) text = `'${text}`;
  return `"${text.replaceAll('"', '""')}"`;
}

export function rankingCsv(rows) {
  const fields = ['etf', 'sector', 'relative_5d', 'relative_20d', 'relative_60d'];
  return [fields.join(','), ...rows.map(row => fields.map(key => csvCell(row[key])).join(','))].join('\r\n');
}

const easternTime = new Intl.DateTimeFormat('en-US', {
  timeZone: 'America/New_York', year: 'numeric', month: 'short', day: '2-digit',
  hour: '2-digit', minute: '2-digit', hour12: true, timeZoneName: 'short',
});

export function formatTimestampET(value) {
  if (typeof value !== 'string') return 'Unavailable';
  const match = /^(\d{4}-\d{2}-\d{2})(?:[T ](\d{2}):(\d{2}):(\d{2})(\.\d{1,6})?(Z|[+-]\d{2}:\d{2})?)?$/.exec(value);
  if (!match) return 'Unavailable';
  const day = new Date(`${match[1]}T00:00:00Z`);
  if (!Number.isFinite(day.getTime()) || day.toISOString().slice(0,10) !== match[1]) return 'Unavailable';
  if (!match[2]) return match[1];
  if (+match[2] > 23 || +match[3] > 59 || +match[4] > 59) return 'Unavailable';
  // Match the legacy Python storage contract: a naive timestamp means UTC.
  const instant = new Date(`${match[1]}T${match[2]}:${match[3]}:${match[4]}${match[5] || ''}${match[6] || 'Z'}`);
  return Number.isFinite(instant.getTime()) ? easternTime.format(instant) : 'Unavailable';
}

export function safeGet(obj, key, fallback = null) {
  if (obj == null || typeof obj !== 'object') return fallback;
  const val = obj[key];
  return val !== undefined && val !== null ? val : fallback;
}

export function safeNumber(obj, key, fallback = 0.0) {
  const val = safeGet(obj, key, fallback);
  const num = Number(val);
  return Number.isFinite(num) ? num : fallback;
}

export function validatePayloadKeys(payload, requiredKeys = []) {
  if (payload == null || typeof payload !== 'object') return { valid: false, missing: requiredKeys };
  const missing = requiredKeys.filter(k => !(k in payload) || payload[k] === undefined);
  return { valid: missing.length === 0, missing };
}

