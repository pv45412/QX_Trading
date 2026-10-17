import React from 'react';

export function evidenceAttributes({source, dataAsOf, freshness, retrievedAt} = {}) {
  return {
    'data-evidence-region': 'true',
    'data-evidence-source': text(source),
    'data-evidence-as-of': text(dataAsOf),
    'data-evidence-freshness': text(freshness),
    'data-evidence-retrieved-at': text(retrievedAt),
  };
}

export default function QXDataEvidence({source, dataAsOf, freshness, retrievedAt, label = 'Evidence'}) {
  return <p className="qx-data-evidence" {...evidenceAttributes({source, dataAsOf, freshness, retrievedAt})}>
    <strong>{label}</strong>
    <span>Source {text(source)}</span>
    <span>As of {formatEvidenceTimestamp(dataAsOf)}</span>
    <span>Freshness {text(freshness)}</span>
    {retrievedAt && <span>Retrieved {formatEvidenceTimestamp(retrievedAt)}</span>}
  </p>;
}

function text(value) {
  return value == null || String(value).trim() === '' ? 'UNAVAILABLE' : String(value);
}

export function formatEvidenceTimestamp(value) {
  if (!value) return 'UNAVAILABLE';
  const parsed = new Date(value);
  if (!Number.isFinite(parsed.getTime())) return String(value);
  if (/^\d{4}-\d{2}-\d{2}T00:00:00(?:\.0+)?Z$/.test(String(value))) {
    return parsed.toLocaleDateString(undefined, {timeZone: 'UTC'});
  }
  return parsed.toLocaleString();
}
