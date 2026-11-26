# Tell Me or Teach Me

**Should an AI tutor give students the answer?** A free practice-quiz app with an AI tutor, used by real
students from course WhatsApp groups. After a wrong answer, one Flagsmith flag decides whether the same AI
**tells** the answer or **teaches** with guiding questions. A **comeback question**, the same idea in new
words, measures whether the learning stuck.

Toggle Wars (WeMakeDevs × Flagsmith) · Track 01: Test Something Real

- Demo video: _add link_
- Live app: _add link_
- Pre-registered design: [EXPERIMENT.md](EXPERIMENT.md)

## How Flagsmith is used

| Flag | Kind | Job |
|---|---|---|
| `tutor_style` | Multivariate, the experiment | `tell` (control) or `teach` (treatment), evaluated **on the server** (`backend/flags.py`) |
| `ai_tutor_enabled` | On/off | Kill switch: turns the live AI off, each style falls back to its written version, no redeploy |
| `tutor_limits` | Remote config (JSON) | Tutor replies per mistake and per student per day, to stay inside free AI tiers |
| `question_set` | Remote config | Which subjects are live, read by the browser; new sets are released without a redeploy |
| `group` trait + segments | Traits | Each WhatsApp group link (`?g=mlt`) sets a trait for per-group analysis and rollout |

Events and exposure:

- **Exposure** is recorded by the server (`track_exposure_event`) the first time the tutor replies, the
  moment the two styles start to differ (`backend/tutor.py`).
- **`comeback_scored`** (1 or 0) is sent by the browser on every comeback question: the primary metric,
  aggregated as a Mean (`frontend/app.js`).
- **`question_answered`** is sent on every scored answer: practice volume.
- Browser and server identify students with the same anonymous ID, so Flagsmith joins exposures and events.
- **Staging** holds simulated students (`backend/simulate.py`, including an A/A check); **production** holds
  only real students. Each environment has its own warehouse.

## Results

_Frozen on Sunday 29 November 2026, 12:00 IST. Add: real exposures per style, probability to win, lift,
credible interval, comeback completion per style, AI provider mix per style, leak-guard count, decision._

## Run it locally

You need Python 3.11+ and a Flagsmith account.

1. **Flagsmith**, in the dashboard (see the setup checklist below), create the four flags and the metric.
2. **Backend**
   ```bash
   cd backend
   python -m venv .venv
   source .venv/bin/activate        # Windows: .venv\Scripts\activate
   pip install -r requirements.txt
   cp .env.example .env             # then fill in the keys
   python app.py                    # runs on http://localhost:5000
   ```
   Open http://localhost:5000/api/health: it lists the AI providers it found keys for.
3. **Frontend**: put the client-side key in `frontend/config.js`, then
   ```bash
   cd frontend
   python -m http.server 5173
   ```
   Open http://localhost:5173/?g=mlt (use a local server, not the file directly).

> The browser key (`config.js`) and the server key (`backend/.env`) must come from the **same environment**,
> or exposures and events land in different places.

### Flagsmith setup checklist

1. Project `tell-or-teach` with environments **staging** and **production**.
2. In each environment's settings, connect the **Flagsmith managed warehouse**.
3. Flags:
   - `tutor_style`: multivariate; control value `tell`; one variation with value `teach`. Give every variation a key.
   - `ai_tutor_enabled`: enabled.
   - `tutor_limits`: enabled, value `{"max_turns": 3, "daily_cap": 40}`.
   - `question_set`: enabled, value `mlt,viva`.
4. Metric **Comeback accuracy**: aggregation Mean, event `comeback_scored`, higher is better.
5. Keys: the client-side key goes in `frontend/config.js`; create a server-side key for `backend/.env`.
6. Experiment: flag `tutor_style`, rollout 100%, split evenly, primary metric Comeback accuracy, expected
   to increase. **Creating it starts it**, and an ended experiment can't be restarted.

### Simulator (staging only)

```bash
cd backend
STAGING_SERVER_KEY=ser.xxx python simulate.py --students 300                          # A/A check
STAGING_SERVER_KEY=ser.xxx python simulate.py --students 300 --p-tell 0.55 --p-teach 0.70
```

## Deploy

- **Database**: a free Postgres on Neon or Supabase; put its URL in `DATABASE_URL`.
- **Backend** (e.g. Render web service): root directory `backend`, build `pip install -r requirements.txt`,
  start `gunicorn app:app`, and the variables from `.env.example`. Set `ALLOWED_ORIGIN` to the frontend URL.
- **Frontend** (e.g. Netlify, Vercel or GitHub Pages): publish the `frontend` folder as a static site with
  `config.js` pointing at the backend and the production client-side key.

## Project layout

```
backend/
  app.py         Flask routes: /api/tutor, /api/answer, /api/stats, /api/health
  tutor.py       the two prompts, AI provider chain, answer-leak guard, written fallbacks
  flags.py       everything the server asks Flagsmith
  db.py          answer and tutor-turn log (SQLite locally, Postgres deployed)
  questions.py   loads and checks the twin-question files
  simulate.py    simulated students for staging
frontend/
  index.html     the three screens: start, quiz, learning receipt
  app.js         screen logic and the tutor panel
  quiz.js        question order and comeback scheduling
  flags.js       Flagsmith in the browser: question_set and events
  questions/     one JSON file per subject; each concept has two twin questions
```

## AI tools used

_Describe honestly: e.g. AI assistance for drafting code and question content; every question and answer was
checked by hand._
