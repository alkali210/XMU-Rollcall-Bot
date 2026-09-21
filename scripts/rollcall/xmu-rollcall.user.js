// ==UserScript==
// @name         厦大 Tronclass 数字签到助手
// @version      1.0.0
// @description  在 lnt.xmu.edu.cn 上轮询待签到列表并自动完成数字签到
// @match        https://lnt.xmu.edu.cn/*
// @run-at       document-idle
// @grant        none
// ==/UserScript==

(function () {
    'use strict';

    const BASE_URL = 'https://lnt.xmu.edu.cn';
    const DEFAULT_INTERVAL_MS = 10 * 1000;
    const TOAST_HOST_ID = 'xmu-rollcall-bot-toast-host';
    const COMPLETED_KEY = 'xmu-rollcall-completed';

    const state = {
        timer: null,
        running: false,
        intervalMs: DEFAULT_INTERVAL_MS,
        discovered: new Set(),
        completed: new Set(),
    };

    function text(value) {
        return value === undefined || value === null ? '' : String(value).trim();
    }

    function isTrue(value) {
        return value === true || value === 1 || text(value).toLowerCase() === 'true';
    }

    function findValue(value, key, seen) {
        if (!value || typeof value !== 'object') {
            return undefined;
        }
        const visited = seen || new Set();
        if (visited.has(value)) {
            return undefined;
        }
        visited.add(value);

        if (!Array.isArray(value) && Object.prototype.hasOwnProperty.call(value, key)) {
            return value[key];
        }
        const values = Array.isArray(value) ? value : Object.values(value);
        for (const item of values) {
            const result = findValue(item, key, visited);
            if (result !== undefined && result !== null) {
                return result;
            }
        }
        return undefined;
    }

    function extractRollcalls(payload) {
        if (Array.isArray(payload)) {
            return payload;
        }
        const rollcalls = findValue(payload, 'rollcalls');
        return Array.isArray(rollcalls) ? rollcalls : [];
    }

    function parseBody(body) {
        const value = text(body);
        if (!value) {
            return null;
        }
        try {
            return JSON.parse(value);
        } catch (_) {
            return value;
        }
    }

    function preview(value) {
        const result = typeof value === 'string' ? value : JSON.stringify(value);
        return text(result).slice(0, 240);
    }

    async function request(path, options) {
        const response = await fetch(BASE_URL + path, {
            credentials: 'include',
            ...options,
        });
        const body = await response.text();
        const data = parseBody(body);
        if (!response.ok) {
            const suffix = preview(data);
            throw new Error(`${response.status} ${response.statusText}${suffix ? `: ${suffix}` : ''}`);
        }
        return { data, response };
    }

    function toastHost() {
        let host = document.getElementById(TOAST_HOST_ID);
        if (host) {
            return host;
        }
        host = document.createElement('div');
        host.id = TOAST_HOST_ID;
        Object.assign(host.style, {
            position: 'fixed',
            right: '16px',
            bottom: '16px',
            zIndex: '2147483647',
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'flex-end',
            gap: '8px',
            maxWidth: 'min(420px, calc(100vw - 32px))',
            pointerEvents: 'none',
        });
        document.body.appendChild(host);
        return host;
    }

    function notify(title, detail, level) {
        const message = detail ? `${title}: ${detail}` : title;
        const logger = level === 'error' ? console.error : level === 'warn' ? console.warn : console.info;
        logger(`[XMU Rollcall] ${message}`);

        if (!document.body) {
            return;
        }
        const toast = document.createElement('div');
        toast.textContent = message;
        Object.assign(toast.style, {
            color: '#fff',
            background: level === 'error' ? '#b42318' : level === 'warn' ? '#b54708' : '#175cd3',
            borderRadius: '6px',
            boxShadow: '0 4px 16px rgba(0, 0, 0, .22)',
            font: '14px/1.45 sans-serif',
            padding: '10px 14px',
            pointerEvents: 'none',
            whiteSpace: 'pre-wrap',
        });
        toastHost().appendChild(toast);
        window.setTimeout(() => toast.remove(), level === 'error' ? 8000 : 5000);
    }

    function courseName(rollcall) {
        return text(rollcall.course_title || rollcall.courseName || rollcall.title) ||
            `签到 #${text(rollcall.rollcall_id)}`;
    }

    function rollcallId(rollcall) {
        const id = rollcall && (rollcall.rollcall_id ?? rollcall.rollcallId);
        return id === undefined || id === null || text(id) === '' ? null : String(id);
    }

    function statusOf(rollcall) {
        return text(rollcall.status || rollcall.rollcall_status).toLowerCase();
    }

    function isNumberRollcall(rollcall) {
        return isTrue(rollcall.is_number) && !isTrue(rollcall.is_radar);
    }

    function isPendingNumberRollcall(rollcall) {
        return Boolean(rollcall) && !isTrue(rollcall.is_expired) &&
            isNumberRollcall(rollcall) && statusOf(rollcall) === 'absent';
    }

    function markCompleted(id) {
        state.completed.add(id);
        try {
            const old = JSON.parse(sessionStorage.getItem(COMPLETED_KEY) || '[]');
            const values = Array.isArray(old) ? old.filter(value => typeof value === 'string') : [];
            if (!values.includes(id)) {
                values.push(id);
            }
            sessionStorage.setItem(COMPLETED_KEY, JSON.stringify(values.slice(-100)));
        } catch (_) {
            // Session storage is optional; an in-memory result is sufficient.
        }
    }

    function restoreCompleted() {
        try {
            const values = JSON.parse(sessionStorage.getItem(COMPLETED_KEY) || '[]');
            if (Array.isArray(values)) {
                values.filter(value => typeof value === 'string').forEach(value => state.completed.add(value));
            }
        } catch (_) {
            // Session storage may be unavailable in a restricted browser context.
        }
    }

    async function answerNumberRollcall(rollcall) {
        const id = rollcallId(rollcall);
        const name = courseName(rollcall);
        if (!id || state.completed.has(id)) {
            return;
        }

        notify('正在获取签到码', name);
        const codeResult = await request(`/api/rollcall/${encodeURIComponent(id)}/student_rollcalls`);
        const numberCode = findValue(codeResult.data, 'number_code');
        if (numberCode === undefined || numberCode === null || text(numberCode) === '') {
            throw new Error(`${name} 的响应中没有找到 number_code`);
        }

        const code = String(numberCode);
        notify('已获取签到码', `${name}：${code}`);
        const deviceId = crypto.randomUUID();
        const answerResult = await request(`/api/rollcall/${encodeURIComponent(id)}/answer_number_rollcall`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                deviceId: String(deviceId),
                numberCode: code,
            }),
        });

        if (answerResult.response.status !== 200) {
            throw new Error(`${name} 提交返回 HTTP ${answerResult.response.status}`);
        }
        markCompleted(id);
        notify('签到完成', name);
    }

    async function runOnce() {
        if (state.running) {
            return;
        }
        state.running = true;
        try {
            const result = await request('/api/radar/rollcalls');
            const rollcalls = extractRollcalls(result.data).filter(item => item && typeof item === 'object');
            const pending = rollcalls.filter(isPendingNumberRollcall);
            const newPending = pending.filter(item => {
                const id = rollcallId(item);
                if (!id || state.discovered.has(id)) {
                    return false;
                }
                state.discovered.add(id);
                return true;
            });

            if (newPending.length) {
                notify('发现待签到课程', newPending.map(item => courseName(item)).join('、'));
            }

            for (const rollcall of pending) {
                const id = rollcallId(rollcall);
                if (!id || state.completed.has(id)) {
                    continue;
                }
                try {
                    await answerNumberRollcall(rollcall);
                } catch (error) {
                    notify('签到失败', `${courseName(rollcall)}：${error.message || error}`, 'error');
                }
            }
        } catch (error) {
            notify('获取签到列表失败', error.message || error, 'error');
        } finally {
            state.running = false;
        }
    }

    function start(intervalMs) {
        if (state.timer !== null) {
            return;
        }
        const value = Number(intervalMs);
        if (Number.isFinite(value) && value >= 1000) {
            state.intervalMs = value;
        }
        state.timer = window.setInterval(runOnce, state.intervalMs);
        notify('签到助手已启动', `每 ${state.intervalMs / 1000} 秒检查一次`);
        void runOnce();
    }

    function stop() {
        if (state.timer !== null) {
            window.clearInterval(state.timer);
            state.timer = null;
            notify('签到助手已停止');
        }
    }

    function status() {
        return {
            running: state.timer !== null,
            requestInProgress: state.running,
            intervalMs: state.intervalMs,
            discovered: [...state.discovered],
            completed: [...state.completed],
        };
    }

    restoreCompleted();
    window.XMURollcallBot = { start, stop, runOnce, status };
    start();
})();
