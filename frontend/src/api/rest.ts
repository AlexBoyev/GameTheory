/**
 * Thin REST client. Same-origin paths only - Vite proxies `/api` to :8000, so
 * there is no backend URL anywhere in the frontend.
 */

import type {
  AgentDetail,
  AgentSummary,
  EventsPayload,
  Health,
  LlmSettings,
  LlmStats,
  LlmStatus,
  Metrics,
  Preset,
  Shelter,
  SimState,
  Tribe,
  TrustGraph,
  WorldConfig,
} from '@/api/types';

const BASE = '/api';

export class ApiError extends Error {
  constructor(
    readonly status: number,
    readonly detail: string,
  ) {
    super(`${status}: ${detail}`);
    this.name = 'ApiError';
  }

  /** True for endpoints that exist but are scheduled for a later phase. */
  get isNotImplementedYet(): boolean {
    return this.status === 501;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${BASE}${path}`, {
    headers: { 'content-type': 'application/json' },
    ...init,
  });
  if (!response.ok) {
    const body: unknown = await response.json().catch(() => null);
    const detail =
      body && typeof body === 'object' && 'detail' in body
        ? String(body.detail)
        : response.statusText;
    throw new ApiError(response.status, detail);
  }
  return (await response.json()) as T;
}

function post<T>(path: string, payload?: unknown): Promise<T> {
  return request<T>(path, {
    method: 'POST',
    ...(payload === undefined ? {} : { body: JSON.stringify(payload) }),
  });
}

export const api = {
  health: (): Promise<Health> => request<Health>('/health'),

  getState: (): Promise<SimState> => request<SimState>('/sim/state'),
  start: (): Promise<SimState> => post<SimState>('/sim/start'),
  pause: (): Promise<SimState> => post<SimState>('/sim/pause'),
  step: (n = 1): Promise<SimState> => post<SimState>('/sim/step', { n }),
  setSpeed: (multiplier: number): Promise<SimState> => post<SimState>('/sim/speed', { multiplier }),
  reset: (payload: { seed?: number; preset?: string; config?: WorldConfig }): Promise<SimState> =>
    post<SimState>('/sim/reset', payload),

  getConfig: (): Promise<WorldConfig> => request<WorldConfig>('/sim/config'),
  putConfig: (config: WorldConfig): Promise<SimState> =>
    request<SimState>('/sim/config', { method: 'PUT', body: JSON.stringify(config) }),
  presets: (): Promise<Preset[]> => request<Preset[]>('/sim/presets'),

  agents: (limit = 500): Promise<AgentSummary[]> =>
    request<AgentSummary[]>(`/agents?limit=${limit}`),
  tribes: (): Promise<Tribe[]> => request<Tribe[]>('/tribes'),
  shelters: (): Promise<Shelter[]> => request<Shelter[]>('/world/shelters'),
  trustGraph: (minimum = 0.3, limit = 300): Promise<TrustGraph> =>
    request<TrustGraph>(`/social/trust-graph?minimum=${minimum}&limit=${limit}`),
  metrics: (fromTick = 0): Promise<Metrics> => request<Metrics>(`/metrics?from_tick=${fromTick}`),
  agent: (id: number): Promise<AgentDetail> => request<AgentDetail>(`/agents/${id}`),
  events: (limit = 200, type?: string): Promise<EventsPayload> =>
    request<EventsPayload>(`/events?limit=${limit}${type ? `&type=${type}` : ''}`),

  llmStatus: (): Promise<LlmStatus> => request<LlmStatus>('/llm/status'),
  llmStats: (): Promise<LlmStats> => request<LlmStats>('/llm/stats'),
  putLlmSettings: (settings: LlmSettings): Promise<LlmStatus> =>
    request<LlmStatus>('/llm/settings', { method: 'PUT', body: JSON.stringify(settings) }),
};
