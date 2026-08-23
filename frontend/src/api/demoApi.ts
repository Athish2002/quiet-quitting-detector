// frontend/src/api/demoApi.ts
//
// In-browser mock API for GitHub Pages deployment (demo mode).
//
// When the app detects it is running on GitHub Pages (or VITE_DEMO_MODE=true),
// all API calls are routed here instead of making real fetch() requests.
// This provides a fully interactive demo with realistic data — every page
// renders, every slider moves, every role works.
//
// The data is deterministic (no randomness) so the demo is reproducible.

// ─── Demo Employees ─────────────────────────────────────────────────────────

interface DemoEmployee {
  name: string;
  score: number;
  classification: "Healthy" | "Watch" | "At Risk" | "Silent Exit";
  rationale: string;
  latest_week: number;
  signals: Array<{
    signal_name: string;
    signal: string | null;
    severity: "high" | "medium" | "low";
    weeks_detected: number[];
    details: string | null;
  }>;
  confidence: "high" | "moderate" | "low" | "none";
  score_range: [number, number];
  attributions: Array<{
    metric: string;
    contribution: number;
    effect_size: number;
    direction: "above" | "below";
    weeks: number[];
  }>;
  model_version: string;
  degraded: boolean;
  history: Array<{
    week: number;
    score: number;
    classification: "Healthy" | "Watch" | "At Risk" | "Silent Exit";
  }>;
}

type Classification = "Healthy" | "Watch" | "At Risk" | "Silent Exit";

function buildHistory(
  weeks: number[],
  scores: number[],
  classifications: Classification[],
): Array<{ week: number; score: number; classification: Classification }> {
  return weeks.map((w, i) => ({
    week: w,
    score: scores[i]!,
    classification: classifications[i]!,
  }));
}

const DEMO_EMPLOYEES: DemoEmployee[] = [
  {
    name: "Arjun",
    score: 2,
    classification: "Healthy",
    rationale:
      "Consistent task completion and collaboration across all tracked weeks. No divergence from personal baseline.",
    latest_week: 12,
    signals: [],
    confidence: "high",
    score_range: [1, 3],
    attributions: [
      { metric: "completed_tasks", contribution: 0.08, effect_size: 0.05, direction: "above", weeks: [11, 12] },
    ],
    model_version: "demo-v1",
    degraded: false,
    history: buildHistory(
      [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12],
      [2, 2, 2, 2, 3, 2, 2, 2, 2, 2, 2, 2],
      ["Healthy","Healthy","Healthy","Healthy","Healthy","Healthy","Healthy","Healthy","Healthy","Healthy","Healthy","Healthy"],
    ),
  },
  {
    name: "Divya",
    score: 2,
    classification: "Healthy",
    rationale:
      "Steady metrics with strong collaboration scores. After-hours activity is minimal and stable.",
    latest_week: 12,
    signals: [],
    confidence: "high",
    score_range: [1, 3],
    attributions: [
      { metric: "collaboration_score", contribution: 0.12, effect_size: 0.08, direction: "above", weeks: [10, 11, 12] },
    ],
    model_version: "demo-v1",
    degraded: false,
    history: buildHistory(
      [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12],
      [2, 2, 1, 2, 2, 2, 2, 2, 2, 2, 2, 2],
      ["Healthy","Healthy","Healthy","Healthy","Healthy","Healthy","Healthy","Healthy","Healthy","Healthy","Healthy","Healthy"],
    ),
  },
  {
    name: "Priya",
    score: 7,
    classification: "At Risk",
    rationale:
      "Declining task completion over three consecutive weeks. Response latency has increased 280% from personal baseline.",
    latest_week: 12,
    signals: [
      {
        signal_name: "Declining Task Completion",
        signal: null,
        severity: "high",
        weeks_detected: [10, 11, 12],
        details: "Tasks dropped from 25 to 10 over weeks 10–12.",
      },
      {
        signal_name: "Response Latency Spike",
        signal: null,
        severity: "medium",
        weeks_detected: [11, 12],
        details: "Average response time rose from 2.4h to 8.0h.",
      },
    ],
    confidence: "low",
    score_range: [5, 9],
    attributions: [
      { metric: "completed_tasks", contribution: 0.65, effect_size: 0.35, direction: "below", weeks: [10, 11, 12] },
      { metric: "avg_response_time", contribution: 0.25, effect_size: 0.18, direction: "below", weeks: [11, 12] },
    ],
    model_version: "demo-v1",
    degraded: false,
    history: buildHistory(
      [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12],
      [2, 3, 3, 3, 4, 4, 5, 5, 6, 6, 7, 7],
      ["Healthy","Healthy","Healthy","Healthy","Watch","Watch","Watch","Watch","At Risk","At Risk","At Risk","At Risk"],
    ),
  },
  {
    name: "Rajesh",
    score: 4,
    classification: "Watch",
    rationale:
      "Moderate increase in after-hours logins with slight dip in collaboration score. Pattern started 3 weeks ago.",
    latest_week: 12,
    signals: [
      {
        signal_name: "After-Hours Activity Increase",
        signal: null,
        severity: "medium",
        weeks_detected: [10, 11, 12],
        details: "After-hours logins rose from 2 to 7 over 3 weeks.",
      },
    ],
    confidence: "moderate",
    score_range: [3, 6],
    attributions: [
      { metric: "after_hours_logins", contribution: 0.40, effect_size: 0.20, direction: "below", weeks: [10, 11, 12] },
      { metric: "collaboration_score", contribution: 0.20, effect_size: 0.10, direction: "below", weeks: [11, 12] },
    ],
    model_version: "demo-v1",
    degraded: false,
    history: buildHistory(
      [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12],
      [2, 2, 2, 2, 2, 3, 3, 3, 3, 4, 4, 4],
      ["Healthy","Healthy","Healthy","Healthy","Healthy","Healthy","Healthy","Healthy","Healthy","Watch","Watch","Watch"],
    ),
  },
  {
    name: "Meera",
    score: 9,
    classification: "Silent Exit",
    rationale:
      "Near-complete disengagement across all metrics for 4 consecutive weeks. Task completion at 5% of baseline.",
    latest_week: 12,
    signals: [
      {
        signal_name: "Severe Task Completion Drop",
        signal: null,
        severity: "high",
        weeks_detected: [9, 10, 11, 12],
        details: "Tasks dropped from 22 to 2 over 4 weeks.",
      },
      {
        signal_name: "Communication Withdrawal",
        signal: null,
        severity: "high",
        weeks_detected: [10, 11, 12],
        details: "Collaboration score dropped from 78 to 15.",
      },
    ],
    confidence: "high",
    score_range: [8, 10],
    attributions: [
      { metric: "completed_tasks", contribution: 0.55, effect_size: 0.45, direction: "below", weeks: [9, 10, 11, 12] },
      { metric: "collaboration_score", contribution: 0.30, effect_size: 0.25, direction: "below", weeks: [10, 11, 12] },
    ],
    model_version: "demo-v1",
    degraded: false,
    history: buildHistory(
      [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12],
      [2, 2, 3, 3, 4, 5, 6, 7, 8, 9, 9, 9],
      ["Healthy","Healthy","Healthy","Healthy","Watch","Watch","At Risk","At Risk","At Risk","Silent Exit","Silent Exit","Silent Exit"],
    ),
  },
  {
    name: "Kiran",
    score: 3,
    classification: "Healthy",
    rationale:
      "Slightly elevated response time this week but within normal variance. All other metrics stable.",
    latest_week: 12,
    signals: [],
    confidence: "high",
    score_range: [2, 4],
    attributions: [
      { metric: "avg_response_time", contribution: 0.15, effect_size: 0.08, direction: "below", weeks: [12] },
    ],
    model_version: "demo-v1",
    degraded: false,
    history: buildHistory(
      [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12],
      [2, 2, 2, 3, 2, 2, 3, 2, 2, 3, 3, 3],
      ["Healthy","Healthy","Healthy","Healthy","Healthy","Healthy","Healthy","Healthy","Healthy","Healthy","Healthy","Healthy"],
    ),
  },
  {
    name: "Sunita",
    score: 5,
    classification: "Watch",
    rationale:
      "Weekly hours have trended upward for 5 weeks while collaboration score has declined. Possible overwork pattern.",
    latest_week: 12,
    signals: [
      {
        signal_name: "Sustained Overwork",
        signal: null,
        severity: "medium",
        weeks_detected: [8, 9, 10, 11, 12],
        details: "Weekly hours rose from 40 to 54 over 5 weeks.",
      },
    ],
    confidence: "moderate",
    score_range: [3, 7],
    attributions: [
      { metric: "weekly_hours", contribution: 0.45, effect_size: 0.22, direction: "below", weeks: [8, 9, 10, 11, 12] },
      { metric: "collaboration_score", contribution: 0.18, effect_size: 0.10, direction: "below", weeks: [10, 11, 12] },
    ],
    model_version: "demo-v1",
    degraded: false,
    history: buildHistory(
      [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12],
      [2, 2, 2, 2, 3, 3, 3, 4, 4, 5, 5, 5],
      ["Healthy","Healthy","Healthy","Healthy","Healthy","Healthy","Healthy","Watch","Watch","Watch","Watch","Watch"],
    ),
  },
  {
    name: "Vikram",
    score: 6,
    classification: "At Risk",
    rationale:
      "Response time has nearly doubled over 6 weeks alongside declining task completion. Pattern consistent with disengagement.",
    latest_week: 12,
    signals: [
      {
        signal_name: "Gradual Disengagement",
        signal: null,
        severity: "high",
        weeks_detected: [9, 10, 11, 12],
        details: "Combined decline in task completion and rising response latency over 4 weeks.",
      },
    ],
    confidence: "moderate",
    score_range: [4, 8],
    attributions: [
      { metric: "avg_response_time", contribution: 0.40, effect_size: 0.25, direction: "below", weeks: [7, 8, 9, 10, 11, 12] },
      { metric: "completed_tasks", contribution: 0.35, effect_size: 0.18, direction: "below", weeks: [9, 10, 11, 12] },
    ],
    model_version: "demo-v1",
    degraded: false,
    history: buildHistory(
      [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12],
      [2, 2, 3, 3, 3, 4, 4, 5, 5, 6, 6, 6],
      ["Healthy","Healthy","Healthy","Healthy","Healthy","Watch","Watch","Watch","Watch","At Risk","At Risk","At Risk"],
    ),
  },
];

// ─── Demo Calibration ────────────────────────────────────────────────────────

const DEMO_CALIBRATION = {
  overall: {
    total: 23,
    accurate: 18,
    not_accurate: 4,
    harmful: 1,
    accuracy_rate: 0.78,
  },
  review_required: false,
};

// ─── Demo Model Status ───────────────────────────────────────────────────────

const DEMO_MODEL_STATUS = {
  fallback_sequence: ["gemini-2.5-flash", "gemini-2.5-pro", "local-deterministic"],
  last_successful_model: "demo-mode",
  exhausted_models: [],
  local_only_mode: false,
  model_mode: "auto",
  selected_model: "demo-mode",
};

// ─── Demo Run Progress ───────────────────────────────────────────────────────

const DEMO_RUN_PROGRESS = {
  running: false,
  total: 0,
  done: 0,
  current: null,
};

// ─── Demo History Events ─────────────────────────────────────────────────────

const DEMO_HISTORY_EVENTS = [
  {
    timestamp: new Date(Date.now() - 86400000 * 1).toISOString(),
    action: "run_completed",
    detail: "Pipeline evaluated 8 employees for week 12.",
    actor: "system",
  },
  {
    timestamp: new Date(Date.now() - 86400000 * 2).toISOString(),
    action: "ingest",
    detail: "CSV upload: 8 employees × 12 weeks (96 records).",
    actor: "analyst",
  },
  {
    timestamp: new Date(Date.now() - 86400000 * 3).toISOString(),
    action: "run_completed",
    detail: "Pipeline evaluated 8 employees for week 11.",
    actor: "system",
  },
  {
    timestamp: new Date(Date.now() - 86400000 * 5).toISOString(),
    action: "feedback",
    detail: "Manager submitted verdict: accurate for Arjun (week 10).",
    actor: "manager",
  },
  {
    timestamp: new Date(Date.now() - 86400000 * 7).toISOString(),
    action: "ingest",
    detail: "Mock data seeded: 8 employees × 10 weeks.",
    actor: "analyst",
  },
  {
    timestamp: new Date(Date.now() - 86400000 * 10).toISOString(),
    action: "system_start",
    detail: "Quiet-Quitting Detector initialised. Demo mode active.",
    actor: "system",
  },
];

// ─── Demo Audit Log ──────────────────────────────────────────────────────────

const DEMO_AUDIT_LOG = [
  {
    timestamp: new Date(Date.now() - 3600000 * 2).toISOString(),
    accessor: "analyst",
    subject: "Priya",
    action: "view_assessment",
    status: "granted" as const,
    hash: "a3f8c2d1e4b5...",
  },
  {
    timestamp: new Date(Date.now() - 3600000 * 4).toISOString(),
    accessor: "manager",
    subject: "Meera",
    action: "view_briefing",
    status: "granted" as const,
    hash: "b7d2e9f1a3c6...",
  },
  {
    timestamp: new Date(Date.now() - 3600000 * 8).toISOString(),
    accessor: "viewer",
    subject: "Arjun",
    action: "view_assessment",
    status: "refused" as const,
    hash: "c1e4f8a2b5d7...",
  },
  {
    timestamp: new Date(Date.now() - 86400000 * 1).toISOString(),
    accessor: "analyst",
    subject: "Vikram",
    action: "view_assessment",
    status: "granted" as const,
    hash: "d5a8b1c4e7f2...",
  },
];

// ─── Demo Intervention Outcomes ──────────────────────────────────────────────

const DEMO_INTERVENTION_OUTCOMES = {
  by_type: [
    {
      type: "workload_review",
      total: 5,
      accepted: 4,
      dismissed: 1,
      effectiveness: 0.80,
    },
    {
      type: "1on1_check_in",
      total: 8,
      accepted: 7,
      dismissed: 1,
      effectiveness: 0.88,
    },
    {
      type: "project_reassignment",
      total: 2,
      accepted: 1,
      dismissed: 1,
      effectiveness: 0.50,
    },
  ],
};

// ─── Demo Briefings ──────────────────────────────────────────────────────────

const DEMO_BRIEFINGS: Record<string, { found: boolean; briefing: string; raw_card: string }> = {
  Arjun: {
    found: true,
    briefing:
      "Arjun's telemetry is stable across all tracked dimensions. Task completion has been consistently above baseline for 12 weeks, and collaboration scores remain strong. No intervention is suggested — this is a pattern of sustained, healthy engagement. Consider acknowledging this consistency in your next 1-on-1.",
    raw_card: "Stable baseline. No divergence detected.",
  },
  Divya: {
    found: true,
    briefing:
      "Divya shows excellent consistency across all metrics. Collaboration scores are among the strongest in the cohort. After-hours activity is minimal, suggesting healthy work boundaries. A good candidate for peer mentoring or team lead responsibilities if she's interested.",
    raw_card: "Strong baseline. Excellent collaboration.",
  },
  Priya: {
    found: true,
    briefing:
      "Priya's telemetry shows a sustained decline over the past 3 weeks. Task completion has dropped significantly and response latency has increased. This pattern is consistent with someone who may be struggling with workload or personal circumstances. A supportive conversation — not about the numbers — would be appropriate. Ask open questions: 'How is your workload pacing lately?' or 'Is there anything we can clear from your plate this week?'",
    raw_card: "Declining trajectory. Supportive check-in recommended.",
  },
  Rajesh: {
    found: true,
    briefing:
      "Rajesh has shown a moderate increase in after-hours logins over the past 3 weeks. This could indicate a challenging project deadline or difficulty completing work during regular hours. Worth exploring whether workload redistribution would help. Frame the conversation around support: 'I noticed some late-night activity — is there anything blocking you during the day?'",
    raw_card: "After-hours increase. Workload check recommended.",
  },
  Meera: {
    found: true,
    briefing:
      "Meera's metrics have dropped significantly across all dimensions over 4 consecutive weeks. This is the most pronounced pattern in the current cohort. Before any work-related conversation, consider whether there are personal circumstances to be sensitive to. If initiating a check-in, lead with care: 'I wanted to check in — how are you doing? Is there anything I can help with?'",
    raw_card: "Significant disengagement. Compassionate check-in needed.",
  },
  Kiran: {
    found: true,
    briefing:
      "Kiran's metrics are largely stable with a minor uptick in response time this week. This is within normal variance and does not suggest a pattern. No action needed at this time, but worth keeping on the radar if the trend continues for 2+ more weeks.",
    raw_card: "Minor variance. No action needed.",
  },
  Sunita: {
    found: true,
    briefing:
      "Sunita has been logging progressively longer weeks over the past 5 weeks, from 40h to 54h. While task completion remains acceptable, this pattern suggests potential overwork that could lead to burnout. Consider proactively discussing workload balance: 'I want to make sure your workload is sustainable. Can we review your current projects together?'",
    raw_card: "Overwork pattern. Proactive workload review suggested.",
  },
  Vikram: {
    found: true,
    briefing:
      "Vikram shows a gradual decline in task completion alongside rising response times over 6 weeks. The pattern is consistent with disengagement, though the underlying cause is unknown. A non-confrontational check-in would be appropriate. Focus on removing blockers: 'I noticed things seem to be moving slower than usual — is there anything getting in the way that I can help clear?'",
    raw_card: "Gradual disengagement. Blocker-focused check-in recommended.",
  },
};

// ─── Route Handlers ──────────────────────────────────────────────────────────

/**
 * Resolves a demo API request. Returns the data that would come from the
 * backend, or null if the path is unrecognised.
 */
export function demoResolve(
  method: string,
  path: string,
  body?: unknown,
): unknown {
  const m = method.toUpperCase();
  const p = path.replace(/^\/api\/v1/, "");

  // GET routes
  if (m === "GET") {
    if (p === "/employees") return DEMO_EMPLOYEES;
    if (p === "/calibration") return DEMO_CALIBRATION;
    if (p === "/models/status") return DEMO_MODEL_STATUS;
    if (p === "/run/progress") return DEMO_RUN_PROGRESS;
    if (p === "/history") return DEMO_HISTORY_EVENTS;
    if (p === "/audit/log") return DEMO_AUDIT_LOG;
    if (p === "/interventions/outcomes") return DEMO_INTERVENTION_OUTCOMES;

    // /employee/:name/briefing
    const briefingMatch = p.match(/^\/employee\/(.+)\/briefing$/);
    if (briefingMatch) {
      const name = decodeURIComponent(briefingMatch[1]!);
      return DEMO_BRIEFINGS[name] ?? { found: false, briefing: null, raw_card: null };
    }
  }

  // POST routes
  if (m === "POST") {
    if (p === "/score/custom") {
      const b = body as Record<string, number | string> | undefined;
      const tasks = Number(b?.tasks_completed ?? 25);
      const response = Number(b?.avg_response_time ?? 4);
      const afterHours = Number(b?.after_hours_logins ?? 2);
      const hours = Number(b?.weekly_hours ?? 40);

      let raw = 1;
      if (tasks < 15) raw += 3;
      else if (tasks < 20) raw += 1;
      if (response > 5) raw += 3;
      else if (response > 2.5) raw += 2;
      if (afterHours > 6) raw += 2;
      else if (afterHours > 2) raw += 1;
      if (hours < 35) raw += 2;
      else if (hours > 50) raw += 1;
      const score = Math.max(1, Math.min(10, raw));

      let cls = "Healthy";
      if (score >= 9) cls = "Silent Exit";
      else if (score >= 7) cls = "At Risk";
      else if (score >= 4) cls = "Watch";

      return {
        risk_data: {
          score,
          classification: cls,
          confidence: score >= 7 ? "high" : "moderate",
        },
        briefing: `Demo simulation: A score of ${score}/10 (${cls}) based on the provided metrics. This is a scratch calculation — nothing is stored.`,
        signals: score >= 4
          ? [
              {
                signal_name: "Simulated Divergence",
                signal: null,
                severity: score >= 7 ? "high" : "medium",
                weeks_detected: [Number(b?.week_number ?? 4)],
                details: `Simulated metrics produced a ${cls} classification.`,
              },
            ]
          : [],
      };
    }

    if (p === "/run") return { status: "completed", message: "Demo mode: pipeline simulation complete." };
    if (p === "/ingest/raw") return { ingested: 1, errors: [] };
    if (p === "/ingest/db") return { status: "ok", message: "Demo: database sync simulated." };
    if (p === "/ingest/s3") return { status: "ok", message: "Demo: S3 sync simulated." };
    if (p === "/ingest/natural-language") return { status: "ok", message: "Demo: NLP extraction simulated." };
    if (p === "/feedback") return { status: "accepted" };
    if (p === "/interventions") return { status: "recorded" };
    if (p === "/settings") return { status: "ok" };
    if (p === "/reset") return { status: "ok" };
    if (p === "/mock-data") return { status: "ok", message: "Demo: mock data already loaded." };
    if (p === "/history/clear") return { status: "ok" };
  }

  // Fallback for unknown routes
  return { status: "ok", message: "Demo mode: no-op." };
}
