import { useCallback, useEffect, useMemo, useState } from 'react';
import { api } from './api.js';

// Bump this when demoing a release: the header badge shows which build is live.
const UI_VERSION = '1.0.0';

const FILTERS = [
  { key: 'ALL', label: 'All' },
  { key: 'VERIFIED', label: 'Verified' },
  { key: 'DRIFT_DETECTED', label: 'Drift detected' },
  { key: 'ARCHIVED', label: 'Archived' },
];

const STATUS_LABEL = { VERIFIED: 'Verified', DRIFT_DETECTED: 'Drift detected', ARCHIVED: 'Archived' };

const EMPTY_SUMMARY = { total: 0, verified: 0, drift_detected: 0, archived: 0, avg_drift_score: 0, drift_threshold: 0.3 };

function driftLevel(score, threshold) {
  if (score >= threshold) return 'high';
  if (score >= threshold / 2) return 'medium';
  return 'low';
}

function timeAgo(iso) {
  // Timestamps are UTC; treat a value without an offset as UTC too.
  const stamp = /[zZ]|[+-]\d\d:\d\d$/.test(iso) ? iso : `${iso}Z`;
  const seconds = Math.max(0, (Date.now() - new Date(stamp).getTime()) / 1000);
  if (seconds < 60) return 'just now';
  if (seconds < 3600) return `${Math.floor(seconds / 60)} min ago`;
  if (seconds < 86400) return `${Math.floor(seconds / 3600)} h ago`;
  return `${Math.floor(seconds / 86400)} d ago`;
}

export default function App() {
  const [datasets, setDatasets] = useState([]);
  const [summary, setSummary] = useState(EMPTY_SUMMARY);
  const [filter, setFilter] = useState('ALL');
  const [search, setSearch] = useState('');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [apiUp, setApiUp] = useState(null);
  const [showForm, setShowForm] = useState(false);
  const [toast, setToast] = useState(null);

  const load = useCallback(async () => {
    try {
      const [list, stats] = await Promise.all([api.list(), api.summary()]);
      setDatasets(list);
      setSummary(stats);
      setError('');
      setApiUp(true);
    } catch (e) {
      setError(e.message);
      setApiUp(false);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
    const timer = setInterval(load, 10000);
    return () => clearInterval(timer);
  }, [load]);

  const notify = (message, tone = 'info') => {
    setToast({ message, tone });
    setTimeout(() => setToast(null), 3200);
  };

  const run = async (action, message, tone) => {
    try {
      await action();
      notify(message, tone);
      await load();
    } catch (e) {
      notify(e.message, 'danger');
    }
  };

  const visible = useMemo(() => {
    const term = search.trim().toLowerCase();
    return datasets.filter(
      (d) =>
        (filter === 'ALL' || d.status === filter) &&
        (!term || d.dataset_name.toLowerCase().includes(term) || d.version_tag.toLowerCase().includes(term)),
    );
  }, [datasets, filter, search]);

  const blocked = datasets.filter((d) => d.status === 'DRIFT_DETECTED');
  const threshold = summary.drift_threshold;

  return (
    <div className="page">
      <header className="topbar">
        <div className="brand">
          <span className="logo">
            <svg viewBox="0 0 32 32" aria-hidden="true">
              <path d="M5 20c4 0 4-8 8-8s4 8 8 8 3-4 5-4" />
            </svg>
          </span>
          <div>
            <b>DataDrift</b>
            <small>Dataset version &amp; schema quality monitor</small>
          </div>
        </div>
        <div className="topbar-right">
          <span className={`api-pill ${apiUp === false ? 'down' : apiUp ? 'up' : ''}`}>
            <i /> {apiUp === false ? 'API unreachable' : apiUp ? 'API healthy' : 'Connecting…'}
          </span>
          <span className="version">UI v{UI_VERSION}</span>
          <button className="btn primary" onClick={() => setShowForm(true)}>
            + Register snapshot
          </button>
        </div>
      </header>

      <main className="content">
        <section className="hero">
          <div>
            <p className="eyebrow">Pre-training data gate</p>
            <h1>Know your data before you train on it.</h1>
            <p className="muted">
              Every snapshot is scored for drift against the last verified baseline. Anything at or above{' '}
              <b>{threshold.toFixed(2)}</b> is blocked from training until someone reviews it.
            </p>
          </div>
        </section>

        {error && (
          <div className="alert">
            <b>Backend unavailable.</b> {error}. Check that the API and PostgreSQL are running.
          </div>
        )}

        <section className="kpis">
          <Kpi label="Snapshots tracked" value={summary.total} hint={`${summary.archived} archived`} tone="neutral" />
          <Kpi label="Verified" value={summary.verified} hint="Cleared for training" tone="good" />
          <Kpi label="Drift detected" value={summary.drift_detected} hint="Blocked from training" tone="bad" />
          <DriftGauge value={summary.avg_drift_score} threshold={threshold} />
        </section>

        <section className="grid">
          <div className="card registry">
            <div className="card-head">
              <div>
                <h2>Snapshot registry</h2>
                <p className="muted">Versioned training datasets and their latest quality checks.</p>
              </div>
              <input
                className="search"
                placeholder="Search dataset or version…"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
              />
            </div>
            <div className="tabs">
              {FILTERS.map((f) => (
                <button key={f.key} className={filter === f.key ? 'active' : ''} onClick={() => setFilter(f.key)}>
                  {f.label}
                  <span>{f.key === 'ALL' ? datasets.length : datasets.filter((d) => d.status === f.key).length}</span>
                </button>
              ))}
            </div>

            {loading ? (
              <div className="empty">Loading snapshots…</div>
            ) : (
              <div className="table-wrap">
                <table>
                  <thead>
                    <tr>
                      <th>Dataset</th>
                      <th className="num">Records</th>
                      <th className="num">Missing</th>
                      <th>Drift score</th>
                      <th>Status</th>
                      <th className="actions-col">Actions</th>
                    </tr>
                  </thead>
                  <tbody>
                    {visible.map((d) => (
                      <tr key={d.id} className={d.status === 'ARCHIVED' ? 'archived' : ''}>
                        <td>
                          <div className="dataset">
                            <b>{d.dataset_name}</b>
                            <code>{d.version_tag}</code>
                            <small>{timeAgo(d.created_at)}</small>
                          </div>
                        </td>
                        <td className="num mono">{d.record_count.toLocaleString()}</td>
                        <td className="num mono">{d.missing_pct.toFixed(1)}%</td>
                        <td>
                          <DriftBar score={d.drift_score} threshold={threshold} />
                        </td>
                        <td>
                          <span className={`badge ${d.status.toLowerCase()}`}>{STATUS_LABEL[d.status]}</span>
                        </td>
                        <td>
                          <div className="actions">
                            {d.status === 'VERIFIED' && (
                              <button
                                className="btn danger-soft"
                                onClick={() =>
                                  run(
                                    () => api.update(d.id, { status: 'DRIFT_DETECTED' }),
                                    `${d.dataset_name}@${d.version_tag} flagged for drift`,
                                    'danger',
                                  )
                                }
                              >
                                Flag drift
                              </button>
                            )}
                            {d.status === 'DRIFT_DETECTED' && (
                              <button
                                className="btn good-soft"
                                onClick={() =>
                                  run(
                                    () => api.update(d.id, { status: 'VERIFIED' }),
                                    `${d.dataset_name}@${d.version_tag} marked verified`,
                                    'good',
                                  )
                                }
                              >
                                Mark verified
                              </button>
                            )}
                            {d.status !== 'ARCHIVED' && (
                              <button
                                className="btn ghost"
                                onClick={() => run(() => api.archive(d.id), `${d.dataset_name}@${d.version_tag} archived`)}
                              >
                                Archive
                              </button>
                            )}
                            <button
                              className="btn ghost icon"
                              title="Purge permanently"
                              onClick={() => {
                                if (window.confirm(`Permanently purge ${d.dataset_name}@${d.version_tag}?`)) {
                                  run(() => api.purge(d.id), `${d.dataset_name}@${d.version_tag} purged`);
                                }
                              }}
                            >
                              ✕
                            </button>
                          </div>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                {!visible.length && (
                  <div className="empty">
                    {datasets.length ? 'No snapshots match this view.' : 'No snapshots yet. Register your first one.'}
                  </div>
                )}
              </div>
            )}
          </div>

          <aside className="card gate">
            <div className="card-head">
              <div>
                <h2>Training gate</h2>
                <p className="muted">Blocked right now.</p>
              </div>
              <span className={`gate-state ${blocked.length ? 'closed' : 'open'}`}>
                {blocked.length ? `${blocked.length} blocked` : 'All clear'}
              </span>
            </div>
            {blocked.length ? (
              <ul className="blocked">
                {blocked.map((d) => (
                  <li key={d.id}>
                    <span className="pulse" />
                    <div>
                      <b>{d.dataset_name}</b>
                      <small>
                        {d.version_tag} · drift {d.drift_score.toFixed(2)}
                      </small>
                    </div>
                  </li>
                ))}
              </ul>
            ) : (
              <div className="clear">
                <span>✓</span>
                <p>No drift detected. Every active snapshot is cleared for training.</p>
              </div>
            )}
            <div className="legend">
              <p className="eyebrow">Drift scale</p>
              <div className="scale">
                <span className="low">0 – {(threshold / 2).toFixed(2)} stable</span>
                <span className="medium">
                  {(threshold / 2).toFixed(2)} – {threshold.toFixed(2)} watch
                </span>
                <span className="high">≥ {threshold.toFixed(2)} drift</span>
              </div>
            </div>
          </aside>
        </section>
      </main>

      {showForm && (
        <RegisterModal
          threshold={threshold}
          onClose={() => setShowForm(false)}
          onSubmit={async (snapshot) => {
            await api.register(snapshot);
            setShowForm(false);
            notify(`${snapshot.dataset_name}@${snapshot.version_tag} registered`, 'good');
            load();
          }}
        />
      )}

      {toast && <div className={`toast ${toast.tone}`}>{toast.message}</div>}
    </div>
  );
}

function Kpi({ label, value, hint, tone }) {
  return (
    <div className={`kpi ${tone}`}>
      <small>{label}</small>
      <strong>{value}</strong>
      <span>{hint}</span>
    </div>
  );
}

function DriftGauge({ value, threshold }) {
  const level = driftLevel(value, threshold);
  const pct = Math.min(100, value * 100);
  return (
    <div className={`kpi gauge ${level}`}>
      <small>Average drift score</small>
      <strong>{value.toFixed(3)}</strong>
      <div className="gauge-track">
        <div className="gauge-fill" style={{ width: `${pct}%` }} />
        <div className="gauge-threshold" style={{ left: `${threshold * 100}%` }} title="Drift threshold" />
      </div>
      <span>Threshold {threshold.toFixed(2)} · active snapshots only</span>
    </div>
  );
}

function DriftBar({ score, threshold }) {
  const level = driftLevel(score, threshold);
  return (
    <div className={`drift ${level}`}>
      <div className="drift-track">
        <div className="drift-fill" style={{ width: `${Math.max(3, score * 100)}%` }} />
        <div className="drift-threshold" style={{ left: `${threshold * 100}%` }} />
      </div>
      <span className="mono">{score.toFixed(2)}</span>
    </div>
  );
}

function RegisterModal({ threshold, onClose, onSubmit }) {
  const [drift, setDrift] = useState(0.1);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const level = driftLevel(drift, threshold);

  const submit = async (e) => {
    e.preventDefault();
    const form = new FormData(e.currentTarget);
    setBusy(true);
    try {
      await onSubmit({
        dataset_name: form.get('dataset_name').trim(),
        version_tag: form.get('version_tag').trim(),
        record_count: Number(form.get('record_count')),
        missing_pct: Number(form.get('missing_pct')),
        drift_score: drift,
      });
    } catch (err) {
      setError(err.message);
      setBusy(false);
    }
  };

  return (
    <div className="backdrop" onClick={onClose}>
      <form className="modal" onSubmit={submit} onClick={(e) => e.stopPropagation()}>
        <div className="modal-head">
          <div>
            <p className="eyebrow">New snapshot</p>
            <h2>Register a dataset version</h2>
          </div>
          <button type="button" className="close" onClick={onClose} aria-label="Close">
            ×
          </button>
        </div>
        <div className="form-row">
          <label>
            Dataset name
            <input name="dataset_name" required maxLength={120} placeholder="customer-churn" />
          </label>
          <label>
            Version tag
            <input name="version_tag" required maxLength={60} placeholder="v1.2-cleaned" />
          </label>
        </div>
        <div className="form-row">
          <label>
            Record count
            <input name="record_count" type="number" min="0" required defaultValue={100000} />
          </label>
          <label>
            Missing values (%)
            <input name="missing_pct" type="number" min="0" max="100" step="0.1" required defaultValue={1.5} />
          </label>
        </div>
        <label>
          Drift score <span className={`drift-value ${level}`}>{drift.toFixed(2)}</span>
          <input
            type="range"
            min="0"
            max="1"
            step="0.01"
            value={drift}
            className={`slider ${level}`}
            onChange={(e) => setDrift(Number(e.target.value))}
          />
        </label>
        <p className={`hint ${level}`}>
          {drift >= threshold
            ? 'At or above the threshold: this snapshot will be registered as DRIFT_DETECTED.'
            : 'Below the threshold: this snapshot will be registered as VERIFIED.'}
        </p>
        {error && <div className="alert small">{error}</div>}
        <button className="btn primary full" disabled={busy}>
          {busy ? 'Registering…' : 'Register snapshot'}
        </button>
      </form>
    </div>
  );
}
