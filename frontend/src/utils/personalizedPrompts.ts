// frontend/src/utils/personalizedPrompts.ts
//
// Generates uniquely tailored, context-specific conversation starters and supportive
// prompts for managers based on an employee's exact behavioral signals, baseline deviations,
// and historical patterns.

import type { EmployeeSummary } from "../api/types";

export interface PersonalizedPromptSet {
  contextSummary: string;
  conversationStarters: string[];
  thingsToAvoid: string[];
  recommendedSupportSteps: Array<{ title: string; desc: string; icon: string }>;
}

export function getPersonalizedPrompts(employee: EmployeeSummary): PersonalizedPromptSet {
  const name = employee.name;
  const signals = employee.signals ?? [];
  const sigNames = signals.map((s) => (s.signal_name ?? s.signal ?? "").toLowerCase());
  const hasTaskDrop = sigNames.some((s) => s.includes("task") || s.includes("completion"));
  const hasResponseSpike = sigNames.some((s) => s.includes("response") || s.includes("time"));
  const hasLateHours = sigNames.some((s) => s.includes("workload") || s.includes("after-hours") || s.includes("after hours") || s.includes("elevation"));
  const hasReducedHours = sigNames.some((s) => s.includes("reduced") || s.includes("hours"));

  // 1. After-hours / Late Night Overwork Signature
  if (hasLateHours && hasTaskDrop) {
    return {
      contextSummary: `${name} has shown sustained evening / after-hours activity alongside a decline in completed deliverables — a classic signature of cognitive fatigue, blocked dependencies, or emerging burnout.`,
      conversationStarters: [
        `"Hey ${name}, I noticed your logged hours extending into the evenings recently. How are you feeling about your bandwidth and rest boundaries lately?"`,
        `"Are there tricky cross-team dependencies or blockers that are forcing you to work late into the night just to keep momentum?"`,
        `"Let's look at your current commitments together — which project can we descopify, pause, or reassign this week so you can wrap up at normal hours?"`,
        `"Is there anything on your plate where pairing with another engineer would take the pressure off?"`,
      ],
      thingsToAvoid: [
        `Do not question ${name}'s output volume or ask why tasks dropped despite longer hours.`,
        `Never mention performance reviews, PIPs, or formal attendance metrics.`,
      ],
      recommendedSupportSteps: [
        { icon: "🛡️", title: "Workload Rebalancing", desc: "Explicitly remove 1-2 non-critical deliverables from this sprint." },
        { icon: "🌙", title: "Boundary Reset", desc: "Agree on asynchronous no-evening communication rules." },
        { icon: "🤝", title: "Pairing Support", desc: "Assign a buddy to share complex architectural or operational tasks." },
      ],
    };
  }

  // 2. High Overwork / Extended Hours only
  if (hasLateHours) {
    return {
      contextSummary: `${name} is putting in extra hours and late-evening sessions beyond their typical baseline. While task delivery remains active, sustained overtime increases long-term burnout risk.`,
      conversationStarters: [
        `"Hi ${name}, I really appreciate your dedication, but I want to make sure you're not burning the candle at both ends. How is your energy holding up?"`,
        `"Are timezone handoffs or meeting clusters eating into your daylight focus time?"`,
        `"Can we establish clear 'pencils-down' hours for the team so you don't feel obligated to check messages late at night?"`,
      ],
      thingsToAvoid: [
        `Do not praise excessive overtime as the expected team norm.`,
        `Avoid adding ad-hoc requests or scheduling early morning meetings after late days.`,
      ],
      recommendedSupportSteps: [
        { icon: "☕", title: "Focus Days", desc: "Designate meeting-free focus blocks during daylight hours." },
        { icon: "🌴", title: "Comp-time / Rest", desc: "Encourage taking compensatory recharge time." },
      ],
    };
  }

  // 3. Response Time Spike
  if (hasResponseSpike && !hasTaskDrop) {
    return {
      contextSummary: `${name}'s communication response latency has increased compared to their week-1 baseline, while output remains steady — often signaling deep-focus mode or communication fatigue.`,
      conversationStarters: [
        `"Hey ${name}, how has the communication rhythm on Slack/email felt? Are notifications distracting you from uninterrupted problem solving?"`,
        `"Would it help if we set explicit async expectations so you can mute notifications during deep work sessions?"`,
        `"Are there recurring status meetings we can convert to written summaries to save you context switching?"`,
      ],
      thingsToAvoid: [
        `Do not demand immediate response times or mandate constant chat availability.`,
        `Avoid interpreting delayed messages as disengagement.`,
      ],
      recommendedSupportSteps: [
        { icon: "🔕", title: "Async Agreement", desc: "Clarify that 24-hour response windows for non-urgent messages are fully supported." },
        { icon: "🎯", title: "Context Minimization", desc: "Consolidate communication channels for active projects." },
      ],
    };
  }

  // 4. Declining Task Completion
  if (hasTaskDrop) {
    return {
      contextSummary: `${name}'s task delivery rate has decreased relative to their own normal pace. This is evaluated as a prompt to check for roadblocks, not a performance verdict.`,
      conversationStarters: [
        `"Hi ${name}, how are your current project milestones feeling? Have you run into unexpected technical hurdles or murky requirements?"`,
        `"Is there any part of the stack or tooling that is slowing you down or causing frustration?"`,
        `"What is the single biggest impediment in your day-to-day right now that I can help unblock or escalate?"`,
      ],
      thingsToAvoid: [
        `Never frame the discussion around velocity numbers or story point comparisons.`,
        `Avoid questioning commitment or work ethic.`,
      ],
      recommendedSupportSteps: [
        { icon: "🧱", title: "Unblock Impediments", desc: "Clarify ambiguous scope and resolve architectural blockers." },
        { icon: "👥", title: "Collaborative Sync", desc: "Schedule short, supportive pairing check-ins instead of formal status reports." },
      ],
    };
  }

  // 5. Reduced Hours
  if (hasReducedHours) {
    return {
      contextSummary: `${name}'s active system hours have dipped below their baseline. Check in with warmth to see if life circumstances or schedule adjustments need accommodation.`,
      conversationStarters: [
        `"Hey ${name}, I wanted to check in on how your schedule and general flexibility are feeling this month."`,
        `"Do you have everything you need in terms of flexibility or asynchronous workflows right now?"`,
        `"Let me know if we need to adjust sprint commitments to better match your current schedule."`,
      ],
      thingsToAvoid: [
        `Do not inquire invasively into personal life or health matters.`,
        `Avoid implying time tracking or surveillance.`,
      ],
      recommendedSupportSteps: [
        { icon: "🕒", title: "Flexible Scheduling", desc: "Offer core-hours flexibility with async handoffs." },
      ],
    };
  }

  // 6. Healthy / Balanced Baseline
  return {
    contextSummary: `${name} is operating in a steady, sustainable cadence consistent with their personal baseline.`,
    conversationStarters: [
      `"Hi ${name}, your pace and rhythm look really steady. What aspects of your current projects are bringing you the most energy right now?"`,
      `"Looking ahead to the next quarter, are there specific skills, technologies, or leadership opportunities you'd like to explore?"`,
      `"Is there any friction or process debt in our team workflow that we should polish while things are smooth?"`,
      `"How are you feeling about your current work-life balance and project autonomy?"`,
    ],
    thingsToAvoid: [
      `Avoid overloading ${name} with extra backlog just because they are currently healthy.`,
      `Do not skip regular 1-on-1s when everything appears fine.`,
    ],
    recommendedSupportSteps: [
      { icon: "🌟", title: "Recognition & Growth", desc: "Discuss long-term learning goals and rewarding project ownership." },
      { icon: "🌿", title: "Sustain Rhythm", desc: "Protect current healthy workload limits against scope creep." },
    ],
  };
}
