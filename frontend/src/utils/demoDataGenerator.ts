import { faker } from '@faker-js/faker';
import type { EmployeeSummary, BriefingView, Attribution, EmployeeWeek } from '../api/types';

/** Generate a random employee summary */
export function generateEmployee(): EmployeeSummary {
  const name = `${faker.person.firstName()} ${faker.person.lastName()}`;
  const score = faker.number.int({ min: 1, max: 10 });
  const classification: "Healthy" | "Watch" | "At Risk" | "Silent Exit" =
    score >= 9 ? 'Silent Exit' : score >= 7 ? 'At Risk' : score >= 4 ? 'Watch' : 'Healthy';
  const confidenceLevels = ['high', 'moderate', 'low'] as const;
  const confidence = faker.helpers.arrayElement(confidenceLevels);
  const scoreRange: [number, number] = [Math.max(1, score - 2), Math.min(10, score + 2)];

  // Generate diverse attributions across all metrics
  const possibleMetrics = [
    'completed_tasks',
    'avg_response_time',
    'weekly_hours',
    'after_hours_logins',
    'collaboration_score',
  ];
  const selectedMetrics = faker.helpers.arrayElements(possibleMetrics, { min: 2, max: 4 });

  const attributions: Attribution[] = selectedMetrics.map((metric) => ({
    metric,
    contribution: Number(faker.number.float({ min: 0.1, max: 0.8, fractionDigits: 2 })),
    effect_size: Number(faker.number.float({ min: 0.05, max: 0.45, fractionDigits: 2 })),
    direction: score >= 4 ? 'below' : 'above',
    weeks: [10, 11, 12],
  }));

  // Generate full 12-week trajectory (spanning Q1 through Q4)
  const history: EmployeeWeek[] = [];
  let currentScore = Math.max(1, score - 2);
  for (let w = 1; w <= 12; w++) {
    if (w >= 9) {
      currentScore = score;
    } else if (w >= 5) {
      currentScore = Math.max(1, Math.min(10, currentScore + faker.number.int({ min: -1, max: 1 })));
    }
    const weekClass: "Healthy" | "Watch" | "At Risk" | "Silent Exit" =
      currentScore >= 9 ? 'Silent Exit' : currentScore >= 7 ? 'At Risk' : currentScore >= 4 ? 'Watch' : 'Healthy';
    history.push({ week: w, score: currentScore, classification: weekClass });
  }

  return {
    name,
    score,
    classification,
    rationale: faker.lorem.sentence(),
    latest_week: 12,
    signals: score >= 4 ? [
      {
        signal_name: score >= 7 ? 'Telemetry Divergence' : 'Early Pacing Shift',
        signal: null,
        severity: score >= 7 ? 'high' : 'medium',
        weeks_detected: [10, 11, 12],
        details: `Variance detected in ${selectedMetrics.join(', ')}.`,
      },
    ] : [],
    confidence,
    score_range: scoreRange,
    attributions,
    model_version: 'demo-model',
    degraded: false,
    history,
  };
}

/** Generate an array of employees */
export function generateEmployees(count: number = 5): EmployeeSummary[] {
  // Ensure Ade and Priya are always present for tests
  const ade: EmployeeSummary = {
    name: 'Ade',
    score: 2,
    classification: 'Healthy',
    rationale: 'Steady performance across all metrics.',
    latest_week: 12,
    signals: [],
    confidence: 'high' as any,
    score_range: [1, 3],
    attributions: [
      {
        metric: 'completed_tasks',
        contribution: 0.15,
        effect_size: 0.10,
        direction: 'above',
        weeks: [10, 11, 12],
      },
    ],
    model_version: 'demo-model',
    degraded: false,
    history: Array.from({ length: 12 }, (_, i) => ({
      week: i + 1,
      score: 2,
      classification: 'Healthy' as const,
    })),
  };
  const priya: EmployeeSummary = {
    name: 'Priya',
    score: 7,
    classification: 'At Risk',
    rationale: 'Declining task completion and rising latency across recent weeks.',
    latest_week: 12,
    signals: [
      {
        signal_name: 'Declining Task Completion',
        signal: null,
        severity: 'high',
        weeks_detected: [10, 11, 12],
        details: 'Tasks dropped from 25 to 10 across weeks 10–12.',
      },
      {
        signal_name: 'Response Latency Spike',
        signal: null,
        severity: 'medium',
        weeks_detected: [11, 12],
        details: 'Average response time rose to 8.0h.',
      },
    ],
    confidence: 'low' as any,
    score_range: [4, 10],
    attributions: [
      {
        metric: 'completed_tasks',
        contribution: 0.65,
        effect_size: 0.35,
        direction: 'below',
        weeks: [10, 11, 12],
      },
      {
        metric: 'avg_response_time',
        contribution: 0.25,
        effect_size: 0.18,
        direction: 'below',
        weeks: [11, 12],
      },
      {
        metric: 'weekly_hours',
        contribution: 0.10,
        effect_size: 0.08,
        direction: 'below',
        weeks: [12],
      },
    ],
    model_version: 'demo-model',
    degraded: true,
    history: [
      { week: 1, score: 2, classification: 'Healthy' },
      { week: 2, score: 2, classification: 'Healthy' },
      { week: 3, score: 3, classification: 'Healthy' },
      { week: 4, score: 3, classification: 'Healthy' },
      { week: 5, score: 4, classification: 'Watch' },
      { week: 6, score: 4, classification: 'Watch' },
      { week: 7, score: 5, classification: 'Watch' },
      { week: 8, score: 5, classification: 'Watch' },
      { week: 9, score: 6, classification: 'At Risk' },
      { week: 10, score: 6, classification: 'At Risk' },
      { week: 11, score: 7, classification: 'At Risk' },
      { week: 12, score: 7, classification: 'At Risk' },
    ],
  };
  const base = [ade, priya];
  if (count <= 2) return base.slice(0, count);
  const extra = Array.from({ length: count - 2 }, () => generateEmployee());
  return [...base, ...extra];
}

/** Generate a briefing view */
export function generateBriefing(): BriefingView {
  return {
    found: true,
    briefing: faker.lorem.paragraph(),
    raw_card: faker.lorem.sentence(),
  };
}
