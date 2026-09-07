// ==UserScript==
// @name         厦大教务课程表导出 ICS
// @version      1.0.0
// @description  将厦门大学教务系统当前学期课程表导出为标准 iCalendar 文件
// @match        https://jw.xmu.edu.cn/gsapp/sys/wdkbapp/*default/index.do*
// @run-at       document-idle
// @grant        none
// ==/UserScript==

(function () {
    'use strict';

    var BUTTON_ID = 'xmu-course-ics-export-button';
    var APP_NAME = 'wdkbapp';
    var TIME_ZONE = 'Asia/Shanghai';

    function text(value) {
        if (value === undefined || value === null) {
            return '';
        }
        return String(value).replace(/\s+/g, ' ').trim();
    }

    function firstValue(object, names) {
        if (!object) {
            return '';
        }
        for (var i = 0; i < names.length; i += 1) {
            if (object[names[i]] !== undefined && object[names[i]] !== null && text(object[names[i]]) !== '') {
                return object[names[i]];
            }
        }
        return '';
    }

    function firstNonEmpty(values) {
        for (var i = 0; i < values.length; i += 1) {
            var value = text(values[i]);
            if (value) {
                return value;
            }
        }
        return '';
    }

    function asArray(value) {
        if (Array.isArray(value)) {
            return value;
        }
        if (value && Array.isArray(value.rows)) {
            return value.rows;
        }
        if (value && typeof value === 'object') {
            var values = Object.keys(value).map(function (key) {
                return value[key];
            });
            if (values.length && values.every(function (item) {
                return item && typeof item === 'object' && !Array.isArray(item);
            })) {
                return values;
            }
        }
        return [];
    }

    function appPath() {
        if (window.WIS_EMAP_SERV && typeof window.WIS_EMAP_SERV.getAppPath === 'function') {
            return window.WIS_EMAP_SERV.getAppPath();
        }
        var pathname = window.location.pathname;
        var sysIndex = pathname.indexOf('/sys/');
        if (sysIndex < 0) {
            return '/gsapp/sys/' + APP_NAME;
        }
        var rest = pathname.slice(sysIndex + 5);
        return pathname.slice(0, sysIndex) + '/sys/' + rest.split('/')[0];
    }

    function apiUrl(path) {
        if (window.WIS_EMAP_SERV && typeof window.WIS_EMAP_SERV.getAbsPath === 'function') {
            return window.WIS_EMAP_SERV.getAbsPath(path);
        }
        return appPath() + '/' + String(path).replace(/^\/+/, '');
    }

    function requestJson(path, data) {
        var params = new URLSearchParams();
        Object.keys(data || {}).forEach(function (key) {
            if (data[key] !== undefined && data[key] !== null) {
                params.set(key, String(data[key]));
            }
        });
        return fetch(apiUrl(path), {
            method: 'POST',
            credentials: 'same-origin',
            headers: {
                'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8',
                'Accept': 'application/json, text/javascript, */*; q=0.01'
            },
            body: params.toString()
        }).then(function (response) {
            if (!response.ok) {
                throw new Error('接口请求失败（HTTP ' + response.status + '）');
            }
            return response.text();
        }).then(function (body) {
            try {
                return JSON.parse(body);
            } catch (error) {
                throw new Error('接口未返回 JSON，请确认已经登录教务系统');
            }
        });
    }

    function responseArray(response, names) {
        if (!response) {
            return [];
        }
        for (var i = 0; i < names.length; i += 1) {
            var direct = asArray(response[names[i]]);
            if (direct.length) {
                return direct;
            }
        }
        if (response.data) {
            var data = asArray(response.data);
            if (data.length) {
                return data;
            }
            for (var key in response.data) {
                if (Object.prototype.hasOwnProperty.call(response.data, key)) {
                    var nested = asArray(response.data[key]);
                    if (nested.length) {
                        return nested;
                    }
                }
            }
        }
        if (response.datas) {
            for (var dataKey in response.datas) {
                if (Object.prototype.hasOwnProperty.call(response.datas, dataKey)) {
                    var rows = asArray(response.datas[dataKey]);
                    if (rows.length) {
                        return rows;
                    }
                }
            }
        }
        return [];
    }

    function studentNumber() {
        var query = new URLSearchParams(window.location.search);
        var fromQuery = query.get('reqXH') || query.get('XH');
        if (fromQuery) {
            return fromQuery;
        }
        var pageMeta = window.pageMeta && window.pageMeta.params;
        if (pageMeta) {
            return firstNonEmpty([pageMeta.XH, pageMeta.USERID]);
        }
        var info = document.getElementById('xsxxprint');
        var match = info && info.textContent.match(/学号\s*[：:]\s*([\w-]+)/);
        return match ? match[1] : '';
    }

    function currentTerm() {
        var select = document.getElementById('myXnxqSelect');
        if (!select || !select.value) {
            throw new Error('课表尚未加载完成，请稍后再试');
        }
        var option = select.options[select.selectedIndex];
        return {
            code: select.value,
            name: option ? text(option.textContent) : select.value
        };
    }

    function parseDate(value) {
        if (value instanceof Date && !isNaN(value.getTime())) {
            return new Date(value.getFullYear(), value.getMonth(), value.getDate());
        }
        var valueText = text(value);
        if (!valueText) {
            return null;
        }
        var match = valueText.match(/(\d{4})\s*[年\/-](\d{1,2})\s*[月\/-](\d{1,2})/);
        if (!match) {
            match = valueText.match(/(\d{4})(\d{2})(\d{2})/);
        }
        if (!match) {
            return null;
        }
        var date = new Date(Number(match[1]), Number(match[2]) - 1, Number(match[3]));
        return isNaN(date.getTime()) ? null : date;
    }

    function dateFrom(row, names) {
        for (var i = 0; i < names.length; i += 1) {
            var date = parseDate(row && row[names[i]]);
            if (date) {
                return date;
            }
        }
        return null;
    }

    function integer(value) {
        var match = text(value).match(/-?\d+/);
        return match ? Number(match[0]) : NaN;
    }

    function parseWeekNumbers(value) {
        var valueText = text(value);
        if (!valueText || /每周|全周|全学期/.test(valueText)) {
            return [];
        }
        var numbers = [];
        var rangePattern = /(\d+)\s*(?:-|~|～|至|到)\s*(\d+)/g;
        var range;
        while ((range = rangePattern.exec(valueText))) {
            var start = Number(range[1]);
            var end = Number(range[2]);
            if (start > end) {
                var swap = start;
                start = end;
                end = swap;
            }
            for (var week = start; week <= end && week <= 60; week += 1) {
                numbers.push(week);
            }
        }
        var singles = valueText.match(/\d+/g) || [];
        singles.forEach(function (single) {
            var weekNumber = Number(single);
            if (weekNumber >= 1 && weekNumber <= 60) {
                numbers.push(weekNumber);
            }
        });
        var unique = Array.from(new Set(numbers));
        if (/单周|奇数周/.test(valueText)) {
            unique = unique.filter(function (weekNumber) { return weekNumber % 2 === 1; });
        }
        if (/双周|偶数周/.test(valueText)) {
            unique = unique.filter(function (weekNumber) { return weekNumber % 2 === 0; });
        }
        return unique.sort(function (a, b) { return a - b; });
    }

    function rowWeekNumbers(row) {
        var names = [
            'ZCMC', 'ZC', 'ZC_DISPLAY', 'SKZC', 'SKZC_DISPLAY', 'PKZC', 'PKZC_DISPLAY',
            'JXZC', 'JXZC_DISPLAY', 'WEEK', 'WEEKS', 'WEEK_DISPLAY'
        ];
        var found = [];
        var hasWeekField = false;
        names.forEach(function (name) {
            if (row && row[name] !== undefined && row[name] !== null && text(row[name]) !== '') {
                hasWeekField = true;
                found = found.concat(parseWeekNumbers(row[name]));
            }
        });
        return {
            explicit: hasWeekField && found.length > 0,
            weeks: Array.from(new Set(found)).sort(function (a, b) { return a - b; })
        };
    }

    function weekdayCode(value) {
        var valueText = text(value);
        if (/日/.test(valueText)) { return 7; }
        if (/一/.test(valueText)) { return 1; }
        if (/二/.test(valueText)) { return 2; }
        if (/三/.test(valueText)) { return 3; }
        if (/四/.test(valueText)) { return 4; }
        if (/五/.test(valueText)) { return 5; }
        if (/六/.test(valueText)) { return 6; }
        var code = integer(valueText);
        return code === 0 ? 7 : code;
    }

    function addDays(date, days) {
        var result = new Date(date.getTime());
        result.setDate(result.getDate() + days);
        return result;
    }

    function dateForWeek(week, weekday) {
        if (!week || !week.start || !weekday) {
            return null;
        }
        var startDay = week.start.getDay();
        var offset;
        if (startDay === 0) {
            offset = weekday === 7 ? 0 : weekday;
        } else {
            offset = weekday === 7 ? 6 : weekday - 1;
        }
        return addDays(week.start, offset);
    }

    function parseWeekTable(response) {
        var rows = responseArray(response, ['zcList', 'weeks', 'weekList']);
        var weeks = {};
        rows.forEach(function (row) {
            var number = integer(firstValue(row, ['ZC', 'WEEK', 'week', 'zc']));
            if (!number || number < 1 || number > 60) {
                var guessed = parseWeekNumbers(firstValue(row, ['ZCMC', 'MC', 'name']));
                number = guessed.length === 1 ? guessed[0] : NaN;
            }
            var start = dateFrom(row, [
                'KSRQ', 'KSRQ_DISPLAY', 'START_DATE', 'STARTDATE', 'WEEK_START', 'WEEKSTART',
                'RQ', 'RQ_DISPLAY', 'DATE', 'date', 'beginDate'
            ]);
            var end = dateFrom(row, ['JSRQ', 'JSRQ_DISPLAY', 'END_DATE', 'ENDDATE', 'WEEK_END', 'WEEKEND', 'endDate']);
            if (!start && end) {
                start = addDays(end, -6);
            }
            if (number) {
                weeks[number] = { number: number, start: start, end: end };
            }
        });
        return weeks;
    }

    function mondayOf(date) {
        var result = new Date(date.getTime());
        var offset = (result.getDay() + 6) % 7;
        result.setDate(result.getDate() - offset);
        result.setHours(0, 0, 0, 0);
        return result;
    }

    function currentTermCode() {
        var term = window.currentXnxq;
        return term && firstNonEmpty([term.XNXQDM, term.DM, term.value]);
    }

    function fillWeekDates(weeks, response, termCode) {
        var weekNumbers = Object.keys(weeks).map(Number).sort(function (a, b) { return a - b; });
        if (!weekNumbers.length || weekNumbers.every(function (number) { return weeks[number].start; })) {
            return;
        }
        var currentCode = currentTermCode();
        var anchor;
        var currentWeek;
        if (!currentCode || String(currentCode) === String(termCode)) {
            anchor = parseDate(window.todayDate) || new Date();
            currentWeek = integer(response && response.currentZc);
            if (!currentWeek || currentWeek < 1) {
                currentWeek = 1;
            }
            anchor = addDays(mondayOf(anchor), -7 * (currentWeek - 1));
        } else {
            var answer = window.prompt('该学期没有提供周次日期。请输入第 1 周周一日期（格式：YYYY-MM-DD）：', '');
            anchor = parseDate(answer);
            if (!anchor) {
                throw new Error('未提供有效的第 1 周日期，已取消导出');
            }
            anchor = mondayOf(anchor);
            currentWeek = 1;
        }
        weekNumbers.forEach(function (number) {
            if (!weeks[number].start) {
                weeks[number].start = addDays(anchor, 7 * (number - 1));
            }
        });
    }

    function periodTime(value, periods, scheme, kind) {
        var valueText = text(value);
        var direct = clockTime(valueText);
        if (direct) {
            return direct;
        }
        var code = integer(valueText);
        if (!isNaN(code)) {
            var period = periods.find(function (item) {
                var periodScheme = firstValue(item, ['JCFADM', 'JCFAD', 'scheme']);
                var periodCode = integer(firstValue(item, ['DM', 'JCDM', 'JC', 'code']));
                return (scheme === '' || text(periodScheme) === text(scheme)) && periodCode === code;
            });
            if (period) {
                return clockTime(firstValue(period, kind === 'start' ? ['KSSJ', 'START_TIME'] : ['JSSJ', 'END_TIME']));
            }
        }
        return null;
    }

    function clockTime(value) {
        var valueText = text(value);
        if (!valueText) {
            return null;
        }
        var match = valueText.match(/^(\d{1,2})\s*[:：]\s*(\d{2})(?:\s*:\s*\d{2})?$/);
        if (match) {
            return { hour: Number(match[1]), minute: Number(match[2]) };
        }
        if (/^\d{3,4}$/.test(valueText)) {
            var padded = valueText.padStart(4, '0');
            return { hour: Number(padded.slice(0, 2)), minute: Number(padded.slice(2)) };
        }
        return null;
    }

    function dateTime(date, time) {
        if (!date || !time || time.hour > 23 || time.minute > 59) {
            return null;
        }
        var result = new Date(date.getTime());
        result.setHours(time.hour, time.minute, 0, 0);
        return result;
    }

    function dateKey(date) {
        return date.getFullYear() + '-' + String(date.getMonth() + 1).padStart(2, '0') + '-' + String(date.getDate()).padStart(2, '0');
    }

    function icsDateTime(date) {
        return date.getFullYear() + String(date.getMonth() + 1).padStart(2, '0') + String(date.getDate()).padStart(2, '0') +
            'T' + String(date.getHours()).padStart(2, '0') + String(date.getMinutes()).padStart(2, '0') + '00';
    }

    function utcDateTime(date) {
        return date.getUTCFullYear() + String(date.getUTCMonth() + 1).padStart(2, '0') + String(date.getUTCDate()).padStart(2, '0') +
            'T' + String(date.getUTCHours()).padStart(2, '0') + String(date.getUTCMinutes()).padStart(2, '0') + String(date.getUTCSeconds()).padStart(2, '0') + 'Z';
    }

    function icsText(value) {
        return text(value).replace(/\\/g, '\\\\').replace(/;/g, '\\;').replace(/,/g, '\\,').replace(/\r?\n/g, '\\n');
    }

    function foldLine(line) {
        var encoder = window.TextEncoder ? new TextEncoder() : null;
        var result = [];
        var current = '';
        var bytes = 0;
        var limit = 75;
        Array.from(line).forEach(function (character) {
            var characterBytes = encoder ? encoder.encode(character).length : character.length;
            if (current && bytes + characterBytes > limit) {
                result.push(current);
                current = ' ';
                bytes = 1;
                limit = 74;
            }
            current += character;
            bytes += characterBytes;
        });
        if (current) {
            result.push(current);
        }
        return result.join('\r\n');
    }

    function hash(value) {
        var result = 2166136261;
        for (var i = 0; i < value.length; i += 1) {
            result ^= value.charCodeAt(i);
            result = Math.imul(result, 16777619);
        }
        return ('00000000' + (result >>> 0).toString(16)).slice(-8);
    }

    function courseFields(row) {
        var course = firstNonEmpty([row.KCMC, row.KCMCYW, row.KCYWMC, row.KCYW, row.COURSE_NAME]);
        var className = firstNonEmpty([row.BJMC, row.JXBMC, row.BJQH, row.CLASS_NAME]);
        var teacher = firstNonEmpty([row.JSXM, row.RKJS, row.SKJS, row.TEACHER]);
        var room = firstNonEmpty([row.JASMC, row.JAS, row.SKJAS, row.ROOM]);
        var campus = firstNonEmpty([row.XQDM_DISPLAY, row.XQMC, row.CAMPUS]);
        var note = firstNonEmpty([row.KBBZ, row.XKBZ, row.BZ, row.NOTE]);
        return {
            course: course || '未命名课程',
            className: className,
            teacher: teacher,
            room: room,
            campus: campus,
            note: note
        };
    }

    function makeEvent(row, date, start, end, termName, source) {
        if (!date || !start || !end || end <= start) {
            return null;
        }
        var fields = courseFields(row);
        var location = [fields.campus, fields.room].filter(Boolean).join(' ');
        var description = [
            fields.className && '教学班：' + fields.className,
            fields.teacher && '教师：' + fields.teacher,
            fields.note && '备注：' + fields.note,
            source
        ].filter(Boolean).join('\n');
        var identity = [termName, fields.course, fields.className, dateKey(date), start.getTime(), end.getTime(), fields.teacher, fields.room].join('|');
        return {
            uid: 'xmu-' + hash(identity) + '@xmu-course-calendar',
            start: start,
            end: end,
            summary: fields.course,
            location: location,
            description: description
        };
    }

    function dateFromRow(row) {
        return dateFrom(row, ['RQ', 'RQ_DISPLAY', 'DATE', 'DATE_DISPLAY', 'SKRQ', 'SJRQ', 'courseDate']);
    }

    function rowWeekday(row) {
        return weekdayCode(firstValue(row, ['XQ', 'XQDM', 'XQ_DISPLAY', 'WEEKDAY', 'DAY']));
    }

    function eventRows(rows, periods, weeks, termName) {
        var events = [];
        var missingDate = 0;
        var allWeekNumbers = Object.keys(weeks).map(Number).sort(function (a, b) { return a - b; });
        rows.forEach(function (row) {
            var scheme = firstValue(row, ['JCFADM', 'JCFAD', 'scheme']);
            var startTime = periodTime(firstValue(row, ['KSSJ', 'KSJCDM', 'START_TIME', 'START']), periods, scheme, 'start');
            var endTime = periodTime(firstValue(row, ['JSSJ', 'JSJCDM', 'END_TIME', 'END']), periods, scheme, 'end');
            var weekday = rowWeekday(row);
            if (!startTime || !endTime || !weekday) {
                return;
            }
            var directDate = dateFromRow(row);
            if (directDate) {
                var directEvent = makeEvent(row, directDate, dateTime(directDate, startTime), dateTime(directDate, endTime), termName, '教务系统日期安排');
                if (directEvent) {
                    events.push(directEvent);
                }
                return;
            }
            var weekInfo = rowWeekNumbers(row);
            var numbers = weekInfo.explicit ? weekInfo.weeks : allWeekNumbers;
            numbers.forEach(function (number) {
                var date = dateForWeek(weeks[number], weekday);
                if (!date) {
                    missingDate += 1;
                    return;
                }
                var event = makeEvent(row, date, dateTime(date, startTime), dateTime(date, endTime), termName, '第' + number + '周');
                if (event) {
                    events.push(event);
                }
            });
        });
        return { events: events, missingDate: missingDate };
    }

    function tableRows() {
        var table = document.querySelector('#kbckBottom-index-table table');
        if (!table) {
            return [];
        }
        var headers = Array.from(table.querySelectorAll('thead th')).map(function (cell) { return text(cell.textContent); });
        return Array.from(table.querySelectorAll('tbody tr')).map(function (tr) {
            var cells = Array.from(tr.children).map(function (cell) { return text(cell.textContent); });
            var row = {};
            cells.forEach(function (value, index) {
                row[headers[index] || String(index)] = value;
            });
            row.RQ = row.RQ || row['日期'];
            row.XQ_DISPLAY = row.XQ_DISPLAY || row['星期'];
            row.KSJCDM = row.KSJCDM || row['开始节次代码'] || row['开始节次'];
            row.JSJCDM = row.JSJCDM || row['结束节次代码'] || row['结束节次'];
            row.KCMC = row.KCMC || row['课程名称'];
            row.BJMC = row.BJMC || row['班级名称'];
            row.XQDM_DISPLAY = row.XQDM_DISPLAY || row['校区'];
            row.JASMC = row.JASMC || row['教室名称'] || row['教室'];
            row.KBBZ = row.KBBZ || row['备注'];
            return row;
        }).filter(function (row) {
            return row.RQ && !/暂无数据/.test(row.RQ);
        });
    }

    function deduplicate(events) {
        var seen = new Set();
        return events.filter(function (event) {
            if (seen.has(event.uid)) {
                return false;
            }
            seen.add(event.uid);
            return true;
        }).sort(function (a, b) {
            return a.start - b.start || a.summary.localeCompare(b.summary, 'zh-Hans');
        });
    }

    function makeCalendar(events, termName) {
        var lines = [
            'BEGIN:VCALENDAR',
            'VERSION:2.0',
            'PRODID:-//XMU//Course Schedule//CN',
            'CALSCALE:GREGORIAN',
            'METHOD:PUBLISH',
            'X-WR-CALNAME:' + icsText('厦门大学课程表 ' + termName),
            'X-WR-TIMEZONE:' + TIME_ZONE
        ];
        events.forEach(function (event) {
            lines.push('BEGIN:VEVENT');
            lines.push('UID:' + event.uid);
            lines.push('DTSTAMP:' + utcDateTime(new Date()));
            lines.push('DTSTART;TZID=' + TIME_ZONE + ':' + icsDateTime(event.start));
            lines.push('DTEND;TZID=' + TIME_ZONE + ':' + icsDateTime(event.end));
            lines.push('SUMMARY:' + icsText(event.summary));
            if (event.location) {
                lines.push('LOCATION:' + icsText(event.location));
            }
            if (event.description) {
                lines.push('DESCRIPTION:' + icsText(event.description));
            }
            lines.push('TRANSP:OPAQUE');
            lines.push('END:VEVENT');
        });
        lines.push('END:VCALENDAR');
        return lines.map(foldLine).join('\r\n') + '\r\n';
    }

    function download(content, termName) {
        var blob = new Blob(['\uFEFF', content], { type: 'text/calendar;charset=utf-8' });
        var url = URL.createObjectURL(blob);
        var anchor = document.createElement('a');
        var filename = ('xmu-course-schedule-' + (termName || 'semester')).replace(/[\\/:*?"<>|]/g, '_') + '.ics';
        anchor.href = url;
        anchor.download = filename;
        anchor.style.display = 'none';
        document.body.appendChild(anchor);
        anchor.click();
        anchor.remove();
        setTimeout(function () { URL.revokeObjectURL(url); }, 1000);
    }

    function setButtonState(button, label, disabled) {
        button.textContent = label;
        button.disabled = disabled;
        button.style.opacity = disabled ? '0.65' : '1';
    }

    async function exportCalendar(button) {
        var term = currentTerm();
        var xh = studentNumber();
        setButtonState(button, '正在读取课表…', true);
        try {
            var common = { XNXQDM: term.code };
            if (xh) {
                common.XH = xh;
            }
            var responses = await Promise.all([
                requestJson('wdkcb/queryXsskjc.do', common),
                requestJson('wdkcb/queryXspkjg.do', common),
                requestJson('wdkcb/getZcxx.do', { XNXQDM: term.code })
            ]);
            var periods = responseArray(responses[0], ['data', 'rows']);
            var scheduleRows = responseArray(responses[1], ['pkjgList', 'data', 'rows']);
            var weeks = parseWeekTable(responses[2]);
            fillWeekDates(weeks, responses[2], term.code);
            if (!scheduleRows.length && xh) {
                var retry = await requestJson('wdkcb/queryXspkjg.do', { XNXQDM: term.code });
                scheduleRows = responseArray(retry, ['pkjgList', 'data', 'rows']);
            }
            var generated = eventRows(scheduleRows, periods, weeks, term.name);
            var dateRows = tableRows();
            var dated = eventRows(dateRows, periods, weeks, term.name);
            var events = deduplicate(generated.events.concat(dated.events));
            if (!events.length) {
                throw new Error('没有找到可导出的课程。请确认课表已加载，并检查学年学期选择。');
            }
            download(makeCalendar(events, term.name), term.name);
            var warning = generated.missingDate ? '，其中 ' + generated.missingDate + ' 条课程缺少周次日期' : '';
            setButtonState(button, '已导出 ' + events.length + ' 项', false);
            button.title = '已导出 ' + events.length + ' 个日历事件' + warning;
            window.setTimeout(function () { setButtonState(button, '导出 ICS', false); }, 4000);
        } catch (error) {
            setButtonState(button, '导出 ICS', false);
            window.alert('课程表导出失败：' + (error && error.message ? error.message : error));
        }
    }

    function installButton() {
        var host = document.getElementById('xsXx');
        if (!host || document.getElementById(BUTTON_ID)) {
            return;
        }
        var button = document.createElement('button');
        button.id = BUTTON_ID;
        button.type = 'button';
        button.className = 'bh-btn bh-btn-default';
        button.textContent = '导出 ICS';
        button.style.marginLeft = '8px';
        button.addEventListener('click', function () {
            exportCalendar(button);
        });
        host.appendChild(button);
    }

    var observer = new MutationObserver(installButton);
    observer.observe(document.documentElement, { childList: true, subtree: true });
    installButton();
})();
