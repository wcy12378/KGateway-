import { describe, expect, it } from 'vitest';
import { parseStoredSessions } from './sessions';

describe('parseStoredSessions', () => {
  it.each([null, 'null', '{}', '[{"id":1}]', 'not-json'])(
    'falls back to an empty list for invalid storage: %s',
    (value) => {
      expect(parseStoredSessions(value)).toEqual([]);
    }
  );

  it('keeps valid session entries', () => {
    const entry = { id: 'session-1', label: '会话 1', timestamp: 123 };
    expect(parseStoredSessions(JSON.stringify([entry]))).toEqual([entry]);
  });
});
