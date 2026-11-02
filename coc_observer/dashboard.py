"""Tkinter dashboard; observation runs on a worker and never controls the game."""

import queue
import threading
import tkinter as tk
from tkinter import ttk

from .analyzer import analyze
from .recommendations import recommend
from .screen import capture_primary_screen
from .storage import ObservationStore
from .vision import observe_frame


class Dashboard:
    def __init__(self, root: tk.Tk, store: ObservationStore, interval_seconds: int = 5):
        self.root = root
        self.store = store
        self.interval_ms = interval_seconds * 1000
        self.results = queue.Queue()
        self.running = False
        root.title("CoC Village Observer")
        root.geometry("1000x720")
        root.minsize(800, 560)
        self._build_ui()
        root.after(300, self._schedule_observation)
        root.after(100, self._poll_results)
        root.protocol("WM_DELETE_WINDOW", self._close)

    def _build_ui(self):
        style = ttk.Style()
        style.configure("Title.TLabel", font=("Segoe UI", 19, "bold"))
        style.configure("Section.TLabel", font=("Segoe UI", 12, "bold"))
        container = ttk.Frame(self.root, padding=18)
        container.pack(fill="both", expand=True)
        ttk.Label(container, text="Village intelligence", style="Title.TLabel").pack(anchor="w")
        self.status = ttk.Label(container, text="Starting read-only screen observation...")
        self.status.pack(anchor="w", pady=(4, 14))

        resources = ttk.LabelFrame(container, text="Live resources", padding=12)
        resources.pack(fill="x")
        self.resource_labels = {}
        for name in ("gold", "elixir", "dark_elixir", "gems"):
            label = ttk.Label(resources, text=f"{name.replace('_', ' ').title()}: --", width=25)
            label.pack(side="left", padx=8)
            self.resource_labels[name] = label

        facts = ttk.Frame(container)
        facts.pack(fill="x", pady=12)
        self.village_label = ttk.Label(facts, text="Town Hall: Unknown  |  Builders: Unknown  |  Completion: Unknown")
        self.village_label.pack(anchor="w")
        self.upgrades_label = ttk.Label(facts, text="Visible upgrade timers: Unknown")
        self.upgrades_label.pack(anchor="w", pady=(5, 0))
        ttk.Label(container, text="Recommended upgrades", style="Section.TLabel").pack(anchor="w", pady=(4, 4))
        columns = ("priority", "name", "category", "cost", "savings", "affordable")
        self.table = ttk.Treeview(container, columns=columns, show="headings", height=8)
        for column, title, width in (
            ("priority", "Priority", 80), ("name", "Building", 220),
            ("category", "Category", 130), ("cost", "Hammer Jam cost", 140),
            ("savings", "Savings", 110), ("affordable", "Affordable", 110),
        ):
            self.table.heading(column, text=title)
            self.table.column(column, width=width, anchor="w")
        self.table.pack(fill="x")
        ttk.Label(container, text="Observation log", style="Section.TLabel").pack(anchor="w", pady=(14, 4))
        self.log = tk.Text(container, height=10, wrap="word", state="disabled", font=("Consolas", 9))
        self.log.pack(fill="both", expand=True)

    def _schedule_observation(self):
        if not self.running:
            self.running = True
            threading.Thread(target=self._observe, daemon=True).start()
        self.root.after(self.interval_ms, self._schedule_observation)

    def _observe(self):
        try:
            frame, width, height = capture_primary_screen()
            self.results.put((observe_frame(frame, width, height), None))
        except Exception as exc:
            self.results.put((None, str(exc)))

    def _poll_results(self):
        try:
            result = self.results.get_nowait()
        except queue.Empty:
            pass
        else:
            self._show_result(result)
        if self.root.winfo_exists():
            self.root.after(100, self._poll_results)

    def _show_result(self, result):
        self.running = False
        observation, error = result
        if error:
            self.status.configure(text=f"Observation unavailable: {error}")
            self._append_log(error)
            return
        try:
            self.store.save(observation)
        except Exception as exc:
            self._append_log(f"Local database error: {exc}")
        analysis = analyze(observation)
        for name, label in self.resource_labels.items():
            reading = observation.resources[name]
            value = f"{reading.value:,}" if reading.value is not None else "Unknown"
            confidence = f" ({reading.confidence:.0%})" if reading.value is not None else ""
            label.configure(text=f"{name.replace('_', ' ').title()}: {value}{confidence}")
        town_hall = observation.town_hall_level.value or "Unknown"
        if observation.town_hall_level.confidence < 0.65:
            town_hall = "Unknown"
        builders = "Unknown"
        if (
            observation.builders_available.value is not None
            and observation.builders_available.confidence >= 0.65
            and observation.builders_total.confidence >= 0.65
        ):
            builders = f"{observation.builders_available.value}/{observation.builders_total.value}"
        self.village_label.configure(
            text=f"Town Hall: {town_hall}  |  Builders: {builders}  |  "
                 f"Completion: {analysis['completion_percentage'] or 'Unknown'}"
        )
        timers = [
            f"{self._format_duration(timer['remaining_seconds'])}"
            f"{' (low confidence)' if timer['confidence'] < 0.65 else ''}"
            for timer in observation.active_upgrades
        ]
        self.upgrades_label.configure(
            text="Visible upgrade timers: " + (", ".join(timers) if timers else "None detected")
        )
        for item in self.table.get_children():
            self.table.delete(item)
        for item in recommend(observation):
            self.table.insert("", "end", values=(
                item["priority"], item["name"], item["category"],
                item.get("hammer_jam_cost", "Unknown"), item.get("savings", "Unknown"),
                "Yes" if item.get("affordable") is True else (
                    "No" if item.get("affordable") is False else "Unknown"
                ),
            ))
        if not observation.buildings:
            self._append_log("No upgrade recommendations: no building identities were reliably recognized.")
        self.status.configure(text=f"Last observation: {observation.observed_at}  |  Read-only")
        for note in observation.notes:
            self._append_log(note)
        self._append_log(
            f"Observed {len(observation.active_upgrades)} visible timer(s); "
            f"{len(observation.buildings)} building(s) identified."
        )

    @staticmethod
    def _format_duration(seconds):
        days, remainder = divmod(seconds, 86400)
        hours, remainder = divmod(remainder, 3600)
        minutes, _ = divmod(remainder, 60)
        parts = []
        if days:
            parts.append(f"{days}d")
        if hours:
            parts.append(f"{hours}h")
        if minutes or not parts:
            parts.append(f"{minutes}m")
        return " ".join(parts)

    def _append_log(self, message):
        self.log.configure(state="normal")
        self.log.insert("end", f"{message}\n")
        self.log.see("end")
        self.log.configure(state="disabled")

    def _close(self):
        self.root.destroy()
