import { useMemo, useState } from 'react'
import { deriveHomeStats, CADENCE_NOUN, type Cadence } from '../lib/aggregates'
import type { Entry } from '../lib/api'
import './home.css'

/**
 * Home — the reason to come back (v1.1 redesign, ADR-045).
 *
 * Every number here is derived in the browser from the entry list the shell already fetched. No new
 * endpoint, no schema change, $0 added cost; promotion to a server-side aggregate is B-029 and this
 * component's props do not change when it happens.
 *
 * Two designed elements are deliberately absent rather than approximated, because their data does
 * not exist (ADR-045, and B-015 as the precedent for why fabricated content is a defect):
 *
 *   - The third stat card is "Longest streak" rather than "Résumés built" — there is no résumé list
 *     endpoint, and RESUMERUN items are TTL'd at 30 days (B-028). Substituting keeps the handoff's
 *     three-column rhythm; dropping the card would leave a row nobody designed.
 *   - The gap-analysis line ("Light on certifications…") is omitted — it needs résumé history plus
 *     an inference, and a per-load Bedrock call is the wrong shape against a $5 ceiling (B-030).
 */

type View = 'home' | 'log' | 'timeline' | 'resumes' | 'import' | 'details'

const CHIPS: { label: string; seed: string }[] = [
  { label: 'Shipped something', seed: 'I shipped ' },
  { label: 'Got recognized', seed: 'I was recognized for ' },
  { label: 'Presented or taught', seed: 'I presented ' },
  { label: 'Learned a skill', seed: 'I learned ' },
]

function greetingFor(hour: number): string {
  if (hour < 12) return 'Good morning'
  if (hour < 18) return 'Good afternoon'
  return 'Good evening'
}

function isoWeek(d: Date): number {
  const date = new Date(Date.UTC(d.getFullYear(), d.getMonth(), d.getDate()))
  const dayNum = date.getUTCDay() || 7
  date.setUTCDate(date.getUTCDate() + 4 - dayNum)
  const yearStart = new Date(Date.UTC(date.getUTCFullYear(), 0, 1))
  return Math.ceil(((date.getTime() - yearStart.getTime()) / 86_400_000 + 1) / 7)
}

const SHORT_DATE = new Intl.DateTimeFormat('en-GB', { month: 'short', year: '2-digit' })
const EYEBROW_DATE = new Intl.DateTimeFormat('en-GB', { weekday: 'short', day: 'numeric', month: 'short' })

export function Home({
  entries,
  cadence,
  name,
  onNavigate,
  onDraft,
}: {
  entries: Entry[] | null
  cadence: Cadence
  name: string | null
  onNavigate: (view: View) => void
  onDraft?: (text: string) => void
}) {
  const [draft, setDraft] = useState('')
  const now = useMemo(() => new Date(), [])
  const stats = useMemo(() => deriveHomeStats(entries ?? [], cadence, now), [entries, cadence, now])

  const noun = CADENCE_NOUN[cadence]
  const firstName = (name || '').trim().split(/\s+/)[0]
  const loading = entries === null
  const empty = !loading && entries.length === 0

  const start = () => {
    const text = draft.trim()
    if (text) onDraft?.(text)
    onNavigate('log')
  }

  const maxCategory = Math.max(...stats.categories.map((c) => c.count), 1)

  return (
    <div className="home">
      <div className="greeting-row">
        <div>
          <p className="eyebrow">
            {EYEBROW_DATE.format(now)} · week {isoWeek(now)}
          </p>
          <h1>
            {greetingFor(now.getHours())}
            {firstName ? `, ${firstName}.` : '.'}
          </h1>
        </div>
        <p className="next-checkin">
          Cadence <span>{noun}ly</span>
          <br />
          {stats.streak.current > 0
            ? `${stats.streak.current}-${noun} streak going`
            : `Log one entry to start a streak`}
        </p>
      </div>

      <section className="card composer" aria-labelledby="composer-heading">
        <h2 id="composer-heading" className="sr-only">
          Log an accomplishment
        </h2>
        <div className="composer-row">
          <label className="sr-only" htmlFor="home-composer">
            What did you accomplish?
          </label>
          <input
            id="home-composer"
            value={draft}
            placeholder="What did you accomplish? — a line is enough"
            onChange={(e) => setDraft(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter') {
                e.preventDefault()
                start()
              }
            }}
          />
          <button type="button" className="btn-primary" onClick={start}>
            Start logging
          </button>
        </div>
        <div className="chips">
          <span className="chips-label">Not sure where to start</span>
          {CHIPS.map((chip) => (
            <button
              key={chip.label}
              type="button"
              className="chip"
              onClick={() => {
                setDraft(chip.seed)
                document.getElementById('home-composer')?.focus()
              }}
            >
              {chip.label}
            </button>
          ))}
        </div>
      </section>

      <div className="stat-trio">
        <div className="card stat">
          <p className="stat-label">In the vault</p>
          <p className="stat-value">{loading ? '—' : stats.total}</p>
          <p className="stat-sub">
            {stats.sinceYear ? `entries since ${stats.sinceYear}` : 'nothing logged yet'}
          </p>
        </div>
        <div className="card stat">
          <p className="stat-label">This quarter</p>
          <p className="stat-value">{loading ? '—' : stats.thisQuarter}</p>
          <p className="stat-sub">
            {stats.lastQuarter > 0 ? `against ${stats.lastQuarter} last quarter` : 'first of the quarter'}
          </p>
        </div>
        {/* "Résumés built" in the handoff — substituted until a résumé list endpoint exists (B-028). */}
        <div className="card stat">
          <p className="stat-label">Longest streak</p>
          <p className="stat-value">{loading ? '—' : stats.streak.longest}</p>
          <p className="stat-sub">
            {stats.streak.longest === 1 ? `${noun} logged` : `${noun}s in a row`}
          </p>
        </div>
      </div>

      <section className="card year-grid" aria-labelledby="year-heading">
        <div className="card-head">
          <h2 id="year-heading">Your year in wins</h2>
          <p className="range">last 12 {noun === 'month' ? 'months' : 'months'}</p>
        </div>
        {/* Axis and cells share one wrapper on the same column track, so each month label sits above
            the week its month actually starts in — and both scroll together on a narrow viewport. */}
        <div className="grid-scroll">
          <div className="grid-inner" style={{ '--cols': stats.grid.columns } as React.CSSProperties}>
            <div
              className="grid-cells"
              role="img"
              aria-label={`Activity over the last year: ${stats.total} entries logged across ${stats.grid.columns} weeks`}
            >
              {stats.grid.cells.map((cell) => (
                <span
                  key={cell.date}
                  className="cell"
                  data-step={cell.step}
                  data-future={cell.future ? '' : undefined}
                  title={
                    cell.future
                      ? undefined
                      : `${cell.count} ${cell.count === 1 ? 'entry' : 'entries'} on ${cell.date}`
                  }
                />
              ))}
            </div>
            <div className="grid-axis" aria-hidden="true">
              {stats.grid.months.map((month) => (
                <span key={`${month.label}-${month.column}`} style={{ gridColumn: month.column }}>
                  {month.label}
                </span>
              ))}
            </div>
          </div>
        </div>
      </section>

      <div className="two-col">
        <section className="card" aria-labelledby="latest-heading">
          <h2 id="latest-heading">Latest in the vault</h2>
          {loading ? (
            <p className="muted">Loading…</p>
          ) : empty ? (
            <p className="muted">Nothing logged yet. The composer above is the fastest way in.</p>
          ) : (
            <ul className="latest-list">
              {stats.latest.map((entry) => (
                <li key={entry.entry_id}>
                  <span className="latest-title">{entry.title}</span>
                  <span className="latest-date">
                    {entry.created_at ? SHORT_DATE.format(new Date(entry.created_at)).toUpperCase() : ''}
                  </span>
                  <span className="latest-meta">
                    {String(entry.organization || entry.issuer || entry.entry_type || '')}
                  </span>
                </li>
              ))}
            </ul>
          )}
          <button type="button" className="link-btn" onClick={() => onNavigate('timeline')}>
            Open the full timeline →
          </button>
        </section>

        <section className="card" aria-labelledby="weight-heading">
          <h2 id="weight-heading">Where the weight is</h2>
          {loading || empty ? (
            <p className="muted">{loading ? 'Loading…' : 'No entries to weigh yet.'}</p>
          ) : (
            <ul className="weight-list">
              {stats.categories.map((category) => (
                <li key={category.type}>
                  <span className="weight-head">
                    <span>{category.label}</span>
                    <span className="weight-count">{category.count}</span>
                  </span>
                  <span className="track">
                    <span
                      className="fill"
                      style={{ width: `${(category.count / maxCategory) * 100}%` }}
                    />
                  </span>
                </li>
              ))}
            </ul>
          )}
        </section>
      </div>
    </div>
  )
}
