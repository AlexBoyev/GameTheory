/**
 * Polls `GET /api/agents/{id}` for the selected agent.
 *
 * Polling rather than streaming on purpose: only one agent is inspected at a
 * time, so a 2 Hz request is cheaper than widening the broadcast for everyone.
 * That held even once the LLM minds gave an agent more to say, so the
 * socket's half-built `subscribe_agent` channel was retired rather than
 * finished - it accepted subscriptions and could never answer them.
 */

import { useEffect, useState } from 'react';

import { api } from '@/api/rest';
import type { AgentDetail } from '@/api/types';

const POLL_MS = 500;

export interface AgentDetailState {
  detail: AgentDetail | null;
  loading: boolean;
  error: string | null;
}

export function useAgentDetail(agentId: number | null): AgentDetailState {
  const [state, setState] = useState<AgentDetailState>({
    detail: null,
    loading: false,
    error: null,
  });

  useEffect(() => {
    if (agentId === null) {
      setState({ detail: null, loading: false, error: null });
      return;
    }

    let cancelled = false;
    let timer: ReturnType<typeof setTimeout> | undefined;

    const poll = async (): Promise<void> => {
      try {
        const detail = await api.agent(agentId);
        if (!cancelled) setState({ detail, loading: false, error: null });
      } catch (error) {
        if (!cancelled) {
          setState((previous) => ({
            detail: previous.detail,
            loading: false,
            error: error instanceof Error ? error.message : 'failed to load agent',
          }));
        }
      }
      if (!cancelled) timer = setTimeout(() => void poll(), POLL_MS);
    };

    void poll();
    return () => {
      cancelled = true;
      if (timer !== undefined) clearTimeout(timer);
    };
  }, [agentId]);

  return state;
}
