#!/usr/bin/env node

/**
 * 持续运行的 ICS 课程考勤调度器。
 *
 * 启动时必须传入 ICS 文件路径：
 *   node --experimental-strip-types schedule.ts ./课程.ics
 *
 * 也可以指定日志时区：
 *   node --experimental-strip-types schedule.ts ./课程.ics --timezone Asia/Shanghai
 */

import { readFileSync, statSync } from "node:fs";
import { resolve } from "node:path";
import { spawn, type ChildProcess } from "node:child_process";
import { fileURLToPath } from "node:url";
import ical, {
  type EventInstance,
  type ParameterValue,
  type VEvent,
} from "node-ical";

const START_BEFORE_MS = 10 * 60 * 1000;
const STOP_AFTER_START_MS = 20 * 60 * 1000;
const POLL_INTERVAL_MS = 30 * 1000;
const HISTORY_MS = 2 * 60 * 60 * 1000;
const LOOK_AHEAD_MS = 90 * 24 * 60 * 60 * 1000;
const COMMAND = "xmu-rollcall";
export type CalendarEvent = {
  uid: string;
  summary: string;
  event: VEvent;
};

export type Occurrence = {
  key: string;
  uid: string;
  summary: string;
  startUtcMs: number;
  endUtcMs: number;
};

const MAX_OCCURRENCES_PER_EVENT = 10000;

function textValue(value: ParameterValue | undefined, fallback: string): string {
  if (typeof value === "string") return value;
  if (value && typeof value === "object" && "val" in value) {
    return String(value.val);
  }
  return fallback;
}

export function parseCalendar(text: string): CalendarEvent[] {
  const parsed = ical.sync.parseICS(text);
  const events: CalendarEvent[] = [];

  for (const component of Object.values(parsed)) {
    if (!component || component.type !== "VEVENT") continue;
    if (component.recurrenceid || !component.start || component.start.dateOnly) continue;

    events.push({
      uid: component.uid || `event:${component.start.getTime()}`,
      summary: textValue(component.summary, "未命名课程"),
      event: component,
    });
    console.log(`已解析课程事件: ${component.uid} (${component.start.toISOString()})`);
  }

  return events;
}

export function expandEvent(
  event: CalendarEvent,
  fromUtcMs: number,
  toUtcMs: number,
): Occurrence[] {
  const instances = ical.expandRecurringEvent(event.event, {
    from: new Date(fromUtcMs),
    to: new Date(toUtcMs),
    includeOverrides: true,
    excludeExdates: true,
    expandOngoing: false,
  });
  const occurrences: Occurrence[] = [];

  for (const instance of instances.slice(0, MAX_OCCURRENCES_PER_EVENT)) {
    if (instance.isFullDay) continue;
    const occurrence = toOccurrence(event, instance);
    if (occurrence) occurrences.push(occurrence);
  }

  return occurrences;
}

function toOccurrence(event: CalendarEvent, instance: EventInstance): Occurrence | undefined {
  const startUtcMs = instance.start.getTime();
  const endUtcMs = instance.end.getTime();
  if (!Number.isFinite(startUtcMs) || !Number.isFinite(endUtcMs)) return undefined;

  return {
    key: `${event.uid}:${startUtcMs}`,
    uid: event.uid,
    summary: textValue(instance.summary, event.summary),
    startUtcMs,
    endUtcMs: Math.max(startUtcMs, endUtcMs),
  };
}

type RunStatus = "pending" | "starting" | "running" | "failed" | "stopping" | "stopped";

type RunState = {
  status: RunStatus;
  child?: ChildProcess;
  childExited: boolean;
  startAttempts: number;
  retryAt?: number;
  occurrence?: Occurrence;
  stopAt?: number;
};

const isMain =
  process.argv[1] !== undefined &&
  resolve(process.argv[1]) === resolve(fileURLToPath(import.meta.url));
let icsPath = "";
let defaultTimeZone = "Asia/Shanghai";

function validateTimeZone(timeZone: string): void {
  try {
    new Intl.DateTimeFormat("zh-CN", { timeZone }).format();
  } catch {
    console.error(`无效时区: ${timeZone}`);
    process.exit(2);
  }
}

function log(message: string): void {
  const now = new Date().toLocaleString("zh-CN", {
    timeZone: defaultTimeZone,
    hour12: false,
  });
  console.log(`[${now}] ${message}`);
}


function displayTime(utcMs: number): string {
  return new Intl.DateTimeFormat("zh-CN", {
    timeZone: defaultTimeZone,
    dateStyle: "short",
    timeStyle: "medium",
    hour12: false,
  }).format(new Date(utcMs));
}

const START_RETRY_DELAYS_MS = [5_000, 15_000, 30_000] as const;
const MAX_START_ATTEMPTS = START_RETRY_DELAYS_MS.length;

function spawnQuiet(command: string, commandArgs: string[]): Promise<number | null> {
  return new Promise((resolvePromise) => {
    let child: ChildProcess;
    try {
      child = spawn(command, commandArgs, { stdio: "ignore", windowsHide: true });
    } catch {
      resolvePromise(null);
      return;
    }
    child.once("error", () => resolvePromise(null));
    child.once("exit", (code) => resolvePromise(code));
  });
}

async function terminateByPid(pid: number): Promise<boolean> {
  if (process.platform === "win32") {
    return (await spawnQuiet("taskkill", ["/PID", String(pid), "/T", "/F"])) === 0;
  }

  try {
    // Unix 下启动时使用独立进程组，连同命令启动的子进程一起结束。
    process.kill(-pid, "SIGTERM");
    return true;
  } catch {
    try {
      process.kill(pid, "SIGTERM");
      return true;
    } catch {
      // 进程可能已经自行退出。
      return false;
    }
  }
}
async function terminateByName(): Promise<boolean> {
  if (process.platform === "win32") {
    return (await spawnQuiet("taskkill", ["/IM", `${COMMAND}.exe`, "/T", "/F"])) === 0;
  }
  return (await spawnQuiet("pkill", ["-TERM", "-x", COMMAND])) === 0;
}

function isActive(state: RunState): boolean {
  return state.status === "starting" || state.status === "running";
}

function scheduleStartRetry(state: RunState, occurrence: Occurrence, message: string): void {
  state.status = "failed";
  if (state.startAttempts < MAX_START_ATTEMPTS) {
    const delay = START_RETRY_DELAYS_MS[state.startAttempts - 1] ?? START_RETRY_DELAYS_MS.at(-1)!;
    state.retryAt = Date.now() + delay;
    if (wakeTimer) clearTimeout(wakeTimer);
    wakeTimer = setTimeout(() => reconcile(), Math.max(250, delay));
    log(`${message}；将在 ${Math.ceil(delay / 1000)} 秒后重试（${occurrence.summary}）`);
  } else {
    state.retryAt = undefined;
    log(`${message}；已达到最大重试次数（${occurrence.summary}）`);
  }
}

function startRollcall(state: RunState, occurrence: Occurrence): void {
  if (state.status !== "pending" && state.status !== "failed") return;

  state.status = "starting";
  state.startAttempts += 1;
  state.retryAt = undefined;
  state.childExited = false;

  let child: ChildProcess;
  try {
    child = spawn(COMMAND, ["start"], {
      shell: true,
      detached: process.platform !== "win32",
      stdio: "ignore",
      windowsHide: true,
    });
  } catch (error) {
    scheduleStartRetry(
      state,
      occurrence,
      `启动失败: ${error instanceof Error ? error.message : String(error)}`,
    );
    return;
  }

  state.child = child;
  let failureHandled = false;
  const handleFailure = (message: string): void => {
    if (failureHandled || state.status === "stopping" || state.status === "stopped") return;
    failureHandled = true;
    state.childExited = true;
    scheduleStartRetry(state, occurrence, message);
  };

  child.once("spawn", () => {
    if (state.status !== "starting") return;
    state.status = "running";
    log(`已执行 xmu-rollcall start：${occurrence.summary}（${displayTime(occurrence.startUtcMs)}）`);
  });
  child.once("error", (error) => {
    handleFailure(`启动失败: ${error.message}`);
  });
  child.once("exit", (code, signal) => {
    state.childExited = true;
    if (state.status === "stopping" || state.status === "stopped") return;
    if (code !== 0 || signal !== null) {
      handleFailure(`xmu-rollcall start 已退出（退出码 ${code ?? "无"}，信号 ${signal ?? "无"}）`);
      return;
    }
    // stopRollcall 在课程结束时会按名称清理所有签到监控进程。
    if (state.status === "starting") state.status = "running";
    log(`xmu-rollcall start 命令已退出（${occurrence.summary}）`);
  });
}

async function stopRollcall(state: RunState, occurrence: Occurrence): Promise<void> {
  if (state.status === "stopped" || state.status === "failed" || state.status === "pending") {
    state.status = "stopped";
    return;
  }
  if (state.status === "stopping") return;

  state.status = "stopping";
  let terminated = false;
  if (state.child?.pid && !state.childExited) {
    terminated = await terminateByPid(state.child.pid);
  }
  // 课程结束时按名称清理，覆盖 start 命令已退出或用户手动启动的监控进程。
  terminated = (await terminateByName()) || terminated;
  if (!terminated) {
    log(`未找到可结束的 xmu-rollcall 进程：${occurrence.summary}`);
  }
  state.status = "stopped";
  log(`已结束 xmu-rollcall 任务：${occurrence.summary}`);
}


let loadedMtimeMs = -1;
let events: CalendarEvent[] = [];
const runStates = new Map<string, RunState>();
let wakeTimer: ReturnType<typeof setTimeout> | undefined;
let shuttingDown = false;

function loadScheduleIfChanged(): void {
  let mtimeMs: number;
  try {
    mtimeMs = statSync(icsPath).mtimeMs;
  } catch (error) {
    log(`无法读取 ICS 文件 ${icsPath}: ${error instanceof Error ? error.message : String(error)}`);
    return;
  }
  if (mtimeMs === loadedMtimeMs) return;

  try {
    events = parseCalendar(readFileSync(icsPath, "utf8"));
    loadedMtimeMs = mtimeMs;
    log(`已加载 ${events.length} 个课程事件：${icsPath}`);
  } catch (error) {
    log(`解析 ICS 文件失败: ${error instanceof Error ? error.message : String(error)}`);
  }
}

function reconcile(): void {
  if (shuttingDown) return;
  loadScheduleIfChanged();

  const now = Date.now();
  const occurrences = events.flatMap((event) =>
    expandEvent(event, now - HISTORY_MS, now + LOOK_AHEAD_MS),
  );
  const occurrenceMap = new Map(occurrences.map((occurrence) => [occurrence.key, occurrence]));
  let nextWakeAt = now + POLL_INTERVAL_MS;

  for (const occurrence of occurrences) {
    const state = runStates.get(occurrence.key) || {
      status: "pending" as const,
      childExited: false,
      startAttempts: 0,
    };
    runStates.set(occurrence.key, state);
    const launchAt = occurrence.startUtcMs - START_BEFORE_MS;
    const stopAt = occurrence.startUtcMs + STOP_AFTER_START_MS;
    state.occurrence = occurrence;
    state.stopAt = stopAt;

    const retryReady = state.retryAt === undefined || now >= state.retryAt;
    if (
      (state.status === "pending" || state.status === "failed") &&
      now >= launchAt &&
      now < stopAt &&
      retryReady
    ) {
      startRollcall(state, occurrence);
    }
    if (isActive(state) && now >= stopAt) {
      void stopRollcall(state, occurrence);
    }

    if (state.status === "pending" && launchAt > now) {
      nextWakeAt = Math.min(nextWakeAt, launchAt);
    }
    if (state.status === "failed" && state.retryAt !== undefined && state.retryAt > now) {
      nextWakeAt = Math.min(nextWakeAt, state.retryAt);
    }
    if (isActive(state) && stopAt > now) {
      nextWakeAt = Math.min(nextWakeAt, stopAt);
    }
  }

  // 清理已经完成很久的状态，避免脚本运行数月后 Map 无限增长。
  for (const [key, state] of runStates) {
    if (!occurrenceMap.has(key)) {
      // ICS 被修改后，已启动任务仍按原定停止时间结束。
      if (
        isActive(state) &&
        state.stopAt !== undefined &&
        state.occurrence &&
        now >= state.stopAt
      ) {
        void stopRollcall(state, state.occurrence);
      }
      if (
        state.status === "stopped" ||
        (!isActive(state) && state.stopAt !== undefined && now >= state.stopAt)
      ) {
        runStates.delete(key);
      }
    }
  }

  const delay = Math.max(250, Math.min(POLL_INTERVAL_MS, nextWakeAt - Date.now()));
  wakeTimer = setTimeout(reconcile, delay);
}
async function shutdown(signal: string): Promise<void> {
  if (shuttingDown) return;
  shuttingDown = true;
  if (wakeTimer) clearTimeout(wakeTimer);
  log(`收到 ${signal}，正在清理活动任务。`);

  const activeStates = [...runStates.values()].filter(
    (state): state is RunState & { occurrence: Occurrence } =>
      isActive(state) && state.occurrence !== undefined,
  );
  await Promise.allSettled(
    activeStates.map((state) => stopRollcall(state, state.occurrence)),
  );
  log(`收到 ${signal}，调度器退出。`);
  process.exit(0);
}

if (isMain) {
  const args = process.argv.slice(2);
  const positionalArgs: string[] = [];
  for (let index = 0; index < args.length; index += 1) {
    if (args[index] === "--timezone") {
      index += 1;
      continue;
    }
    if (!args[index].startsWith("--")) positionalArgs.push(args[index]);
  }

  if (args.includes("--help") || args.includes("-h")) {
    console.log(`用法: node --experimental-strip-types schedule.ts <ics 文件> [--timezone 时区]

示例:
  node --experimental-strip-types schedule.ts Cal-3-1.ics --timezone Asia/Shanghai

脚本会持续运行，在每节课开始前 10 分钟执行 “${COMMAND} start”，
并在课程开始后 20 分钟结束所有 xmu-rollcall 进程。`);
    process.exit(0);
  }

  if (positionalArgs.length !== 1) {
    console.error("必须且只能传入一个 ICS 文件路径。");
    console.error(
      "用法: node --experimental-strip-types schedule.ts <ics 文件> [--timezone 时区]",
    );
    process.exit(2);
  }

  icsPath = resolve(positionalArgs[0]!);
  const timezoneArgumentIndex = args.indexOf("--timezone");
  const configuredTimeZone =
    timezoneArgumentIndex >= 0 ? args[timezoneArgumentIndex + 1] : undefined;
  defaultTimeZone = configuredTimeZone || "Asia/Shanghai";
  validateTimeZone(defaultTimeZone);

  process.on("SIGINT", () => {
    void shutdown("SIGINT");
  });
  process.on("SIGTERM", () => {
    void shutdown("SIGTERM");
  });

  log(`开始运行，ICS: ${icsPath}，时区: ${defaultTimeZone}`);
  reconcile();
}
