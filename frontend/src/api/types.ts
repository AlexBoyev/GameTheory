/**
 * Hand-written shapes for the WebSocket protocol, plus convenient aliases over
 * the generated REST types.
 *
 * REST DTOs are generated from the backend's OpenAPI schema
 * (`npm run gen:api`) and must never be hand-written. The WS protocol is not
 * part of OpenAPI, so its envelopes live here.
 */

import type { components } from '@/api/generated';

export type SimState = components['schemas']['SimStateDTO'];
export type WorldConfig = components['schemas']['WorldConfig'];
export type Health = components['schemas']['HealthDTO'];
export type Preset = components['schemas']['PresetDTO'];
export type LlmStatus = components['schemas']['LLMStatusDTO'];
export type LlmStats = components['schemas']['LLMStatsDTO'];
export type LlmCall = components['schemas']['LLMCallDTO'];
export type LlmSettings = components['schemas']['LLMSettingsRequest'];
export type LlmMind = components['schemas']['LLMMindDTO'];
export type AgentSummary = components['schemas']['AgentSummaryDTO'];
export type AgentDetail = components['schemas']['AgentDetailDTO'];
export type EventsPayload = components['schemas']['EventsDTO'];
export type Tribe = components['schemas']['TribeDTO'];
export type Shelter = components['schemas']['ShelterDTO'];
export type TrustGraph = components['schemas']['TrustGraphDTO'];
export type TrustEdge = components['schemas']['TrustEdgeDTO'];
export type Metrics = components['schemas']['MetricsDTO'];
export type MetricPoint = components['schemas']['MetricPointDTO'];
export type Snapshot = components['schemas']['SnapshotDTO'];
export type GodAction = components['schemas']['GodAction'];
export type GodRequest = components['schemas']['GodActionRequest'];
export type GodResult = components['schemas']['GodActionResultDTO'];
export type Tournament = components['schemas']['TournamentDTO'];
export type TournamentStanding = components['schemas']['TournamentStandingDTO'];

/** One row of the event feed. */
export interface EventItem {
  tick: number;
  type: string;
  summary: string;
  importance: number;
  actors: number[];
  x: number | null;
  z: number | null;
}

/** Every server message is `{type, tick, data}` (SPEC 8). */
export interface Envelope<T = Record<string, unknown>> {
  type: string;
  tick: number;
  data: T;
}

export interface TerrainMeta {
  size: number;
  resolution: number;
  water_level: number;
  max_height: number;
  /** False until Phase 2 serves a real heightmap. */
  available: boolean;
}

export interface Legend {
  states: string[];
  biomes: string[];
  /** Resource kind names, indexed by wire code. Added in Phase 2. */
  resources?: string[];
}

export interface HelloData {
  config: WorldConfig;
  terrain: TerrainMeta;
  legend: Legend;
  /** Every resource node in the world: `[id, x, z, kind, amount, capacity]`. */
  resources?: { stride: number; nodes: number[] };
  state: {
    status: string;
    tick: number;
    speed: number;
    seed: number;
    day: number;
    season: string;
    time_of_day: number;
    population: number;
  };
}

export interface FrameData {
  stride: number;
  /** Flat `[id, x, z, heading, state, tribe, flags]` per agent. */
  agents: number[];
  tod: number;
  status: string;
  speed: number;
  day: number;
  season: string;
  population?: number;
  /** Changed resource amounts as `[id, amount, ...]` pairs. */
  resources?: number[];
  /** Ids of nodes that no longer exist (a rotted corpse, say). */
  removed?: number[];
  /** Ticks still owed to a skip; 0 when none is running. */
  skip?: number;
}

/** The `day` envelope: the title card for a day that has just begun. */
export interface DayData {
  day: number;
  season: string;
  headline: string;
  lines: string[];
  counts: Record<string, number>;
}

export interface SpeechData {
  agent: number;
  text: string;
  ttl: number;
}

export interface ErrorData {
  message: string;
}

export type ConnectionStatus = 'idle' | 'connecting' | 'open' | 'reconnecting' | 'closed';
