import { faker } from '@faker-js/faker';
import type { EmployeeSummary, BriefingView, Attribution, EmployeeWeek } from '../api/types';

/** Generate a random employee summary */
export function generateEmployee(): EmployeeSummary {
  const name = `${faker.person.firstName()} ${faker.person.lastName()}`;
  const score = faker.number.int({ min: 1, max: 10 });
  const classifications = ['Healthy', 'Watch', 'At Risk', 'Silent Exit'] as const;
  const classification: "Healthy" | "Watch" | "At Risk" | "Silent Exit" = faker.helpers.arrayElement(classifications);
  const confidenceLevels = ['high', 'moderate', 'low', 'none'];
  const confidence = faker.helpers.arrayElement(confidenceLevels) as any;
  const scoreRange: [number, number] = [Math.max(1, score - 2), Math.min(10, score + 2)];
  const attributions: Attribution[] = [];
  const history: EmployeeWeek[] = [];
  // generate simple history for last 6 weeks
  for (let w = 5; w <= 6; w++) {
    history.push({ week: w, score, classification });
  }
  return {
    name,
    score,
    classification,
    rationale: faker.lorem.sentence(),
    latest_week: 6,
    signals: [],
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
    latest_week: 6,
    signals: [],
    confidence: 'high' as any,
    score_range: [1, 3],
    attributions: [
      {
        metric: 'completed_tasks',
        contribution: 0.1,
        effect_size: 0.1,
        direction: 'above',
        weeks: [6],
      },
    ],
    model_version: 'demo-model',
    degraded: false,
    history: [
      { week: 5, score: 2, classification: 'Healthy' },
      { week: 6, score: 2, classification: 'Healthy' },
    ],
  };
  const priya: EmployeeSummary = {
    name: 'Priya',
    score: 7,
    classification: 'At Risk',
    rationale: 'Declining task completion across recent weeks.',
    latest_week: 6,
    signals: [
      {
        signal_name: 'Declining Task Completion',
        signal: null,
        severity: 'high',
        weeks_detected: [5, 6],
        details: null,
      },
    ],
    confidence: 'low' as any,
    score_range: [4, 10],
    attributions: [
      {
        metric: 'completed_tasks',
        contribution: 0.7,
        effect_size: 0.35,
        direction: 'below',
        weeks: [5, 6],
      },
    ],
    model_version: 'demo-model',
    degraded: true,
    history: [
      { week: 5, score: 6, classification: 'At Risk' },
      { week: 6, score: 7, classification: 'At Risk' },
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
