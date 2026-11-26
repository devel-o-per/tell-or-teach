/*
 * The quiz engine: which question comes next, and when a comeback returns.
 *
 * Every concept has two twin questions. A student sees one twin (picked at
 * random, so neither twin is always the "first" one). If they get it wrong,
 * the other twin is scheduled to come back after `gap` more questions.
 * Comebacks still pending at the end are shown before the session finishes.
 */
(function (root) {
  function shuffle(list, rng) {
    const a = list.slice();
    for (let i = a.length - 1; i > 0; i--) {
      const j = Math.floor(rng() * (i + 1));
      [a[i], a[j]] = [a[j], a[i]];
    }
    return a;
  }

  const TIER_QUOTAS = [[1, 7], [2, 5], [3, 3]];
  const MAX_PRIORITY = 5;

  /*
   * Order of original questions for one session.
   * Tiered banks: up to 5 priority concepts, then tier 1, 2, 3 with quotas 7/5/3
   * (minus priority concepts from that tier). Within a tier unseen concepts come
   * first; a tier that runs short passes its leftover count to the next tier.
   * Banks without tiers: priority concepts first, then the rest, each shuffled.
   */
  function planOriginals(concepts, opts, rng) {
    const size = opts.size || concepts.length;
    const priority = new Set(opts.priority || []);
    const seen = new Set(opts.seen || []);

    if (!concepts.some((c) => c.tier)) {
      const first = shuffle(concepts.filter((c) => priority.has(c.id)), rng);
      const rest = shuffle(concepts.filter((c) => !priority.has(c.id)), rng);
      return first.concat(rest).slice(0, size);
    }

    const tierOf = (c) => ([1, 2, 3].includes(c.tier) ? c.tier : 3);
    const plan = shuffle(concepts.filter((c) => priority.has(c.id)), rng).slice(0, MAX_PRIORITY);
    const taken = new Set(plan.map((c) => c.id));
    let carry = 0;
    for (const [tier, quota] of TIER_QUOTAS) {
      const need = Math.max(0, quota + carry - plan.filter((c) => tierOf(c) === tier).length);
      const pool = concepts.filter((c) => tierOf(c) === tier && !taken.has(c.id));
      const picked = shuffle(pool.filter((c) => !seen.has(c.id)), rng)
        .concat(shuffle(pool.filter((c) => seen.has(c.id)), rng))
        .slice(0, need);
      picked.forEach((c) => taken.add(c.id));
      plan.push(...picked);
      carry = need - picked.length;
    }
    return plan.slice(0, size);
  }

  class Session {
    constructor(concepts, opts = {}) {
      const rng = opts.rng || Math.random;
      this.gap = opts.gap ?? 3;
      this.queue = planOriginals(concepts, opts, rng)
        .map((c) => ({ concept: c, twin: rng() < 0.5 ? 0 : 1, kind: 'original' }));
      this.pending = [];
      this.shown = 0;
      this.results = [];
    }

    next() {
      const due = this.pending.findIndex((p) => p.dueAt <= this.shown);
      let item = null;
      if (due >= 0) item = this.pending.splice(due, 1)[0].item;
      else if (this.queue.length) item = this.queue.shift();
      else if (this.pending.length) item = this.pending.shift().item;
      if (item) this.shown += 1;
      return item;
    }

    // Questions planned for this session so far; grows when a comeback is scheduled.
    get planned() {
      return this.shown + this.queue.length + this.pending.length;
    }

    question(item) {
      return item.concept.twins[item.twin];
    }

    record(item, correct, confidence) {
      this.results.push({ conceptId: item.concept.id, topic: item.concept.topic, kind: item.kind, correct, confidence });
      if (item.kind === 'original' && !correct) {
        this.pending.push({
          dueAt: this.shown + this.gap,
          item: { concept: item.concept, twin: 1 - item.twin, kind: 'comeback' },
        });
      }
    }

    receipt() {
      const missed = this.results.filter((r) => r.kind === 'original' && !r.correct);
      const comebacks = this.results.filter((r) => r.kind === 'comeback');
      const shaky = missed.filter((m) => !comebacks.some((c) => c.conceptId === m.conceptId && c.correct));
      return {
        answered: this.results.length,
        originals: this.results.filter((r) => r.kind === 'original').length,
        firstTry: this.results.filter((r) => r.kind === 'original' && r.correct).length,
        fixed: comebacks.filter((r) => r.correct).map((r) => r.topic),
        stillShaky: shaky.map((m) => m.topic),
        stillShakyIds: shaky.map((m) => m.conceptId),
        comebacksWon: comebacks.filter((r) => r.correct).length,
        comebacksTotal: comebacks.length,
      };
    }
  }

  const api = { Session, shuffle, planOriginals };
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  else root.Quiz = api;
})(typeof window !== 'undefined' ? window : globalThis);
