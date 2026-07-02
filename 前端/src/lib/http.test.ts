// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from 'vitest';
import { isTokenExpired, requestJson } from './http';

function tokenWithExpiry(exp: number): string {
  const payload = btoa(JSON.stringify({ exp }))
    .replaceAll('+', '-')
    .replaceAll('/', '_')
    .replace(/=+$/, '');
  return `header.${payload}.signature`;
}

describe('isTokenExpired', () => {
  it('rejects malformed tokens', () => {
    expect(isTokenExpired('not-a-jwt')).toBe(true);
  });

  it('rejects expired tokens', () => {
    expect(isTokenExpired(tokenWithExpiry(Math.floor(Date.now() / 1000) - 1))).toBe(true);
  });

  it('accepts tokens whose expiry is still in the future', () => {
    expect(isTokenExpired(tokenWithExpiry(Math.floor(Date.now() / 1000) + 60))).toBe(false);
  });
});

describe('requestJson authentication recovery', () => {
  afterEach(() => {
    localStorage.clear();
    vi.unstubAllGlobals();
  });

  it('removes the stored token after a 401 response', async () => {
    localStorage.setItem('kagent_token', tokenWithExpiry(Math.floor(Date.now() / 1000) + 60));
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: false,
      status: 401,
      headers: { get: () => 'application/json' },
      json: async () => ({ detail: 'unauthorized' }),
    }));

    await expect(requestJson('/protected')).rejects.toMatchObject({ status: 401 });
    expect(localStorage.getItem('kagent_token')).toBeNull();
  });
});
