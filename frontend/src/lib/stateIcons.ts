/**
 * The emoji vocabulary of the simulation (SPEC 9.2).
 *
 * Lives in `lib/` rather than next to the component that draws it, so the
 * inspector, the tooltip and the help legend can all share one definition -
 * and so there is no doubt that 🍖 means the same thing everywhere.
 */

/** Agent states worth announcing. Wandering, moving and idling get no icon. */
export const STATE_EMOJI: Record<string, string> = {
  eat: '🍖',
  drink: '💧',
  sleep: '😴',
  gather: '🧺',
  hunt: '🏹',
  flee: '😱',
  talk: '🗣️',
  scheme: '🕵️',
  fight: '⚔️',
  trade: '🤝',
  build: '🔨',
  dead: '💀',
};

/** Event types in the feed. */
export const EVENT_EMOJI: Record<string, string> = {
  birth: '👶',
  death: '💀',
  hunt: '🏹',
  cooperation: '🤝',
  defection: '🔪',
  betrayal: '💔',
  gift: '🎁',
  trade: '⚖️',
  gossip: '🗣️',
  lie_told: '🤥',
  lie_caught: '👁️',
  alliance: '🤝',
  combat: '⚔️',
  hunt_joined: '🦌',
  tribe_founded: '🏕️',
  tribe_joined: '🤝',
  tribe_left: '🚪',
  tribe_split: '✂️',
  leader_changed: '👑',
  coup: '🗡️',
  war_declared: '🔥',
  peace_made: '🕊️',
  raid: '🏴',
  speech: '💬',
  disaster: '🌪️',
  god_action: '✨',
};
