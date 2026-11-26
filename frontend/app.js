/*
 * Tell Me or Teach Me: the student-facing app (Vue 3, no build step).
 *
 * Screens: start -> quiz -> receipt.
 * After a wrong first answer the tutor panel opens. The server decides the
 * tutor style (tell or teach) from Flagsmith; this file only shows it.
 */
const { createApp } = Vue;

const SUBJECT_NAMES = { mlt: 'MLT', viva: 'MAD 2 viva', java: 'Java' };
const SUBJECT_TAGLINES = { viva: 'The 16 topics examiners ask most, from 675 real viva reports' };
const SESSION_SIZE = 15;
const COMEBACK_GAP = 3;
const LETTERS = 'ABCDE';

function makeUid() {
  try {
    const saved = localStorage.getItem('tot_uid');
    if (saved) return saved;
  } catch (e) { /* storage blocked: a fresh ID per visit is fine */ }
  const uid = (crypto.randomUUID && crypto.randomUUID()) ||
    'u-' + Date.now().toString(36) + '-' + Math.random().toString(36).slice(2, 10);
  try { localStorage.setItem('tot_uid', uid); } catch (e) { /* ignore */ }
  return uid;
}

// Concept ids this browser has already been shown, per subject.
function loadSeen(subject) {
  try {
    const list = JSON.parse(localStorage.getItem('tot_seen_' + subject) || '[]');
    return Array.isArray(list) ? list : [];
  } catch (e) { return []; }
}

function saveSeen(subject, list) {
  try { localStorage.setItem('tot_seen_' + subject, JSON.stringify(list)); } catch (e) { /* ignore */ }
}

// Record a shown concept; once every concept has been seen, start the list again.
function markSeen(subject, conceptId, allConcepts) {
  const seen = new Set(loadSeen(subject));
  seen.add(conceptId);
  const all = allConcepts.every((c) => seen.has(c.id));
  saveSeen(subject, all ? [] : [...seen]);
}

function readGroup() {
  const g = (new URLSearchParams(location.search).get('g') || '').toLowerCase();
  return /^[a-z0-9-]{1,24}$/.test(g) ? g : 'direct';
}

async function api(path, body) {
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), 15000);
  try {
    const res = await fetch(window.APP_CONFIG.API_BASE + path, {
      method: body ? 'POST' : 'GET',
      headers: body ? { 'Content-Type': 'application/json' } : {},
      body: body ? JSON.stringify(body) : undefined,
      signal: ctrl.signal,
    });
    if (!res.ok) throw new Error(path + ' answered ' + res.status);
    return await res.json();
  } finally {
    clearTimeout(timer);
  }
}

function freshTutor() {
  return {
    open: false, style: null, messages: [], turn: 0, turnsLeft: 0,
    loading: false, input: '', failed: false,
    retry: { active: false, pick: null, done: false, correct: false },
  };
}

createApp({
  data() {
    return {
      screen: 'start',
      uid: makeUid(),
      group: readGroup(),
      subjects: [],
      subject: null,
      concepts: null,
      flagsReady: false,
      studentsToday: null,
      loadError: '',
      session: null,
      item: null,
      q: null,
      selected: null,
      confidence: null,
      submitted: false,
      correct: false,
      tutor: freshTutor(),
      receipt: null,
      copied: false,
      letters: LETTERS,
    };
  },

  computed: {
    isComeback() { return this.item && this.item.kind === 'comeback'; },
    isCode() { return !!this.q && this.q.question.includes('\n'); },
    progress() {
      const total = this.session ? this.session.planned : 0;
      return total ? Math.min(100, (this.session.shown / total) * 100) : 0;
    },
    shareLink() {
      return location.origin + location.pathname + (this.group !== 'direct' ? '?g=' + this.group : '');
    },
    whatsappUrl() {
      const text = 'I just practised the most-asked MAD 2 viva topics with an AI tutor. Try it: ' + this.shareLink;
      return 'https://wa.me/?text=' + encodeURIComponent(text);
    },
    effectiveStyle() { return this.tutor.style || 'tell'; },
    revealAnswer() {
      if (!this.submitted) return false;
      if (this.correct || this.isComeback) return true;
      if (this.effectiveStyle === 'tell') return this.tutor.messages.length > 0 && !this.tutor.loading;
      return this.tutor.retry.done;
    },
    canContinue() {
      if (!this.submitted) return false;
      if (!this.tutor.open) return true;
      if (this.tutor.loading) return false;
      if (this.effectiveStyle === 'tell') return this.tutor.messages.length > 0;
      return this.tutor.retry.done;
    },
    canChat() {
      const t = this.tutor;
      return t.open && !t.loading && !t.failed && t.turnsLeft > 0 && t.messages.length > 0 &&
        !t.retry.active && !t.retry.done;
    },
    canRetry() {
      const t = this.tutor;
      return t.open && this.effectiveStyle === 'teach' && !t.loading && t.messages.length > 0 &&
        !t.retry.active && !t.retry.done;
    },
    groupCount() {
      if (!this.studentsToday) return null;
      if (this.group !== 'direct') return this.studentsToday[this.group] || 0;
      return Object.values(this.studentsToday).reduce((a, b) => a + b, 0);
    },
  },

  async mounted() {
    api('/api/health').catch(() => {}); // wake a sleeping free server early
    this.flagsReady = await Flags.init(this.uid, this.group);
    const live = String(Flags.value('question_set', 'viva')).split(',').map((s) => s.trim());
    this.subjects = live.filter((s) => SUBJECT_NAMES[s]);
    api('/api/stats').then((r) => { this.studentsToday = r.studentsToday; }).catch(() => {});
    addEventListener('pagehide', () => Flags.flush());
  },

  methods: {
    subjectName(s) { return SUBJECT_NAMES[s] || s; },
    subjectTagline(s) { return SUBJECT_TAGLINES[s] || ''; },

    async start(subject) {
      this.loadError = '';
      try {
        const res = await fetch('questions/' + subject + '.json');
        const bank = await res.json();
        this.subject = subject;
        this.concepts = bank.concepts;
        this.begin([]);
      } catch (e) {
        this.loadError = 'Could not load the questions. Please refresh and try again.';
      }
    },

    // New session from the already-loaded bank; `priority` concept ids are asked first.
    begin(priority) {
      this.session = new Quiz.Session(this.concepts, {
        size: SESSION_SIZE, gap: COMEBACK_GAP, priority, seen: loadSeen(this.subject),
      });
      this.receipt = null;
      this.copied = false;
      this.screen = 'quiz';
      this.next();
    },

    practiseAgain() {
      this.begin(this.receipt ? this.receipt.stillShakyIds : []);
    },

    next() {
      this.selected = null;
      this.confidence = null;
      this.submitted = false;
      this.correct = false;
      this.tutor = freshTutor();
      this.item = this.session.next();
      if (!this.item) return this.finish();
      markSeen(this.subject, this.item.concept.id, this.concepts);
      this.q = this.session.question(this.item);
      window.scrollTo({ top: 0, behavior: 'smooth' });
    },

    pick(i) {
      if (this.tutor.retry.active) { this.tutor.retry.pick = i; return; }
      if (!this.submitted) this.selected = i;
    },

    submit() {
      if (this.selected === null || !this.confidence || this.submitted) return;
      this.submitted = true;
      this.correct = this.selected === this.q.answer;
      Flags.track('question_answered');
      if (this.isComeback) Flags.track('comeback_scored', this.correct ? 1 : 0);
      this.session.record(this.item, this.correct, this.confidence);
      this.logAnswer(this.item.kind, this.correct);
      if (!this.isComeback && !this.correct) this.openTutor();
    },

    logAnswer(kind, correct) {
      api('/api/answer', {
        uid: this.uid, group: this.group, qid: this.q.id, kind, correct,
        confidence: kind === 'retry' ? null : this.confidence, position: this.session.shown,
      }).catch(() => {});
    },

    openTutor() {
      this.tutor.open = true;
      this.askTutor('');
    },

    async askTutor(message) {
      const t = this.tutor;
      const history = t.messages.map((m) => ({ role: m.role, content: m.content }));
      if (message) t.messages.push({ role: 'user', content: message });
      t.loading = true;
      try {
        const res = await api('/api/tutor', {
          uid: this.uid, qid: this.q.id, chosen: this.selected, turn: t.turn, history, message,
        });
        t.style = res.style;
        t.turnsLeft = res.turnsLeft;
        t.messages.push({ role: 'assistant', content: res.reply });
        t.turn += 1;
      } catch (e) {
        // Server unreachable: show the written explanation so nobody is stuck.
        t.failed = true;
        t.style = t.style || 'tell';
        t.messages.push({ role: 'assistant', content: this.q.explanation });
      } finally {
        t.loading = false;
      }
    },

    sendChat() {
      const text = this.tutor.input.trim().slice(0, 300);
      if (!text) return;
      this.tutor.input = '';
      this.askTutor(text);
    },

    startRetry() {
      this.tutor.retry.active = true;
      this.tutor.retry.pick = null;
    },

    submitRetry() {
      const r = this.tutor.retry;
      if (r.pick === null) return;
      r.correct = r.pick === this.q.answer;
      r.active = false;
      r.done = true;
      this.logAnswer('retry', r.correct); // not scored: no Flagsmith event
    },

    optionClass(i) {
      const r = this.tutor.retry;
      return {
        chosen: (!this.submitted && this.selected === i) || (r.active && r.pick === i),
        wrong: this.submitted && i === this.selected && !this.correct,
        right: this.revealAnswer && i === this.q.answer,
      };
    },

    finish() {
      this.receipt = this.session.receipt();
      this.screen = 'receipt';
      Flags.flush();
    },

    chooseSubject() {
      this.screen = 'start';
      this.session = null;
      this.receipt = null;
    },

    async copyLink() {
      const link = this.shareLink;
      try {
        await navigator.clipboard.writeText(link);
        this.copied = true;
      } catch (e) {
        this.copied = link;
      }
    },
  },
}).mount('#app');
