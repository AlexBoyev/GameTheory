import { beforeEach, describe, expect, it } from 'vitest';

import { MAX_SPEECH, useSimStore } from '@/state/simStore';
import type { Envelope } from '@/api/types';

function speech(agent: number, text: string, ttl = 6): Envelope {
  return { type: 'speech', tick: 1, data: { agent, text, ttl } };
}

describe('speech bubbles', () => {
  beforeEach(() => {
    useSimStore.setState({ speech: [] });
  });

  it('keeps what an agent said, with an expiry', () => {
    useSimStore.getState().ingest(speech(3, 'A friend is cheaper than a fight.'));

    const [line] = useSimStore.getState().speech;
    expect(line?.agentId).toBe(3);
    expect(line?.text).toBe('A friend is cheaper than a fight.');
    expect(line?.until).toBeGreaterThan(performance.now());
  });

  it('replaces a line rather than stacking two over one head', () => {
    useSimStore.getState().ingest(speech(3, 'first'));
    useSimStore.getState().ingest(speech(3, 'second'));

    const lines = useSimStore.getState().speech;
    expect(lines).toHaveLength(1);
    expect(lines[0]?.text).toBe('second');
  });

  it('keeps several speakers apart', () => {
    useSimStore.getState().ingest(speech(1, 'one'));
    useSimStore.getState().ingest(speech(2, 'two'));

    expect(useSimStore.getState().speech.map((line) => line.agentId)).toEqual([2, 1]);
  });

  it('caps how many bubbles can be on screen', () => {
    for (let id = 0; id < MAX_SPEECH + 5; id += 1) {
      useSimStore.getState().ingest(speech(id, `line ${id}`));
    }

    expect(useSimStore.getState().speech).toHaveLength(MAX_SPEECH);
  });

  it('ignores an empty line', () => {
    useSimStore.getState().ingest(speech(1, ''));

    expect(useSimStore.getState().speech).toHaveLength(0);
  });

  it('forgets everything when the world is rebuilt', () => {
    useSimStore.getState().ingest(speech(1, 'before the reset'));

    useSimStore.getState().clearWorld();

    expect(useSimStore.getState().speech).toHaveLength(0);
  });
});
