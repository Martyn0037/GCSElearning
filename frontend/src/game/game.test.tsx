// frontend/src/game/game.test.tsx
/**
 * Covers:
 * - home: Continue goes to reviews / a topic / today's challenge, or explains
 *   there's nothing yet; level, XP to next level, streak, freeze, weekly XP;
 *   daily card (not started, in progress, done); badges link; dashboard error
 *   leaves the subjects list working; refetched every time home opens
 * - continuePath for every kind (topic without IDs → none)
 * - results: XP pop, streak, level up, new badge, freeze note, challenge
 *   progress, bonus and "See results"
 * - daily challenge: start → question → answer → summary; start errors shown
 * - boss battle: intro, start errors, timed question with no hints, answer
 *   moves on, ending early shows results with the labelled estimate, personal
 *   best, unanswered questions and solutions; time running out ends it
 * - describeEstimate: band, single grade, below lowest, standing only
 * - topic list: ring and boss button (locked with skills needed / unlocked
 *   with best score); progress page ring
 * - badges page: earned with date, not yet earned
 * - sounds: off by default, toggled and remembered, cue never throws, plays
 *   through Web Audio when on
 */
import { act, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type {
  AnswerResultOut,
  ChallengeOut,
  DashboardOut,
  PracticeItemOut,
  RewardsOut,
  TopicOut,
} from "../api/generated/model";
import { installFakeApi, json, apiError, STUDENT, type Handler } from "../test/fakeApi";
import { NO_STANDING } from "../test/fixtures";
import { renderApp } from "../test/renderApp";
import { TopicList } from "../subjects/TopicList";
import { MemoryRouter } from "react-router";
import { continuePath } from "./continuePath";
import { describeEstimate } from "./estimate";
import { playCue, setSoundsOn, soundsOn } from "./sound";

const ENROLMENT = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa";
const TOPIC = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb";
const CHALLENGE = "cccccccc-cccc-4ccc-8ccc-cccccccccccc";
const ITEM = "dddddddd-dddd-4ddd-8ddd-dddddddddddd";
const ITEM2 = "eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee";

const DASHBOARD: DashboardOut = {
  level: { level: 3, totalXp: 350, xpIntoLevel: 50, xpForLevel: 300 },
  streak: { currentDays: 4, longestDays: 6, activeToday: false, freezeAvailable: true },
  xpThisWeek: 120,
  xpLastWeek: 90,
  daily: { challengeId: null, status: "not_started", answered: 0, total: 0 },
  reviewsDue: 2,
  continueTo: { kind: "review", label: "Review 2 mistakes" },
  badgesEarned: 1,
  badgesTotal: 10,
  recentBadges: [],
};

const ITEM_OUT: PracticeItemOut = {
  id: ITEM,
  questionType: "multiple_choice",
  commandWord: "Write down",
  stem: "Write down the highest common factor of $12$ and $18$.",
  options: [
    { label: "A", text: "2" },
    { label: "B", text: "3" },
    { label: "C", text: "6" },
    { label: "D", text: "36" },
  ],
  unit: null,
  marks: 1,
  difficulty: 3,
  objectiveRef: "N4",
  hints: [],
  hintsRemaining: 4,
  review: false,
  keypad: false,
  symbolKeys: [],
};

const REWARDS: RewardsOut = {
  xpGained: 30,
  bonusXp: 0,
  totalXp: 380,
  level: 3,
  levelUp: false,
  xpIntoLevel: 80,
  xpForLevel: 300,
  streakDays: 5,
  streakExtended: true,
  usedFreeze: false,
  newBadges: [],
};

function result(overrides: Partial<AnswerResultOut> = {}): AnswerResultOut {
  return {
    itemId: ITEM,
    correct: true,
    assisted: false,
    correctAnswer: "C: 6",
    workedSolution: "Common factors are 1, 2, 3, 6.",
    levelBefore: 3,
    levelAfter: 3,
    mistakeId: null,
    review: false,
    mistakeResolved: false,
    rewards: REWARDS,
    challenge: null,
    ...overrides,
  };
}

const BOSS: ChallengeOut = {
  id: CHALLENGE,
  kind: "boss",
  status: "active",
  londonDate: "2026-11-15",
  total: 2,
  answered: 0,
  enrolmentId: ENROLMENT,
  topicId: TOPIC,
  topicTitle: "Number",
  deadlineAt: "2026-11-15T10:05:00Z",
  secondsLeft: 300,
  score: null,
  maxScore: null,
  percent: null,
  bonusXp: null,
  grade: null,
  previousBest: null,
  personalBest: false,
  results: [],
};

const BOSS_DONE: ChallengeOut = {
  ...BOSS,
  status: "completed",
  answered: 1,
  secondsLeft: null,
  score: 1,
  maxScore: 2,
  percent: 50,
  bonusXp: 60,
  grade: { percent: 50, standing: "developing", bandLow: 4, bandHigh: 5, belowLowestGrade: null },
  previousBest: 25,
  personalBest: true,
  results: [
    {
      position: 1,
      stem: "Work out $2^{3}$.",
      marks: 1,
      marksEarned: 1,
      answered: true,
      correct: true,
      yourAnswer: "8",
      correctAnswer: "8",
      workedSolution: "2 × 2 × 2 = 8",
    },
    {
      position: 2,
      stem: "Work out $3^{2}$.",
      marks: 1,
      marksEarned: 0,
      answered: false,
      correct: null,
      yourAnswer: null,
      correctAnswer: "9",
      workedSolution: "3 × 3 = 9",
    },
  ],
};

function api(routes: Record<string, Handler | Handler[]>) {
  return installFakeApi({
    "GET /api/v1/users/me": () => json(STUDENT),
    "GET /api/v1/me/subjects": () => json({ setupCompleted: true, subjects: [] }),
    ...routes,
  });
}

beforeEach(() => {
  window.localStorage.clear();
  setSoundsOn(false);
  window.localStorage.clear();
});

afterEach(() => {
  vi.useRealTimers();
});

describe("home dashboard", () => {
  it("should continue to reviews and show level, streak, XP and badges", async () => {
    // Arrange
    api({ "GET /api/v1/me/dashboard": () => json(DASHBOARD) });

    // Act
    renderApp("/");

    // Assert
    expect(
      await screen.findByRole("link", { name: /Continue\s*Review 2 mistakes/ }),
    ).toHaveAttribute("href", "/review");
    expect(screen.getByText("250 XP to level 4")).toBeInTheDocument();
    expect(screen.getByRole("progressbar", { name: "XP to next level" })).toHaveAttribute(
      "aria-valuenow",
      "50",
    );
    expect(screen.getByText(/4 days/)).toBeInTheDocument();
    expect(
      screen.getByText(/Answer one question to keep it going · freeze ready/),
    ).toBeInTheDocument();
    expect(screen.getByText("This week: 120 XP · last week: 90 XP")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Daily challenge/ })).toHaveAttribute("href", "/daily");
    expect(screen.getByRole("link", { name: "Badges (1 of 10)" })).toHaveAttribute(
      "href",
      "/badges",
    );
  });

  it("should continue today's challenge and show its progress", async () => {
    api({
      "GET /api/v1/me/dashboard": () =>
        json({
          ...DASHBOARD,
          streak: {
            ...DASHBOARD.streak,
            currentDays: 1,
            activeToday: true,
            freezeAvailable: false,
          },
          level: { level: 99, totalXp: 999999, xpIntoLevel: 10, xpForLevel: 0 },
          daily: { challengeId: CHALLENGE, status: "active", answered: 2, total: 5 },
          continueTo: { kind: "daily", challengeId: CHALLENGE, label: "Carry on" },
        }),
    });
    renderApp("/");

    expect(await screen.findByRole("link", { name: /Continue\s*Carry on/ })).toHaveAttribute(
      "href",
      "/daily",
    );
    expect(screen.getByText("2 of 5 done")).toBeInTheDocument();
    expect(screen.getByText("Top level!")).toBeInTheDocument();
    expect(screen.getByText(/1 day/)).toBeInTheDocument();
    expect(screen.getByText("Done for today")).toBeInTheDocument();
  });

  it("should say when today's challenge is done and when there's nothing to do", async () => {
    api({
      "GET /api/v1/me/dashboard": () =>
        json({
          ...DASHBOARD,
          daily: { challengeId: CHALLENGE, status: "completed", answered: 5, total: 5 },
          continueTo: { kind: "none", label: "Nothing to practise yet" },
        }),
    });
    renderApp("/");

    expect(await screen.findByText(/Today's challenge done/)).toBeInTheDocument();
    expect(screen.getByText(/Nothing to practise yet\. Ask for a topic/)).toBeInTheDocument();
  });

  it("should keep the subjects list when the dashboard fails", async () => {
    api({ "GET /api/v1/me/dashboard": () => apiError(500, "INTERNAL") });
    renderApp("/");

    expect(await screen.findByRole("heading", { name: "Your subjects" })).toBeInTheDocument();
    expect(screen.queryByText(/Continue/)).not.toBeInTheDocument();
  });

  it("should refetch the dashboard each time home is opened", async () => {
    // Arrange: the challenge finishes between visits
    const fetchMock = api({
      "GET /api/v1/me/dashboard": [
        () => json(DASHBOARD),
        () =>
          json({
            ...DASHBOARD,
            daily: { challengeId: CHALLENGE, status: "completed", answered: 5, total: 5 },
          }),
      ],
      "GET /api/v1/me/badges": () => json([]),
    });
    const { router } = renderApp("/");
    await screen.findByRole("link", { name: /Daily challenge/ });

    // Act
    await act(() => router.navigate("/badges"));
    await act(() => router.navigate("/"));

    // Assert
    expect(await screen.findByText(/Today's challenge done/)).toBeInTheDocument();
    const calls = fetchMock.mock.calls.filter(([url]) => url === "/api/v1/me/dashboard");
    expect(calls).toHaveLength(2);
  });

  it("should map every Continue kind to a path", () => {
    expect(continuePath({ kind: "daily", label: "" })).toBe("/daily");
    expect(continuePath({ kind: "review", label: "" })).toBe("/review");
    expect(continuePath({ kind: "topic", enrolmentId: ENROLMENT, topicId: TOPIC, label: "" })).toBe(
      `/practice/${ENROLMENT}/${TOPIC}`,
    );
    expect(continuePath({ kind: "topic", label: "" })).toBeNull();
    expect(continuePath({ kind: "none", label: "" })).toBeNull();
  });
});

describe("daily challenge", () => {
  it("should run the questions, show rewards and finish with a summary", async () => {
    // Arrange
    api({
      "POST /api/v1/practice/challenges/daily": () =>
        json({ ...BOSS, kind: "daily", topicTitle: null, secondsLeft: null, deadlineAt: null }),
      [`POST /api/v1/practice/challenges/${CHALLENGE}/next`]: [
        () => json(ITEM_OUT),
        () => apiError(409, "CHALLENGE_FINISHED"),
      ],
      [`POST /api/v1/practice/items/${ITEM}/answer`]: () =>
        json(
          result({
            rewards: {
              ...REWARDS,
              bonusXp: 50,
              levelUp: true,
              level: 4,
              usedFreeze: true,
              newBadges: [
                {
                  code: "daily_7",
                  name: "Seven challenges",
                  description: "Complete 7.",
                  earnedAt: null,
                },
              ],
            },
            challenge: {
              challengeId: CHALLENGE,
              kind: "daily",
              answered: 5,
              total: 5,
              completed: true,
            },
          }),
        ),
      [`GET /api/v1/practice/challenges/${CHALLENGE}`]: () =>
        json({ ...BOSS_DONE, kind: "daily", score: 4, maxScore: 5, bonusXp: 50 }),
    });
    renderApp("/daily");
    const user = userEvent.setup();

    // Act
    await user.click(await screen.findByRole("radio", { name: /C\s*6/ }));
    await user.click(screen.getByRole("button", { name: "Check answer" }));

    // Assert: rewards
    expect(await screen.findByText("+80 XP")).toBeInTheDocument();
    expect(screen.getByText(/5-day streak/)).toBeInTheDocument();
    expect(screen.getByText("Challenge complete: +50 bonus XP")).toBeInTheDocument();
    expect(screen.getByText("Level 4 reached!")).toBeInTheDocument();
    expect(screen.getByText("New badge: Seven challenges")).toBeInTheDocument();
    expect(screen.getByText(/streak freeze covered/)).toBeInTheDocument();

    // Act / Assert: summary
    await user.click(screen.getByRole("button", { name: "See results" }));
    expect(await screen.findByText("Daily challenge done!")).toBeInTheDocument();
    expect(screen.getByText("4 of 5 right · +50 bonus XP")).toBeInTheDocument();
  });

  it("should show progress through the challenge after each answer", async () => {
    api({
      "POST /api/v1/practice/challenges/daily": () => json({ ...BOSS, kind: "daily" }),
      [`POST /api/v1/practice/challenges/${CHALLENGE}/next`]: () => json(ITEM_OUT),
      [`POST /api/v1/practice/items/${ITEM}/answer`]: () =>
        json(
          result({
            correct: false,
            rewards: { ...REWARDS, xpGained: 0, streakExtended: false },
            challenge: {
              challengeId: CHALLENGE,
              kind: "daily",
              answered: 2,
              total: 5,
              completed: false,
            },
          }),
        ),
    });
    renderApp("/daily");
    const user = userEvent.setup();
    await user.click(await screen.findByRole("radio", { name: /A\s*2/ }));
    await user.click(screen.getByRole("button", { name: "Check answer" }));

    expect(await screen.findByText("2 of 5 done")).toBeInTheDocument();
    expect(screen.queryByText(/XP/)).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Next question" })).toBeInTheDocument();
  });

  it.each([
    ["NOTHING_TO_PRACTISE", /a topic needs to be unlocked first/],
    ["QUESTIONS_PREPARING", /preparing today's challenge/],
  ])("should explain %s", async (code, message) => {
    api({ "POST /api/v1/practice/challenges/daily": () => apiError(409, code) });
    renderApp("/daily");
    expect(await screen.findByRole("alert")).toHaveTextContent(message);
  });
});

describe("boss battle", () => {
  const path = `/boss/${ENROLMENT}/${TOPIC}`;
  const start = `POST /api/v1/practice/enrolments/${ENROLMENT}/topics/${TOPIC}/boss`;

  it("should run a timed, hintless battle and show labelled results", async () => {
    // Arrange
    let answered = 0;
    api({
      [start]: () => json(BOSS),
      [`GET /api/v1/practice/challenges/${CHALLENGE}`]: () => json({ ...BOSS, answered }),
      [`POST /api/v1/practice/challenges/${CHALLENGE}/next`]: () =>
        json(answered === 0 ? ITEM_OUT : { ...ITEM_OUT, id: ITEM2 }),
      [`POST /api/v1/practice/items/${ITEM}/answer`]: () => {
        answered = 1;
        return json(
          result({
            challenge: {
              challengeId: CHALLENGE,
              kind: "boss",
              answered: 1,
              total: 2,
              completed: false,
            },
          }),
        );
      },
      [`POST /api/v1/practice/challenges/${CHALLENGE}/finish`]: () => json(BOSS_DONE),
    });
    renderApp(path);
    const user = userEvent.setup();

    // Act: start
    expect(await screen.findByText(/No hints, and no marks until the end/)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Start the clock" }));

    // Assert: timed, no hints
    expect(await screen.findByText("Number: question 1 of 2")).toBeInTheDocument();
    expect(screen.getByLabelText("Time left 5:00")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "I'm stuck" })).not.toBeInTheDocument();

    // Act: answer, then end early
    await user.click(await screen.findByRole("radio", { name: /C\s*6/ }));
    await user.click(screen.getByRole("button", { name: "Check answer" }));
    expect(await screen.findByText("Number: question 2 of 2")).toBeInTheDocument();
    expect(screen.queryByText("✓ Correct!")).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "End the battle now" }));

    // Assert: results
    expect(await screen.findByText("1 / 2 marks (50%)")).toBeInTheDocument();
    expect(screen.getByText(/around grade 4–5 \(developing\)/)).toBeInTheDocument();
    expect(screen.getByText(/not a predicted grade/)).toBeInTheDocument();
    expect(screen.getByText("New personal best! (was 25%)")).toBeInTheDocument();
    expect(screen.getByText("+60 bonus XP")).toBeInTheDocument();
    expect(screen.getByText(/Question 2 · 0\/1 mark · not answered/)).toBeInTheDocument();
    expect(screen.getAllByText("Worked solution")).toHaveLength(2);
  });

  it("should show the best score when not beaten", async () => {
    api({
      [start]: () =>
        json({ ...BOSS_DONE, personalBest: false, previousBest: 80, bonusXp: 0, grade: null }),
    });
    renderApp(path);
    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: "Start the clock" }));

    expect(await screen.findByText("Your best on this topic: 80%")).toBeInTheDocument();
    expect(screen.queryByText(/bonus XP/)).not.toBeInTheDocument();
  });

  it("should end the battle when the clock reaches zero", async () => {
    const finish = vi.fn(() => json(BOSS_DONE));
    api({
      [start]: () => json({ ...BOSS, secondsLeft: 1 }),
      [`GET /api/v1/practice/challenges/${CHALLENGE}`]: () => json({ ...BOSS, secondsLeft: 1 }),
      [`POST /api/v1/practice/challenges/${CHALLENGE}/next`]: () => json(ITEM_OUT),
      [`POST /api/v1/practice/challenges/${CHALLENGE}/finish`]: finish,
    });
    renderApp(path);
    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: "Start the clock" }));

    expect(await screen.findByText("1 / 2 marks (50%)", {}, { timeout: 4000 })).toBeInTheDocument();
    expect(finish).toHaveBeenCalled();
  });

  it("should show results when the server says time is up", async () => {
    let over = false;
    api({
      [start]: () => json(BOSS),
      [`GET /api/v1/practice/challenges/${CHALLENGE}`]: () => json(over ? BOSS_DONE : BOSS),
      [`POST /api/v1/practice/challenges/${CHALLENGE}/next`]: () => {
        over = true;
        return apiError(409, "TIME_UP");
      },
    });
    renderApp(path);
    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: "Start the clock" }));

    expect(await screen.findByText("1 / 2 marks (50%)")).toBeInTheDocument();
  });

  it.each([
    ["BOSS_LOCKED", /Practise more skills/],
    ["QUESTIONS_PREPARING", /preparing this boss battle/],
  ])("should explain %s", async (code, message) => {
    api({ [start]: () => apiError(409, code) });
    renderApp(path);
    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: "Start the clock" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(message);
  });

  it.each([
    [{ bandLow: 5, bandHigh: 6, standing: "secure" }, "around grade 5–6 (secure)"],
    [{ bandLow: 5, bandHigh: 5, standing: "developing" }, "around grade 5 (developing)"],
    [{ belowLowestGrade: 4, standing: "not_yet" }, "below grade 4 for now (not yet secure)"],
    [{ standing: "developing" }, "developing"],
  ] as const)("should describe the estimate %#", (grade, text) => {
    expect(
      describeEstimate({
        percent: 50,
        bandLow: null,
        bandHigh: null,
        belowLowestGrade: null,
        ...grade,
      }),
    ).toBe(text);
  });
});

describe("rings and boss buttons", () => {
  const topic: TopicOut = {
    id: TOPIC,
    ref: "1",
    title: "Number",
    taughtAtSchool: true,
    unlocked: true,
    subtopics: [],
    standing: { ...NO_STANDING, skillsToUnlockBoss: 3 },
  };

  it("should show the ring and how many skills unlock the boss", () => {
    render(
      <MemoryRouter>
        <TopicList topics={[topic]} enrolmentId={ENROLMENT} />
      </MemoryRouter>,
    );
    expect(screen.getByText("No ring yet")).toBeInTheDocument();
    expect(screen.getByText(/practise 3 more skills to unlock/)).toBeInTheDocument();
  });

  it("should link to an unlocked boss battle with the best score", () => {
    render(
      <MemoryRouter>
        <TopicList
          topics={[
            {
              ...topic,
              standing: {
                ring: "gold",
                ringProgress: 1,
                bossUnlocked: true,
                skillsToUnlockBoss: 0,
                bossBest: 65,
              },
            },
          ]}
          enrolmentId={ENROLMENT}
        />
      </MemoryRouter>,
    );
    expect(screen.getByText("Gold")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Boss battle/ })).toHaveAttribute(
      "href",
      `/boss/${ENROLMENT}/${TOPIC}`,
    );
    expect(screen.getByText("(best 65%)")).toBeInTheDocument();
  });

  it("should say one skill in the singular", () => {
    render(
      <MemoryRouter>
        <TopicList
          topics={[{ ...topic, standing: { ...NO_STANDING, skillsToUnlockBoss: 1 } }]}
          enrolmentId={ENROLMENT}
        />
      </MemoryRouter>,
    );
    expect(screen.getByText(/practise 1 more skill to unlock/)).toBeInTheDocument();
  });
});

describe("badges page", () => {
  it("should list earned and unearned badges", async () => {
    api({
      "GET /api/v1/me/badges": () =>
        json([
          {
            code: "streak_5",
            name: "5-day streak",
            description: "Practise on 5 days in a row.",
            earnedAt: "2026-11-14T10:00:00Z",
          },
          {
            code: "century",
            name: "Century",
            description: "Answer 100 questions.",
            earnedAt: null,
          },
        ]),
    });
    renderApp("/badges");

    expect(await screen.findByText("Earned 14 Nov")).toBeInTheDocument();
    expect(screen.getByText("Not yet")).toBeInTheDocument();
    expect(screen.getByText("Century")).toBeInTheDocument();
  });

  it("should say when badges can't load", async () => {
    api({ "GET /api/v1/me/badges": () => apiError(500, "INTERNAL") });
    renderApp("/badges");
    expect(await screen.findByRole("alert")).toHaveTextContent(/Couldn't load your badges/);
  });
});

describe("sounds", () => {
  it("should be off by default and remembered when turned on", async () => {
    api({ "GET /api/v1/me/dashboard": () => json(DASHBOARD) });
    renderApp("/");
    const user = userEvent.setup();

    const toggle = await screen.findByRole("checkbox", { name: "Sounds" });
    expect(toggle).not.toBeChecked();
    await user.click(toggle);

    expect(toggle).toBeChecked();
    expect(window.localStorage.getItem("gcse-coach:sounds")).toBe("on");
    expect(soundsOn()).toBe(true);
  });

  it("should play through Web Audio when on, and never throw", () => {
    // Arrange
    const start = vi.fn();
    const node = () => ({
      connect: vi.fn().mockReturnThis(),
      start,
      stop: vi.fn(),
      frequency: { value: 0 },
      gain: { setValueAtTime: vi.fn(), exponentialRampToValueAtTime: vi.fn() },
    });
    class FakeAudio {
      currentTime = 0;
      destination = {};
      createOscillator = node;
      createGain = node;
      close = vi.fn(() => Promise.resolve());
    }
    vi.stubGlobal("AudioContext", FakeAudio);

    // Act
    playCue("correct"); // off: nothing
    setSoundsOn(true);
    act(() => {
      playCue("levelUp");
    });

    // Assert
    expect(start).toHaveBeenCalledTimes(4);
    vi.stubGlobal("AudioContext", undefined);
    expect(() => {
      playCue("badge");
    }).not.toThrow();
    vi.stubGlobal("AudioContext", () => {
      throw new Error("blocked");
    });
    expect(() => {
      playCue("badge");
    }).not.toThrow();
    vi.unstubAllGlobals();
  });
});
