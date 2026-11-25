/**
 * One key map, three readers.
 *
 * `lib/keybindings.ts` exists, in its own words, "so the help overlay and
 * the handlers can never disagree about what a key does". The front screen
 * became a third reader and briefly broke that rule by spelling the keys out
 * again in its own array - a copy free to drift the moment anybody rebinds
 * something. These tests guard the lookup both now read through.
 */

import { describe, expect, it } from 'vitest';

import { KEYBINDINGS, UNBOUND, actionForKey, keyFor, keyLabel } from '@/lib/keybindings';

describe('keyLabel', () => {
  it('names the keys nobody writes literally', () => {
    expect(keyLabel(' ')).toBe('Space');
    expect(keyLabel('escape')).toBe('Esc');
  });

  it('upper-cases single letters and leaves the rest alone', () => {
    expect(keyLabel('t')).toBe('T');
    expect(keyLabel('.')).toBe('.');
    expect(keyLabel('1')).toBe('1');
  });
});

describe('keyFor', () => {
  it('returns what the table actually binds', () => {
    expect(keyFor('togglePlay')).toBe('Space');
    expect(keyFor('escapeBack')).toBe('Esc');
    expect(keyFor('toggleTrustLines')).toBe('T');
  });

  it('answers for every action in the table, with no gaps', () => {
    for (const binding of KEYBINDINGS) {
      expect(keyFor(binding.action)).not.toBe(UNBOUND);
      expect(keyFor(binding.action)).toBe(keyLabel(binding.key));
    }
  });

  it('does not use a real key as its "missing" marker', () => {
    // `?` opens the help overlay, so it cannot double as "no binding" -
    // a gap would have rendered as a key that does something else.
    expect(KEYBINDINGS.map((binding) => keyLabel(binding.key))).toContain('?');
    expect(KEYBINDINGS.map((binding) => keyLabel(binding.key))).not.toContain(UNBOUND);
  });

  it('round-trips: the key it reports is the key that triggers the action', () => {
    for (const binding of KEYBINDINGS) {
      expect(actionForKey(binding.key)).toBe(binding.action);
    }
  });
});

describe('the table itself', () => {
  it('binds each key once, so a press is never ambiguous', () => {
    const keys = KEYBINDINGS.map((binding) => binding.key);

    expect(new Set(keys).size).toBe(keys.length);
  });
});
