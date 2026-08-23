// frontend/src/pages/Simulator.tsx
//
// Modernist Telemetry Simulator.
// Supports:
// - Timeframe Granularity: Weekly (W1-W52), Monthly (M1-M12), Quarterly (Q1-Q4)
// - Instant 0ms reactive calculation on slider movement (updates score, chip, and deltas by the second)
// - Debounced LLM manager briefing generation
// - Scratch-only mode (never touches persistent memory or audit trail)

import { useState, useEffect, useMemo } from 'react';
import { SectionHeader } from '../components/SectionHeader';
import { ErrorNote } from '../components/ErrorNote';
import { FormattedBriefing } from '../components/FormattedBriefing';
import { api } from '../api/client';
import type { SimulationResult } from '../api/types';

function getBandClass(classification?: string | null): string {
  const c = (classification ?? '').toLowerCase();
  if (c.includes('healthy')) return 'healthy';
  if (c.includes('watch')) return 'watch';
  if (c.includes('at risk') || c.includes('risk')) return 'at-risk';
  if (c.includes('exit')) return 'exit';
  return 'healthy';
}

export function Simulator() {
  const [timeframe, setTimeframe] = useState<'weekly' | 'monthly' | 'quarterly'>('weekly');
  const [timeIndex, setTimeIndex] = useState(4); // e.g. Week 4, Month 2, Q1

  const [metrics, setMetrics] = useState({
    tasks_completed: 25,
    avg_response_time: 4,
    weekly_hours: 40,
    after_hours_logins: 2,
    collaboration_score: 70,
  });

  const [result, setResult] = useState<SimulationResult | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<Error | null>(null);

  // Instant local 0ms score calculation for real-time reactivity
  const instantScore = useMemo(() => {
    let raw = 1;
    if (metrics.tasks_completed < 15) raw += 3;
    else if (metrics.tasks_completed < 20) raw += 1;

    if (metrics.avg_response_time > 5) raw += 3;
    else if (metrics.avg_response_time > 2.5) raw += 2;

    if (metrics.after_hours_logins > 6) raw += 2;
    else if (metrics.after_hours_logins > 2) raw += 1;

    if (metrics.weekly_hours < 35) raw += 2;
    else if (metrics.weekly_hours > 50) raw += 1;

    const clamped = Math.max(1, Math.min(10, raw));
    let cls = 'Healthy';
    if (clamped >= 9) cls = 'Silent Exit';
    else if (clamped >= 7) cls = 'At Risk';
    else if (clamped >= 4) cls = 'Watch';

    return { score: clamped, classification: cls };
  }, [metrics]);

  useEffect(() => {
    const timer = setTimeout(async () => {
      setIsLoading(true);
      setError(null);
      try {
        const payload = {
          name: "Simulated Person",
          week_number: timeframe === 'weekly' ? timeIndex : timeIndex * 4,
          tasks_completed: metrics.tasks_completed,
          avg_response_time: metrics.avg_response_time,
          after_hours_logins: metrics.after_hours_logins,
          weekly_hours: metrics.weekly_hours,
          previous_classification: instantScore.classification,
          consecutive_weeks_elevated: instantScore.score >= 4 ? 2 : 0,
        };
        const data = await api.post<SimulationResult>('/score/custom', payload);
        setResult(data);
      } catch (err) {
        setError(err instanceof Error ? err : new Error('An error occurred during simulation.'));
      } finally {
        setIsLoading(false);
      }
    }, 250);

    return () => clearTimeout(timer);
  }, [metrics, timeframe, timeIndex, instantScore.classification, instantScore.score]);

  const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const { name, value } = e.target;
    setMetrics(prev => ({ ...prev, [name]: Number(value) }));
  };

  const displayScore = result?.risk_data?.score ?? instantScore.score;
  const displayClassification = result?.risk_data?.classification ?? instantScore.classification;
  const confidence = result?.risk_data?.confidence ?? (displayScore >= 7 ? 'high' : 'moderate');

  // Baseline comparison calculations (baseline: 25 tasks, 2.0h response, 40h weekly, 0 after-hours)
  const taskDelta = Math.round(((metrics.tasks_completed - 25) / 25) * 100);
  const responseDelta = Math.round(((metrics.avg_response_time - 2.0) / 2.0) * 100);
  const hoursDelta = Math.round(((metrics.weekly_hours - 40) / 40) * 100);

  return (
    <div className="simulator-page" aria-labelledby="simulator-title">
      <SectionHeader
        eyebrow="SIMULATOR"
        title="Try a shape of week and see what it scores."
        intro="Nothing here is stored. It exists so you can see what the model reacts to before you trust it with someone real."
      />

      {/* Timeframe Granularity Tabs */}
      <div style={{ display: 'flex', gap: '8px', margin: '1.25rem 0 1.5rem', borderBottom: '1px solid var(--rule)', paddingBottom: '10px', alignItems: 'center', flexWrap: 'wrap' }}>
        <span style={{ fontSize: '12px', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.08em', color: 'var(--muted)', marginRight: '8px' }}>
          Timeframe Mode:
        </span>
        {[
          { id: 'weekly', label: '📅 Weekly View (Weeks 1 – 52)' },
          { id: 'monthly', label: '📆 Monthly Aggregate (Months 1 – 12)' },
          { id: 'quarterly', label: '🏛️ Quarterly Review (Q1 – Q4)' },
        ].map((t) => {
          const isActive = timeframe === t.id;
          return (
            <button
              key={t.id}
              type="button"
              onClick={() => setTimeframe(t.id as any)}
              style={{
                padding: '6px 12px',
                fontSize: '12.5px',
                fontWeight: isActive ? 700 : 500,
                border: '1px solid',
                borderColor: isActive ? 'var(--accent)' : 'var(--rule)',
                background: isActive ? 'var(--accent-bg)' : 'var(--surface)',
                color: isActive ? 'var(--ink)' : 'var(--muted)',
                cursor: 'pointer',
              }}
            >
              {t.label}
            </button>
          );
        })}
      </div>

      {/* 1-Click Behavioral Archetype Presets */}
      <div style={{ marginBottom: '1.25rem', padding: '12px 14px', background: 'var(--surface)', border: '1px solid var(--rule)' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '8px' }}>
          <span style={{ fontSize: '11.5px', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.06em', color: 'var(--muted)' }}>
            Quick Archetype Presets (1-Click Load)
          </span>
          <span style={{ fontSize: '11px', color: 'var(--muted)' }}>Uncommitted</span>
        </div>
        <div style={{ display: 'flex', gap: '6px', flexWrap: 'wrap' }}>
          {[
            { label: "🟢 Baseline Healthy", values: { tasks_completed: 28, avg_response_time: 1.5, weekly_hours: 40, after_hours_logins: 1, collaboration_score: 85 } },
            { label: "⚠️ Response Friction", values: { tasks_completed: 22, avg_response_time: 6.5, weekly_hours: 40, after_hours_logins: 2, collaboration_score: 65 } },
            { label: "🚨 Overwork Burnout", values: { tasks_completed: 36, avg_response_time: 2.0, weekly_hours: 56, after_hours_logins: 12, collaboration_score: 75 } },
            { label: "📉 Progressive Drop", values: { tasks_completed: 8, avg_response_time: 14.0, weekly_hours: 34, after_hours_logins: 0, collaboration_score: 35 } },
            { label: "🛑 Silent Exit", values: { tasks_completed: 2, avg_response_time: 28.0, weekly_hours: 24, after_hours_logins: 0, collaboration_score: 15 } },
          ].map((preset) => (
            <button
              key={preset.label}
              type="button"
              onClick={() => setMetrics(preset.values)}
              style={{
                padding: '4px 9px',
                fontSize: '11.5px',
                fontWeight: 600,
                border: '1px solid var(--rule)',
                background: 'var(--paper)',
                color: 'var(--ink)',
                cursor: 'pointer',
              }}
            >
              {preset.label}
            </button>
          ))}
        </div>
      </div>

      <div className="simulator-layout">
        <aside className="simulator-controls">
          <div style={{ marginBottom: '1.25rem', padding: '10px 12px', background: 'var(--paper)', border: '1px solid var(--rule)' }}>
            <label htmlFor="time-selector" style={{ display: 'block', fontSize: '12px', fontWeight: 600, color: 'var(--ink)', marginBottom: '4px' }}>
              {timeframe === 'weekly' ? 'Simulation Target Week' : (timeframe === 'monthly' ? 'Simulation Target Month' : 'Simulation Target Quarter')}
            </label>
            <input
              id="time-selector"
              type="number"
              min={1}
              max={timeframe === 'weekly' ? 52 : (timeframe === 'monthly' ? 12 : 4)}
              value={timeIndex}
              onChange={(e) => setTimeIndex(Number(e.target.value))}
              style={{ width: '100%', padding: '6px 8px', border: '1px solid var(--rule)', background: 'var(--surface)', color: 'var(--ink)' }}
            />
          </div>

          <div className="control-group">
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <label htmlFor="tasks_completed">
                Tasks completed: <strong>{metrics.tasks_completed}</strong>
              </label>
              <span style={{ fontSize: '11px', color: taskDelta < 0 ? 'var(--exit)' : 'var(--healthy)', fontWeight: 600 }}>
                {taskDelta > 0 ? `+${taskDelta}%` : `${taskDelta}%`} vs base
              </span>
            </div>
            <input
              type="range"
              id="tasks_completed"
              name="tasks_completed"
              min="0"
              max="50"
              value={metrics.tasks_completed}
              onChange={handleChange}
              aria-label="Tasks completed"
            />
          </div>

          <div className="control-group">
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <label htmlFor="avg_response_time">
                Avg response time: <strong>{metrics.avg_response_time}h</strong>
              </label>
              <span style={{ fontSize: '11px', color: responseDelta > 0 ? 'var(--exit)' : 'var(--healthy)', fontWeight: 600 }}>
                {responseDelta > 0 ? `+${responseDelta}%` : `${responseDelta}%`} vs base
              </span>
            </div>
            <input
              type="range"
              id="avg_response_time"
              name="avg_response_time"
              min="0"
              max="72"
              step="0.5"
              value={metrics.avg_response_time}
              onChange={handleChange}
              aria-label="Average response time in hours"
            />
          </div>

          <div className="control-group">
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <label htmlFor="weekly_hours">
                Weekly hours: <strong>{metrics.weekly_hours}h</strong>
              </label>
              <span style={{ fontSize: '11px', color: 'var(--muted)', fontWeight: 600 }}>
                {hoursDelta !== 0 ? `${hoursDelta > 0 ? '+' : ''}${hoursDelta}%` : 'Standard 40h'}
              </span>
            </div>
            <input
              type="range"
              id="weekly_hours"
              name="weekly_hours"
              min="0"
              max="80"
              value={metrics.weekly_hours}
              onChange={handleChange}
              aria-label="Weekly hours"
            />
          </div>

          <div className="control-group">
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <label htmlFor="after_hours_logins">
                After-hours logins: <strong>{metrics.after_hours_logins}</strong>
              </label>
              <span style={{ fontSize: '11px', color: metrics.after_hours_logins > 2 ? 'var(--exit)' : 'var(--muted)', fontWeight: 600 }}>
                {metrics.after_hours_logins > 2 ? 'Strain signal' : 'Standard'}
              </span>
            </div>
            <input
              type="range"
              id="after_hours_logins"
              name="after_hours_logins"
              min="0"
              max="30"
              value={metrics.after_hours_logins}
              onChange={handleChange}
              aria-label="After-hours logins"
            />
          </div>

          <div className="control-group">
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <label htmlFor="collaboration_score">
                Collaboration score: <strong>{metrics.collaboration_score}</strong>
              </label>
              <span style={{ fontSize: '11px', color: 'var(--muted)', fontWeight: 600 }}>
                {metrics.collaboration_score}/100
              </span>
            </div>
            <input
              type="range"
              id="collaboration_score"
              name="collaboration_score"
              min="0"
              max="100"
              value={metrics.collaboration_score}
              onChange={handleChange}
              aria-label="Collaboration score"
            />
          </div>
        </aside>

        <main className="simulator-results">
          {error && <ErrorNote error={error} />}

          <div className={`results-container ${isLoading ? 'is-updating' : ''}`}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '16px', marginBottom: '12px' }}>
              <div className="simulator-score__numeral" style={{ flexShrink: 0 }}>
                {displayScore}
              </div>
              <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-start', gap: '4px' }}>
                <span
                  className={`chip chip--${getBandClass(displayClassification)}`}
                  style={{ display: 'inline-flex', width: 'fit-content', whiteSpace: 'nowrap', alignSelf: 'flex-start' }}
                >
                  {displayClassification}
                </span>
                <span className="confidence-indicator" style={{ fontSize: '11.5px', color: 'var(--muted)', whiteSpace: 'nowrap' }}>
                  Confidence: {confidence} {isLoading && '· Updating briefing...'}
                </span>
              </div>
            </div>

            <div className="simulator-briefing">
              <h2>Supportive Coaching Briefing Preview</h2>
              <FormattedBriefing text={result?.briefing || "Evaluating metrics against baseline..."} />
            </div>

            {result?.signals && result.signals.length > 0 && (
              <div className="simulator-attributions" style={{ marginTop: '1.25rem', padding: '1rem', background: 'var(--surface)', border: '1px solid var(--rule)' }}>
                <h3 style={{ margin: '0 0 8px', fontSize: '13px', letterSpacing: '0.08em', textTransform: 'uppercase', color: 'var(--muted)' }}>
                  Detected Divergence Signals
                </h3>
                <ul style={{ margin: 0, paddingLeft: '1.2rem', fontSize: '13px', lineHeight: '1.6', color: 'var(--ink)' }}>
                  {result.signals.map((sig, idx) => (
                    <li key={idx}>
                      <strong>{sig.signal_name ?? sig.signal ?? 'Signal'}:</strong> {sig.details ?? 'Divergence from personal trajectory detected.'}
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </div>

          <div className="scratch-notice">
            <p>Scratch only — nothing here modifies stored data.</p>
          </div>
        </main>
      </div>
    </div>
  );
}
