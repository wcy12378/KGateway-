export interface SessionEntry {
  id: string;
  label: string;
  timestamp: number;
}

function isSessionEntry(value: unknown): value is SessionEntry {
  if (!value || typeof value !== 'object') return false;
  const entry = value as Record<string, unknown>;
  return typeof entry.id === 'string'
    && typeof entry.label === 'string'
    && typeof entry.timestamp === 'number'
    && Number.isFinite(entry.timestamp);
}

export function parseStoredSessions(value: string | null): SessionEntry[] {
  if (!value) return [];
  try {
    const parsed: unknown = JSON.parse(value);
    return Array.isArray(parsed) ? parsed.filter(isSessionEntry) : [];
  } catch {
    return [];
  }
}
