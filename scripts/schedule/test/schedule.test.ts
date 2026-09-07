import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

import { expandEvent, parseCalendar } from "../schedule.ts";

function expand(text: string, from: string, to: string) {
  const events = parseCalendar(text);
  return events.flatMap((event) =>
    expandEvent(event, Date.parse(from), Date.parse(to)),
  );
}

test("parses the bundled calendar and expands timezone-aware weekly events", () => {
  const events = parseCalendar(readFileSync("Cal-3-1.ics", "utf8"));
  const occurrences = events.flatMap((event) =>
    expandEvent(
      event,
      Date.parse("2026-09-07T00:00:00Z"),
      Date.parse("2026-09-30T23:59:59Z"),
    ),
  );

  assert.equal(events.length, 10);
  assert.equal(occurrences.length, 25);
  assert.deepEqual(
    occurrences.slice(0, 2).map((occurrence) => new Date(occurrence.startUtcMs).toISOString()),
    ["2026-09-08T02:10:00.000Z", "2026-09-15T02:10:00.000Z"],
  );
});

test("honors BYDAY and EXDATE recurrence rules", () => {
  const occurrences = expand(
    `BEGIN:VCALENDAR
VERSION:2.0
BEGIN:VEVENT
UID:byday@example.test
SUMMARY:课程\\,测试
DTSTART;TZID=Asia/Shanghai:20260907T090000
DTEND;TZID=Asia/Shanghai:20260907T100000
RRULE:FREQ=WEEKLY;BYDAY=MO,WE;COUNT=4
EXDATE;TZID=Asia/Shanghai:20260909T090000
END:VEVENT
END:VCALENDAR
`,
    "2026-09-01T00:00:00Z",
    "2026-09-30T23:59:59Z",
  );

  assert.deepEqual(
    occurrences.map((occurrence) => new Date(occurrence.startUtcMs).toISOString()),
    [
      "2026-09-07T01:00:00.000Z",
      "2026-09-14T01:00:00.000Z",
      "2026-09-16T01:00:00.000Z",
    ],
  );
  assert.equal(occurrences[0]?.summary, "课程,测试");
});

test("applies RECURRENCE-ID overrides", () => {
  const occurrences = expand(
    `BEGIN:VCALENDAR
VERSION:2.0
BEGIN:VEVENT
UID:override@example.test
SUMMARY:原课程
DTSTART;TZID=Asia/Shanghai:20260907T090000
DTEND;TZID=Asia/Shanghai:20260907T100000
RRULE:FREQ=DAILY;COUNT=3
END:VEVENT
BEGIN:VEVENT
UID:override@example.test
SUMMARY:调整后的课程
RECURRENCE-ID;TZID=Asia/Shanghai:20260908T090000
DTSTART;TZID=Asia/Shanghai:20260908T110000
DTEND;TZID=Asia/Shanghai:20260908T120000
END:VEVENT
END:VCALENDAR
`,
    "2026-09-07T00:00:00Z",
    "2026-09-10T00:00:00Z",
  );

  assert.deepEqual(
    occurrences.map((occurrence) => new Date(occurrence.startUtcMs).toISOString()),
    [
      "2026-09-07T01:00:00.000Z",
      "2026-09-08T03:00:00.000Z",
      "2026-09-09T01:00:00.000Z",
    ],
  );
  assert.equal(occurrences[1]?.summary, "调整后的课程");
});

test("skips date-only events without scheduling them", () => {
  const events = parseCalendar(`BEGIN:VCALENDAR
VERSION:2.0
BEGIN:VEVENT
UID:all-day@example.test
SUMMARY:全天事件
DTSTART;VALUE=DATE:20260907
DTEND;VALUE=DATE:20260908
END:VEVENT
END:VCALENDAR
`);

  assert.equal(events.length, 0);
});
