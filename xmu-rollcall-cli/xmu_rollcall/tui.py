"""Shared terminal presentation. No account or network operations live here."""

import click
import time
from colorsys import hsv_to_rgb
from contextlib import contextmanager
from contextvars import ContextVar
from rich import box
from rich.console import Console, Group
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich.live import Live
from rich.progress_bar import ProgressBar

from . import __version__

console = Console(highlight=False)
_rollcall_view = ContextVar("rollcall_view", default=None)


def rollcall_output_active():
    return _rollcall_view.get() is not None


def update_rollcall(**changes):
    view = _rollcall_view.get()
    if view is not None:
        view.update(**changes)


class RollcallView:
    """Presentation state scoped to one batch; never performs account operations."""

    def __init__(self, name, runtime, queries, interval):
        self.system = menu_rows([
            ("Account", str(name)), ("Detected at", time.strftime("%H:%M:%S")),
            ("Running time", runtime), ("Queries", str(queries)),
        ], key_style="magenta")
        self.interval = interval
        self.data = {}
        self.results = []
        self.live = None

    def update(self, **changes):
        if "rollcall" in changes:
            if self.data:
                self.results.append(Text.assemble(
                    (f"{self.data['index']}. ", "cyan"),
                    (str(self.data["rollcall"]["course_title"]), "default"),
                    (f" · {self.data['state']}", "dim")))
            self.data = {"state": "detected", "number_code": None,
                         "signed": None, "total": None, "target": None}
        self.data.update(changes)
        self.live.update(self.render(), refresh=True)

    def render(self):
        data = self.data
        if not data:
            return frame(Text("Reading rollcall details…"), "Rollcall activity")
        state = data["state"]
        title, color, detail = {
            "detected": ("New rollcall found", "cyan", "Reading rollcall details"),
            "waiting": ("Waiting for classmates", "yellow", "Submit when the target is reached"),
            "submitting": ("Submitting answer", "cyan", "Waiting for confirmation"),
            "success": ("Rollcall answered", "green", "Answer confirmed"),
            "failed": ("Answering failed", "red", "No confirmation received · see log for details"),
            "already": ("Already answered", "green", "No submission needed"),
            "unsupported": ("QRcode not supported", "yellow", "Please sign in manually · next attempt in 5 minutes"),
            "interrupted": ("Interrupted", "yellow", "Processing stopped"),
        }[state]
        rollcall = data["rollcall"]
        kind = "Radar" if rollcall["is_radar"] else "Number" if rollcall["is_number"] else "QRcode"
        content = [menu_rows([
            ("Course", str(rollcall["course_title"])),
            ("Created by", f"{rollcall['department_name']} · {rollcall['created_by_name']}"),
            ("Type", f"{kind} rollcall"),
        ]), Text("")]
        if data["number_code"] is not None:
            content.extend([Text.assemble(("Number code   ", "dim"),
                                          (str(data["number_code"]), "bold yellow")), Text("")])
        if data.get("target_label"):
            signed, total, target = data["signed"], data["total"], data["target"]
            count = "unknown" if signed is None else f"{signed} / {total}"
            content.append(Text(f"Classmates signed: {count} · Target: {data['target_label']}", style="yellow"))
            if signed is not None and target is not None and target > 0:
                content.append(ProgressBar(total=target, completed=min(signed, target),
                                           complete_style="yellow", finished_style="green"))
            elif state == "waiting":
                content.append(Text("Attendance unavailable · retrying…", style="dim"))
            content.append(Text(""))
        content.extend([Text(f"● {title}", style=f"bold {color}"), Text(detail, style="dim")])
        monitor = Group(Text("● Active", style="bold green"), Text(""),
                        Text(f"{data['count']} rollcall(s) in this batch"),
                        Text(f"Checking every {self.interval} second(s)", style="dim"))
        steps = Text()
        labels = ["Detected", "Waiting", "Submitting", "Confirmed"]
        active = {"detected": 0, "waiting": 1, "submitting": 2}.get(state, 3)
        if state in {"already", "unsupported", "interrupted"}:
            labels, active = ["Detected", title], 1
        elif state == "failed":
            labels[-1] = "Failed"
        for index, label in enumerate(labels):
            if index:
                steps.append("  >  ", "bright_black")
            steps.append(label, f"bold {color}" if index == active else "dim")
        return frame(Group(
            sections(panel(self.system, "System status", "blue"), panel(monitor, "Rollcall monitor")),
            Text(""), panel(Group(*content), f"Rollcall · {data['index']} of {data['count']}", color),
            Text(""), steps, *self.results,
        ), "Rollcall activity", subtitle="Ctrl+C to exit")


@contextmanager
def rollcall_activity(name, runtime, queries, interval):
    view = RollcallView(name, runtime, queries, interval)
    with Live(view.render(), console=console, auto_refresh=False) as live:
        view.live = live
        token = _rollcall_view.set(view)
        try:
            yield view
        except BaseException as exc:
            if view.data:
                view.update(state="interrupted" if isinstance(exc, KeyboardInterrupt) else "failed")
            raise
        finally:
            _rollcall_view.reset(token)


def panel(content, title, style="cyan"):
    return Panel(content, title=Text(title), title_align="left",
                 border_style=style, box=box.ROUNDED, safe_box=False)


def frame(content, title="Welcome back", subtitle="Ctrl+C to cancel"):
    heading = Text.assemble(("XMU Rollcall", "bold cyan"), (" · ", "dim"),
                            (f"v{__version__}", "yellow"))
    return Panel(Group(Text(title, style="bold cyan"), Text(""), content),
                 title=heading, title_align="left",
                 subtitle=Text(subtitle), subtitle_align="right",
                 border_style="bright_black", box=box.ROUNDED, safe_box=False, padding=(1, 2))


def sections(*items):
    if console.width < 88:
        return Group(*items)
    layout = Table.grid(expand=True, padding=(0, 1))
    for _ in items:
        layout.add_column(ratio=1)
    layout.add_row(*items)
    return layout


def menu_rows(rows, key_style="bold cyan"):
    table = Table.grid(padding=(0, 2), expand=True)
    table.add_column(style=key_style, no_wrap=True)
    table.add_column(ratio=1)
    for key, description in rows:
        table.add_row(Text(key), Text(description))
    return table


def echo(message=""):
    # Keep legacy message colors, but never interpret account names as markup.
    console.print(Text.from_ansi(str(message)))


def prompt(message, **kwargs):
    console.rule(style="blue")
    console.print(Text.assemble(("❯ ", "bold green"), Text.from_ansi(message)), end=" ")
    return click.prompt("", prompt_suffix="› ", **kwargs)


def accounts_panel(accounts, current, settings):
    table = Table(box=box.SIMPLE, expand=True, show_edge=False, padding=(0, 1))
    table.add_column("ID", style="cyan")
    table.add_column("Account", overflow="fold", ratio=1)
    table.add_column("Wait", overflow="fold", style="yellow")
    table.add_column("Status", style="green")
    for account in accounts:
        wait = settings(account).get("wait_before_answer")
        table.add_row(str(account.get("id")),
                      Text(account.get("name") or account.get("username") or ""),
                      ("no wait" if wait is False else
                       f"{wait} of students" if isinstance(wait, str) and wait.endswith("%")
                       else f"{wait} classmates"),
                      "current" if current and account.get("id") == current.get("id") else "")
    return panel(table if accounts else Text("No accounts configured.", style="dim"), "Accounts")


def home(account, account_count):
    identity = Text("XMU\nROLLCALL", style="bold cyan")
    identity.append(f"\n\n{account_count}", style="bold yellow")
    identity.append(" configured account(s)", style="default")
    identity.append("\n" + ((account.get("name") or account.get("username") or "")
                            if account else "Run config to add your first account"),
                    style="green" if account else "yellow")
    commands = menu_rows([
        ("1 / config", "Configure accounts and rollcall settings"),
        ("2 / switch", "Switch the current account"),
        ("3 / start", "Start monitoring rollcalls"),
        ("4 / refresh", "Clear saved login session"),
    ])
    console.print(frame(sections(panel(identity, "", "blue"),
                                 panel(commands, "Commands")),
                        subtitle="Enter a number or command · Ctrl+C to exit"))


def gradient_text(value):
    text = Text(justify="center")
    for index, character in enumerate(value):
        red, green, blue = hsv_to_rgb(index / max(1, len(value) - 1) * 0.8, 0.55, 1)
        text.append(character, style=f"rgb({int(red * 255)},{int(green * 255)},{int(blue * 255)})")
    return text


def dashboard(name, local_time, runtime, queries, interval):
    hour = time.localtime().tm_hour
    greeting = "Good morning" if 5 <= hour < 12 else "Good afternoon" if 12 <= hour < 18 else "Good evening"
    status = menu_rows([("Current time", local_time), ("Running time", runtime),
                        ("Queries", str(queries))], key_style="magenta")
    monitor = Text("● Active", style="bold green")
    monitor.append(f"\n\nMonitoring for new rollcalls\nChecking every {interval} second(s)", style="default")
    credits = gradient_text("XMU-Rollcall-Bot @ KrsMt\n")
    repository = Text("Repository: https://github.com/alkali210/XMU-Rollcall-Bot",
                      style="grey62", justify="center")
    return frame(Group(sections(panel(status, "System status", "blue"), panel(monitor, "Rollcall monitor")),
                       Text(""), credits, repository),
                 title=f"{greeting}, {name}!", subtitle="Ctrl+C to exit")
