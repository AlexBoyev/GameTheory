/**
 * The keyboard map (SPEC 9.3).
 *
 * Declared here as data so the help overlay and the handlers can never
 * disagree about what a key does. Phase 3 wires the actions.
 */

export type ActionId =
  | 'togglePlay'
  | 'step'
  | 'reset'
  | 'speed1'
  | 'speed2'
  | 'speed5'
  | 'speed10'
  | 'speed25'
  | 'speed50'
  | 'speedMax'
  | 'followSelected'
  | 'escapeBack'
  | 'toggleTrustLines'
  | 'toggleTerritories'
  | 'toggleHeatmap'
  | 'toggleNames'
  | 'toggleSpeech'
  | 'toggleCharts'
  | 'toggleLog'
  | 'toggleLlm'
  | 'toggleGod'
  | 'toggleMinimap'
  | 'toggleHelp';

export interface Keybinding {
  /** `KeyboardEvent.key`, lower-cased for letters. */
  key: string;
  action: ActionId;
  label: string;
  group: 'simulation' | 'camera' | 'overlays';
}

export const KEYBINDINGS: readonly Keybinding[] = [
  { key: ' ', action: 'togglePlay', label: 'Play / pause', group: 'simulation' },
  { key: '.', action: 'step', label: 'Step one tick', group: 'simulation' },
  { key: 'r', action: 'reset', label: 'Reset world', group: 'simulation' },
  { key: '1', action: 'speed1', label: 'Speed 1x', group: 'simulation' },
  { key: '2', action: 'speed2', label: 'Speed 2x', group: 'simulation' },
  { key: '3', action: 'speed5', label: 'Speed 5x', group: 'simulation' },
  { key: '4', action: 'speed10', label: 'Speed 10x', group: 'simulation' },
  { key: '5', action: 'speed25', label: 'Speed 25x', group: 'simulation' },
  { key: '6', action: 'speed50', label: 'Speed 50x', group: 'simulation' },
  { key: '7', action: 'speedMax', label: 'Speed MAX', group: 'simulation' },
  { key: 'f', action: 'followSelected', label: 'Follow selected agent', group: 'camera' },
  { key: 'escape', action: 'escapeBack', label: 'Close · unfollow · menu', group: 'simulation' },
  { key: 't', action: 'toggleTrustLines', label: 'Trust lines', group: 'overlays' },
  { key: 'g', action: 'toggleTerritories', label: 'Tribe territories', group: 'overlays' },
  { key: 'h', action: 'toggleHeatmap', label: 'Activity heatmap', group: 'overlays' },
  { key: 'n', action: 'toggleNames', label: 'Agent names', group: 'overlays' },
  { key: 'b', action: 'toggleSpeech', label: 'Speech bubbles', group: 'overlays' },
  { key: 'c', action: 'toggleCharts', label: 'Charts panel', group: 'overlays' },
  { key: 'l', action: 'toggleLog', label: 'Event log', group: 'overlays' },
  { key: 'm', action: 'toggleLlm', label: 'LLM minds monitor', group: 'overlays' },
  { key: 'k', action: 'toggleGod', label: 'God tools', group: 'overlays' },
  { key: 'o', action: 'toggleMinimap', label: 'Minimap', group: 'overlays' },
  { key: '?', action: 'toggleHelp', label: 'This help', group: 'overlays' },
];

/** Resolve a `KeyboardEvent` to an action, or `null` when unbound. */
export function actionForKey(key: string): ActionId | null {
  const normalised = key.length === 1 ? key.toLowerCase() : key.toLowerCase();
  return KEYBINDINGS.find((binding) => binding.key === normalised)?.action ?? null;
}

/** Shown when an action has no key. Deliberately not a pressable character. */
export const UNBOUND = '—';

/** How a key is written for a reader: `Space`, `Esc`, `T`. */
export function keyLabel(key: string): string {
  if (key === ' ') return 'Space';
  if (key === 'escape') return 'Esc';
  return key.length === 1 ? key.toUpperCase() : key;
}

/**
 * The key bound to `action`, written for a reader.
 *
 * Exists so nothing has to keep its own copy of the map. The front screen
 * summarises a handful of these and the help overlay lists them all; both
 * used to be able to drift from the handlers, which is the one thing this
 * module is for.
 */
export function keyFor(action: ActionId): string {
  const binding = KEYBINDINGS.find((entry) => entry.action === action);
  // Not '?': that is a real key here (the help overlay), so a missing
  // binding would render as a plausible one. An em dash cannot be mistaken
  // for something to press.
  return binding === undefined ? UNBOUND : keyLabel(binding.key);
}
