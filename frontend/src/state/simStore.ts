/**
 * Live simulation state, fed by the world socket.
 *
 * Frames are kept as `previous`/`current` so the renderer can interpolate.
 * Components that run per render frame (the agent instances) read this store
 * imperatively via `getState()` rather than subscribing, so a 10 Hz stream
 * never causes 10 React re-renders per second of the 3D scene.
 */

import { create } from 'zustand';

import type {
  ConnectionStatus,
  DayData,
  Envelope,
  EventItem,
  FrameData,
  HelloData,
  Legend,
  SpeechData,
  TerrainMeta,
  WorldConfig,
} from '@/api/types';
import type { AgentFrame } from '@/lib/interpolation';

export interface ResourceNode {
  id: number;
  x: number;
  z: number;
  kind: string;
  capacity: number;
}

/** Values per resource node on the wire: id, x, z, kind, amount, capacity. */
const RESOURCE_STRIDE = 6;

export interface SimStoreState {
  connection: ConnectionStatus;
  tick: number;
  status: string;
  speed: number;
  seed: number;
  day: number;
  season: string;
  timeOfDay: number;
  population: number;
  /** Measured tick rate from `GET /api/sim/state` (trailing 1s average). */
  ticksPerSecond: number;
  /**
   * Ticks still owed to a skip, from the frame stream.
   *
   * On the frame rather than only on the 1 Hz state poll: a skip of a day
   * takes tens of seconds and a progress bar that moves once a second looks
   * stuck.
   */
  skipRemaining: number;
  /** The newest day card, or null once it has been shown and dismissed. */
  dayReport: DayData | null;
  /**
   * Every day card this world has produced, newest first.
   *
   * A card is up for ten seconds and then gone, which at MAX speed is about
   * as long as a day takes - so looking away costs you the day. The log
   * panel lists these and a click brings the card back.
   */
  dayHistory: DayData[];
  isNight: boolean;
  terrain: TerrainMeta | null;
  legend: Legend | null;
  config: WorldConfig | null;
  previousFrame: AgentFrame | null;
  currentFrame: AgentFrame | null;
  framesReceived: number;
  lastError: string | null;

  /** Incremented on every `hello`, so the scene knows to refetch terrain. */
  worldEpoch: number;
  resourceNodes: ResourceNode[];
  /**
   * `node id -> fullness in 0..1`, quantised to 2% steps by the backend.
   * Mutated in place on every frame - deliberately not reactive.
   */
  resourceAmounts: Map<number, number>;
  /** Bumped only when nodes are added or removed, never on an amount change. */
  resourceVersion: number;

  /** Newest first, capped - this is the event feed. */
  events: EventItem[];

  /**
   * What agents are saying out loud, by agent id.
   *
   * Separate from the event feed because a bubble has its own lifetime: the
   * feed keeps a line forever, the bubble over a head expires.
   */
  speech: SpeechLine[];

  setConnection: (connection: ConnectionStatus) => void;
  ingest: (envelope: Envelope) => void;
  clearWorld: () => void;
  /** Seed the feed from `GET /api/events` so a fresh tab is not empty. */
  seedEvents: (items: EventItem[]) => void;
  /** Take the day card down (its timer ran out, or it was clicked away). */
  dismissDay: () => void;
  /** Put a card from the history back on screen. */
  showDay: (report: DayData) => void;
}

/**
 * How many days of headlines the log keeps - two months of island history.
 *
 * All of them are listed (the strip scrolls); the cap is only so that a run
 * left going overnight cannot grow the array without bound.
 */
export const MAX_DAY_HISTORY = 60;

export const MAX_FEED_EVENTS = 300;

/** How many bubbles can be on screen at once. */
export const MAX_SPEECH = 8;

export interface SpeechLine {
  agentId: number;
  text: string;
  /** `performance.now()` after which the bubble is gone. */
  until: number;
}

const INITIAL = {
  connection: 'idle' as ConnectionStatus,
  tick: 0,
  status: 'stopped',
  speed: 1,
  seed: 0,
  day: 0,
  season: 'spring',
  timeOfDay: 0.5,
  population: 0,
  ticksPerSecond: 0,
  skipRemaining: 0,
  dayReport: null as DayData | null,
  dayHistory: [] as DayData[],
  isNight: false,
  terrain: null,
  legend: null,
  config: null,
  previousFrame: null,
  currentFrame: null,
  framesReceived: 0,
  lastError: null,
  worldEpoch: 0,
  resourceNodes: [] as ResourceNode[],
  resourceAmounts: new Map<number, number>(),
  resourceVersion: 0,
  events: [] as EventItem[],
  speech: [] as SpeechLine[],
};

/** Decode the flat resource array from `hello` into nodes plus amounts. */
function decodeResources(
  flat: number[] | undefined,
  kinds: string[],
): { nodes: ResourceNode[]; amounts: Map<number, number> } {
  const nodes: ResourceNode[] = [];
  const amounts = new Map<number, number>();
  if (!flat) return { nodes, amounts };

  for (let offset = 0; offset + RESOURCE_STRIDE <= flat.length; offset += RESOURCE_STRIDE) {
    const id = flat[offset] ?? 0;
    const capacity = flat[offset + 5] ?? 1;
    nodes.push({
      id,
      x: flat[offset + 1] ?? 0,
      z: flat[offset + 2] ?? 0,
      kind: kinds[flat[offset + 3] ?? 0] ?? 'unknown',
      capacity,
    });
    // `hello` sends absolute amounts; frames send fullness. Normalise here so
    // the renderer only ever deals with one of them.
    amounts.set(id, capacity > 0 ? Math.min(1, (flat[offset + 4] ?? 0) / capacity) : 1);
  }
  return { nodes, amounts };
}

export const useSimStore = create<SimStoreState>((set) => ({
  ...INITIAL,

  setConnection: (connection) => set({ connection }),

  clearWorld: () =>
    set({ previousFrame: null, currentFrame: null, framesReceived: 0, speech: [] }),

  seedEvents: (items) => set({ events: items.slice(0, MAX_FEED_EVENTS) }),

  dismissDay: () => set({ dayReport: null }),

  showDay: (report) => set({ dayReport: report }),

  ingest: (envelope) => {
    switch (envelope.type) {
      case 'hello': {
        const data = envelope.data as unknown as HelloData;
        const { nodes, amounts } = decodeResources(
          data.resources?.nodes,
          data.legend.resources ?? [],
        );
        set((state) => ({
          resourceNodes: nodes,
          resourceAmounts: amounts,
          resourceVersion: state.resourceVersion + 1,
          worldEpoch: state.worldEpoch + 1,
          config: data.config,
          terrain: data.terrain,
          legend: data.legend,
          seed: data.state.seed,
          tick: data.state.tick,
          status: data.state.status,
          speed: data.state.speed,
          day: data.state.day,
          season: data.state.season,
          timeOfDay: data.state.time_of_day,
          population: data.state.population,
          previousFrame: null,
          currentFrame: null,
          dayReport: null,
          dayHistory: [],
        }));
        break;
      }
      case 'frame': {
        const data = envelope.data as unknown as FrameData;
        const frame: AgentFrame = {
          agents: Float32Array.from(data.agents),
          stride: data.stride,
          tick: envelope.tick,
          receivedAt: performance.now(),
        };
        set((state) => {
          // Amount deltas mutate the shared map: the renderer reads it every
          // frame anyway, and making it reactive would re-render the scene at
          // the broadcast rate for nothing.
          const amounts = state.resourceAmounts;
          const deltas = data.resources ?? [];
          for (let offset = 0; offset + 1 < deltas.length; offset += 2) {
            amounts.set(deltas[offset] ?? 0, deltas[offset + 1] ?? 0);
          }

          const gone = data.removed ?? [];
          let nodes = state.resourceNodes;
          let version = state.resourceVersion;
          if (gone.length > 0) {
            const removed = new Set(gone);
            for (const id of removed) amounts.delete(id);
            nodes = nodes.filter((node) => !removed.has(node.id));
            version += 1;
          }

          return {
            previousFrame: state.currentFrame,
            currentFrame: frame,
            tick: envelope.tick,
            timeOfDay: data.tod,
            status: data.status,
            speed: data.speed,
            day: data.day,
            season: data.season,
            population: frame.agents.length / Math.max(1, data.stride),
            framesReceived: state.framesReceived + 1,
            skipRemaining: data.skip ?? 0,
            resourceNodes: nodes,
            resourceVersion: version,
          };
        });
        break;
      }
      case 'day': {
        const report = envelope.data as unknown as DayData;
        set((state) => ({
          dayReport: report,
          // Guard against a repeat of the same day: a reconnect replays
          // nothing today, but a card listed twice would read as a bug.
          dayHistory: [
            report,
            ...state.dayHistory.filter((entry) => entry.day !== report.day),
          ].slice(0, MAX_DAY_HISTORY),
        }));
        break;
      }
      case 'events': {
        const data = envelope.data as unknown as { items?: EventItem[] };
        const incoming = data.items ?? [];
        if (incoming.length === 0) break;
        set((state) => ({
          // Newest first, so the feed reads like a log.
          events: [...incoming.slice().reverse(), ...state.events].slice(0, MAX_FEED_EVENTS),
        }));
        break;
      }
      case 'speech': {
        const data = envelope.data as unknown as SpeechData;
        if (!data.text) break;
        const line: SpeechLine = {
          agentId: data.agent,
          text: data.text,
          until: performance.now() + (data.ttl ?? 6) * 1000,
        };
        set((state) => ({
          // One bubble per agent: a second line replaces the first rather
          // than stacking two over the same head.
          speech: [line, ...state.speech.filter((item) => item.agentId !== line.agentId)].slice(
            0,
            MAX_SPEECH,
          ),
        }));
        break;
      }
      case 'error': {
        const data = envelope.data as unknown as { message?: string };
        set({ lastError: data.message ?? 'unknown error' });
        break;
      }
      default:
        // `metrics` is polled over REST by useSocietyPolling, and so is agent
        // detail (`useAgentDetail`). The socket carries neither: there is no
        // `agent_detail` envelope any more, because the server could never
        // send one.
        break;
    }
  },
}));

/** Non-reactive read for code running inside the render loop. */
export const simState = (): SimStoreState => useSimStore.getState();
