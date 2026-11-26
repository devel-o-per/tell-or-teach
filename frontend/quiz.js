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

  class Session {
    constructor(concepts, opts = {}) {
      const rng = opts.rng || Math.random;
      this.gap = opts.gap ?? 3;
      this.queue = shuffle(concepts, rng)
        .slice(0, opts.size || concepts.length)
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
      return {
        answered: this.results.length,
        firstTry: this.results.filter((r) => r.kind === 'original' && r.correct).length,
        fixed: comebacks.filter((r) => r.correct).map((r) => r.topic),
        stillShaky: missed.map((m) => m.topic).filter((t) => !comebacks.some((c) => c.topic === t && c.correct)),
        comebacksWon: comebacks.filter((r) => r.correct).length,
        comebacksTotal: comebacks.length,
      };
    }
  }

  const api = { Session, shuffle };
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  else root.Quiz = api;
})(typeof window !== 'undefined' ? window : globalThis);
