import assert from "node:assert/strict";
import { chmod, mkdtemp, readFile, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { delimiter, join, resolve } from "node:path";
import { spawn, type ChildProcess } from "node:child_process";
import test from "node:test";

const repoRoot = resolve(".");

function formatUtcIcsDate(date: Date): string {
  return date.toISOString().replace(/[-:]/g, "").replace(/\.\d{3}Z$/, "Z");
}

async function waitForExit(child: ChildProcess): Promise<number | null> {
  if (child.exitCode !== null) return child.exitCode;
  return await new Promise((resolvePromise, reject) => {
    const timer = setTimeout(() => reject(new Error("Timed out waiting for child exit")), 10_000);
    child.once("error", (error) => {
      clearTimeout(timer);
      reject(error);
    });
    child.once("exit", (code) => {
      clearTimeout(timer);
      resolvePromise(code);
    });
  });
}

async function waitForOutput(
  output: string[],
  predicate: (value: string) => boolean,
): Promise<void> {
  const deadline = Date.now() + 15_000;
  while (Date.now() < deadline) {
    if (predicate(output.join(""))) return;
    await new Promise((resolvePromise) => setTimeout(resolvePromise, 100));
  }
  throw new Error(`Timed out waiting for scheduler output:\n${output.join("")}`);
}

async function waitForFile(path: string, predicate: (value: string) => boolean): Promise<string> {
  const deadline = Date.now() + 10_000;
  while (Date.now() < deadline) {
    try {
      const value = await readFile(path, "utf8");
      if (predicate(value)) return value;
    } catch {
      // The child has not written the marker yet.
    }
    await new Promise((resolvePromise) => setTimeout(resolvePromise, 100));
  }
  throw new Error(`Timed out waiting for ${path}`);
}

async function waitForProcessExit(pid: number): Promise<void> {
  const deadline = Date.now() + 10_000;
  while (Date.now() < deadline) {
    try {
      process.kill(pid, 0);
    } catch {
      return;
    }
    await new Promise((resolvePromise) => setTimeout(resolvePromise, 100));
  }
  throw new Error(`Process ${pid} is still alive`);
}

async function createFakeCommand(directory: string): Promise<{logPath: string; commandPath: string}> {
  const logPath = join(directory, "rollcall.log");
  const runnerPath = join(directory, "fake-rollcall.mjs");
  await writeFile(
    runnerPath,
    [
      'import { appendFileSync } from "node:fs";',
      'appendFileSync(process.env.ROLLCALL_LOG, `${process.pid} ${process.argv.slice(2).join(" ")}\\n`);',
      'if (process.env.ROLLCALL_FAIL === "1") process.exit(1);',
      "setInterval(() => {}, 1000);",
      "",
    ].join("\n"),
  );

  if (process.platform === "win32") {
    const commandPath = join(directory, "xmu-rollcall.cmd");
    await writeFile(
      commandPath,
      `@echo off\n"%ROLLCALL_NODE%" "%ROLLCALL_SCRIPT%" %*\n`,
    );
    return { logPath, commandPath };
  }

  const commandPath = join(directory, "xmu-rollcall");
  await writeFile(
    commandPath,
    `#!/bin/sh\nexec "$ROLLCALL_NODE" "$ROLLCALL_SCRIPT" "$@"\n`,
  );
  await chmod(commandPath, 0o755);
  return { logPath, commandPath };
}

test("terminates rollcall processes at stop time", async () => {
  const directory = await mkdtemp(join(tmpdir(), "schedule-process-"));
  const icsPath = join(directory, "schedule.ics");
  let scheduler: ChildProcess | undefined;

  try {
    const fake = await createFakeCommand(directory);
    const start = new Date(Date.now() - 19 * 60 * 1000 - 50 * 1000);
    const startValue = formatUtcIcsDate(start);
    const endValue = formatUtcIcsDate(new Date(start.getTime() + 60 * 60 * 1000));
    await writeFile(
      icsPath,
      `BEGIN:VCALENDAR\nVERSION:2.0\nBEGIN:VEVENT\nUID:stop@example.test\nSUMMARY:stop test\nDTSTART:${startValue}\nDTEND:${endValue}\nEND:VEVENT\nEND:VCALENDAR\n`,
    );

    const output: string[] = [];
    scheduler = spawn(
      process.execPath,
      ["--experimental-strip-types", resolve("schedule.ts"), icsPath, "--timezone", "UTC"],
      {
        cwd: repoRoot,
        env: {
          ...process.env,
          PATH: `${directory}${delimiter}${process.env.PATH ?? ""}`,
          ROLLCALL_LOG: fake.logPath,
          ROLLCALL_NODE: process.execPath,
          ROLLCALL_SCRIPT: join(directory, "fake-rollcall.mjs"),
        },
        stdio: ["ignore", "pipe", "pipe"],
        windowsHide: true,
      },
    );
    scheduler.stdout?.on("data", (chunk) => output.push(String(chunk)));
    scheduler.stderr?.on("data", (chunk) => output.push(String(chunk)));

    const log = await waitForFile(fake.logPath, (value) => value.includes(" start\n"));
    const rollcallPid = Number.parseInt(log.split(/\s+/u, 1)[0] ?? "", 10);
    assert.ok(Number.isInteger(rollcallPid) && rollcallPid > 0);

    await waitForOutput(output, (value) => value.includes("已结束 xmu-rollcall 任务"));
    await waitForProcessExit(rollcallPid);
  } finally {
    if (scheduler && scheduler.exitCode === null) {
      if (process.platform === "win32" && scheduler.pid) {
        const killer = spawn("taskkill", ["/PID", String(scheduler.pid), "/T", "/F"], {
          stdio: "ignore",
          windowsHide: true,
        });
        await waitForExit(killer).catch(() => undefined);
      } else {
        scheduler.kill("SIGKILL");
      }
      await waitForExit(scheduler).catch(() => undefined);
    }
    await rm(directory, { recursive: true, force: true });
  }
});
test("retries a failed rollcall start during the launch window", async () => {
  const directory = await mkdtemp(join(tmpdir(), "schedule-retry-"));
  const icsPath = join(directory, "schedule.ics");
  let scheduler: ChildProcess | undefined;

  try {
    const fake = await createFakeCommand(directory);
    const start = new Date(Date.now() + 2 * 60 * 1000);
    const startValue = formatUtcIcsDate(start);
    const endValue = formatUtcIcsDate(new Date(start.getTime() + 60 * 60 * 1000));
    await writeFile(
      icsPath,
      `BEGIN:VCALENDAR\nVERSION:2.0\nBEGIN:VEVENT\nUID:retry@example.test\nSUMMARY:retry test\nDTSTART:${startValue}\nDTEND:${endValue}\nEND:VEVENT\nEND:VCALENDAR\n`,
    );

    const output: string[] = [];
    scheduler = spawn(
      process.execPath,
      ["--experimental-strip-types", resolve("schedule.ts"), icsPath, "--timezone", "UTC"],
      {
        cwd: repoRoot,
        env: {
          ...process.env,
          PATH: `${directory}${delimiter}${process.env.PATH ?? ""}`,
          ROLLCALL_FAIL: "1",
          ROLLCALL_LOG: fake.logPath,
          ROLLCALL_NODE: process.execPath,
          ROLLCALL_SCRIPT: join(directory, "fake-rollcall.mjs"),
        },
        stdio: ["ignore", "pipe", "pipe"],
        windowsHide: true,
      },
    );
    scheduler.stdout?.on("data", (chunk) => output.push(String(chunk)));
    scheduler.stderr?.on("data", (chunk) => output.push(String(chunk)));

    await waitForOutput(
      output,
      (value) => (value.match(/将在/gu) ?? []).length >= 2,
    );
  } finally {
    if (scheduler && scheduler.exitCode === null) {
      if (process.platform === "win32" && scheduler.pid) {
        const killer = spawn("taskkill", ["/PID", String(scheduler.pid), "/T", "/F"], {
          stdio: "ignore",
          windowsHide: true,
        });
        await waitForExit(killer).catch(() => undefined);
      } else {
        scheduler.kill("SIGKILL");
      }
      await waitForExit(scheduler).catch(() => undefined);
    }
    await rm(directory, { recursive: true, force: true });
  }
});
