/**
 * The world socket, with automatic reconnection.
 *
 * A simulation you watch for an hour will survive a backend restart, a laptop
 * sleep and a Vite reload, so reconnection is not optional: the socket retries
 * with exponential backoff plus jitter (so many tabs do not stampede) and
 * resets its delay once a connection survives long enough to be real.
 */

import type { ConnectionStatus, Envelope } from '@/api/types';

export interface WorldSocketOptions {
  /** Defaults to `/ws/world` on the current origin (Vite proxies it). */
  url?: string;
  onEnvelope: (envelope: Envelope) => void;
  onStatus?: (status: ConnectionStatus) => void;
  /** Injected in tests; defaults to the global `WebSocket`. */
  socketFactory?: (url: string) => WebSocket;
}

export interface WorldSocket {
  send(message: Record<string, unknown>): void;
  close(): void;
  readonly status: ConnectionStatus;
}

export const BACKOFF_BASE_MS = 300;
export const BACKOFF_MAX_MS = 10_000;
const STABLE_AFTER_MS = 5_000;

/** Delay before retry `attempt` (0-based), with +-25% jitter. */
export function backoffDelay(attempt: number, random: () => number = Math.random): number {
  const exponential = Math.min(BACKOFF_MAX_MS, BACKOFF_BASE_MS * 2 ** attempt);
  const jitter = exponential * 0.25 * (random() * 2 - 1);
  return Math.round(Math.max(BACKOFF_BASE_MS, exponential + jitter));
}

export function defaultWorldSocketUrl(): string {
  if (typeof window === 'undefined') return 'ws://localhost:5173/ws/world';
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
  return `${protocol}//${window.location.host}/ws/world`;
}

export function createWorldSocket(options: WorldSocketOptions): WorldSocket {
  const url = options.url ?? defaultWorldSocketUrl();
  const factory = options.socketFactory ?? ((target: string) => new WebSocket(target));

  let socket: WebSocket | null = null;
  let attempt = 0;
  let status: ConnectionStatus = 'idle';
  let disposed = false;
  let retryTimer: ReturnType<typeof setTimeout> | null = null;
  let openedAt = 0;

  const setStatus = (next: ConnectionStatus): void => {
    status = next;
    options.onStatus?.(next);
  };

  const scheduleRetry = (): void => {
    if (disposed) return;
    setStatus('reconnecting');
    const delay = backoffDelay(attempt);
    attempt += 1;
    retryTimer = setTimeout(connect, delay);
  };

  function connect(): void {
    if (disposed) return;
    setStatus(attempt === 0 ? 'connecting' : 'reconnecting');
    socket = factory(url);

    socket.onopen = (): void => {
      openedAt = Date.now();
      setStatus('open');
    };

    socket.onmessage = (event: MessageEvent<string>): void => {
      try {
        const envelope = JSON.parse(event.data) as Envelope;
        options.onEnvelope(envelope);
      } catch {
        // A malformed frame is not worth dropping the connection over.
      }
    };

    socket.onclose = (): void => {
      socket = null;
      if (disposed) {
        setStatus('closed');
        return;
      }
      // A connection that lasted a while was healthy: start backoff over.
      if (openedAt > 0 && Date.now() - openedAt > STABLE_AFTER_MS) attempt = 0;
      scheduleRetry();
    };

    socket.onerror = (): void => {
      // `onclose` always follows, which is where retrying is handled.
      socket?.close();
    };
  }

  connect();

  return {
    get status() {
      return status;
    },
    send(message) {
      if (socket && socket.readyState === WebSocket.OPEN) {
        socket.send(JSON.stringify(message));
      }
    },
    close() {
      disposed = true;
      if (retryTimer) clearTimeout(retryTimer);
      socket?.close();
      socket = null;
      setStatus('closed');
    },
  };
}
