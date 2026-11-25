import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import {
  BACKOFF_BASE_MS,
  BACKOFF_MAX_MS,
  STALE_AFTER_MS,
  backoffDelay,
  createWorldSocket,
} from '@/api/ws';

describe('backoffDelay', () => {
  it('grows exponentially from the base delay', () => {
    const noJitter = () => 0.5;
    expect(backoffDelay(0, noJitter)).toBe(BACKOFF_BASE_MS);
    expect(backoffDelay(1, noJitter)).toBe(BACKOFF_BASE_MS * 2);
    expect(backoffDelay(3, noJitter)).toBe(BACKOFF_BASE_MS * 8);
  });

  it('caps so a dead backend is retried once every ten seconds, not faster', () => {
    expect(backoffDelay(50, () => 0.5)).toBe(BACKOFF_MAX_MS);
  });

  it('never returns less than the base delay, even with full negative jitter', () => {
    for (let attempt = 0; attempt < 12; attempt += 1) {
      expect(backoffDelay(attempt, () => 0)).toBeGreaterThanOrEqual(BACKOFF_BASE_MS);
    }
  });

  it('applies jitter so reconnecting tabs do not stampede', () => {
    const low = backoffDelay(5, () => 0);
    const high = backoffDelay(5, () => 1);
    expect(low).toBeLessThan(high);
  });
});

/** The smallest WebSocket a socket-under-test needs to believe in. */
class FakeSocket {
  static OPEN = 1;
  readyState = FakeSocket.OPEN;
  onopen: (() => void) | null = null;
  onmessage: ((event: MessageEvent<string>) => void) | null = null;
  onclose: (() => void) | null = null;
  onerror: (() => void) | null = null;
  closed = false;

  close(): void {
    this.closed = true;
    this.readyState = 3;
    this.onclose?.();
  }

  send(): void {}

  deliver(payload: unknown): void {
    this.onmessage?.({ data: JSON.stringify(payload) } as MessageEvent<string>);
  }
}

describe('a socket that is open and dead', () => {
  beforeEach(() => {
    vi.useFakeTimers();
    vi.stubGlobal('WebSocket', FakeSocket);
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllGlobals();
  });

  it('is closed and retried once it goes silent', () => {
    // Vite proxies this socket in development. When the backend side resets,
    // the browser side is left open: no `close` event, so the retry that
    // hangs off `onclose` never runs and the UI freezes on its last frame.
    const made: FakeSocket[] = [];
    const socket = createWorldSocket({
      url: 'ws://test/ws/world',
      onEnvelope: () => {},
      socketFactory: () => {
        const fake = new FakeSocket();
        made.push(fake);
        return fake as unknown as WebSocket;
      },
    });

    made[0]!.onopen?.();
    expect(socket.status).toBe('open');

    made[0]!.deliver({ type: 'frame' });
    vi.advanceTimersByTime(STALE_AFTER_MS - 500);
    expect(made[0]!.closed, 'a socket still delivering must be left alone').toBe(false);

    vi.advanceTimersByTime(1_000);
    expect(made[0]!.closed, 'silence past the threshold means the pipe is gone').toBe(true);
    expect(socket.status).toBe('reconnecting');

    vi.advanceTimersByTime(BACKOFF_MAX_MS);
    expect(made.length, 'and it reconnects rather than sitting there').toBeGreaterThan(1);

    socket.close();
  });

  it('keeps a chatty socket open indefinitely', () => {
    const made: FakeSocket[] = [];
    const socket = createWorldSocket({
      url: 'ws://test/ws/world',
      onEnvelope: () => {},
      socketFactory: () => {
        const fake = new FakeSocket();
        made.push(fake);
        return fake as unknown as WebSocket;
      },
    });
    made[0]!.onopen?.();

    for (let elapsed = 0; elapsed < STALE_AFTER_MS * 4; elapsed += 1_000) {
      made[0]!.deliver({ type: 'frame' });
      vi.advanceTimersByTime(1_000);
    }

    expect(made[0]!.closed).toBe(false);
    expect(made).toHaveLength(1);

    socket.close();
  });
});
