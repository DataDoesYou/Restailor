import { describe, it, expect } from 'vitest';
import { normalizeText, stableHash, makeAppliedKey } from './hash';

// Fixtures aligned with backend logic (see backend/hash_utils.py)
const cases: Array<{ raw: string; normalized: string; }> = [
  { raw: 'Hello\r\nWorld', normalized: 'Hello World' },
  { raw: 'A\tB\n\nC', normalized: 'A B C' },
  { raw: '\uFEFFZero\u200BWidth', normalized: 'ZeroWidth' },
  { raw: '  Multi   space\nlines\t', normalized: 'Multi space lines' },
];

describe('normalizeText', () => {
  for (const c of cases) {
    it(`normalizes: ${JSON.stringify(c.raw)}`, () => {
      expect(normalizeText(c.raw)).toEqual(c.normalized);
    });
  }
});

describe('stableHash + parity', () => {
  it('produces known SHA-256 for a sample', async () => {
    const h = await stableHash('test');
    // Precomputed echo -n test | sha256sum
    expect(h).toEqual('9f86d081884c7d659a2feaa0c55ad015a3bf4f1b2b0b822cd15d6c15b0f00a08');
  });

  it('hashes normalized text same as backend expectation', async () => {
    // Combine normalization + hashing; we just assert deterministic output
    const norm = normalizeText('Line\r\nBreak\tTest');
    const h = await stableHash(norm);
    // Compute expected using Node crypto for reference (kept inline deterministic value)
  expect(h).toEqual('e415854129ff2ff3d8d4b2171c0890cc80e4608c2a9ae27817cc4f6177561e78');
  });
});

describe('makeAppliedKey', () => {
  it('builds applied key from normalized component hashes', async () => {
    const { jdHash, baseHash, appliedKey } = await makeAppliedKey('42', 'JD\rText', 'Base\n\nText');
    expect(appliedKey).toEqual(`42:${jdHash}:${baseHash}`);
    expect(jdHash).toHaveLength(64);
    expect(baseHash).toHaveLength(64);
  });
});
