// frontend/src/api/types.ts
//
// Hand-written for now. `npm run generate:api` replaces these from the backend
// OpenAPI schema (openapi-typescript is already installed), which is the §4
// requirement: "a backend schema change that breaks the frontend must fail tsc
// in CI". That wiring lands with the remaining page migrations -- see
// PROGRESS.md. Until then these mirror the response shapes in
// src/api/routers/evolution.py and are the single place they are described.

export type Confidence = "none" | "low" | "moderate" | "high";

export type Classification = "Healthy" | "Watch" | "At Risk" | "Silent Exit";

export interface Attribution {
  metric: string;
  contribution: number;
  effect_size: number;
  direction: string;
  weeks: number[];
}

export interface CalibrationReport {
  total: number;
  accurate: number;
  not_accurate: number;
  harmful: number;
  elevated_precision: number | null;
  harm_rate: number;
  system_fault_rate: number | null;
}

export interface CalibrationView {
  active_model_version: string;
  overall: CalibrationReport;
  recent: CalibrationReport;
  drifting: boolean;
  review_required: boolean;
  message: string;
}

export interface InterventionAggregate {
  intervention: string;
  sample_size: number;
  median_excess_recovery: number | null;
  improved: number;
  declined: number;
  no_change: number;
  reportable: boolean;
  note: string;
}

export interface InterventionOutcomes {
  association_only: true;
  caveat: string;
  by_type: InterventionAggregate[];
  measured_outcomes: number;
  examples: Array<{
    subject_id: string;
    week: number;
    intervention: string;
    metric: string;
    excess_recovery: number;
    plain_english: string;
  }>;
}

export type FeedbackVerdict = "accurate" | "not_accurate" | "harmful";

export interface FeedbackInput {
  employee_name: string;
  week: number;
  verdict: FeedbackVerdict;
  reason?: string;
}

export interface InterventionInput {
  employee_name: string;
  week: number;
  intervention: string;
}
