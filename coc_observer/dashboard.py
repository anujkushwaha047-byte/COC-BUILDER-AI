"""Read-only, two-village planning dashboard."""

import queue
import threading
import tkinter as tk
from dataclasses import asdict
from tkinter import filedialog, messagebox, ttk

from .analyzer import analyze
from .farming import LootOpportunity, analyze_opportunity
from .missions import MissionSettings, mission_summary
from .planning import UpgradeCandidate, allocate_resources, rank_upgrades
from .screen import capture_primary_screen
from .storage import ObservationStore
from .vision import observe_frame, observe_loot_screenshot


RESOURCE_NAMES = ("gold", "elixir", "dark_elixir", "gems")
VILLAGES = {"home": "Home Village", "builder_base": "Builder Base"}


class Dashboard:
    def __init__(self, root: tk.Tk, store: ObservationStore, interval_seconds: int = 5):
        self.root = root
        self.store = store
        self.interval_ms = interval_seconds * 1000
        self.results = queue.Queue()
        self.running = False
        self.observations = {"home": None, "builder_base": None}
        self.resource_labels = {}
        self.village_details = {}
        self.village_warnings = {}
        self.mission_settings = self.store.load_mission_settings()
        root.title("CoC Builder AI — Read-only Village Planner")
        root.geometry("1180x800")
        root.minsize(900, 620)
        self._build_ui()
        self._load_saved_state()
        root.after(300, self._schedule_observation)
        root.after(100, self._poll_results)
        root.protocol("WM_DELETE_WINDOW", self._close)

    def _build_ui(self):
        style = ttk.Style()
        style.configure("Title.TLabel", font=("Segoe UI", 19, "bold"))
        style.configure("Section.TLabel", font=("Segoe UI", 12, "bold"))
        root_frame = ttk.Frame(self.root, padding=14)
        root_frame.pack(fill="both", expand=True)
        ttk.Label(root_frame, text="CoC Builder AI", style="Title.TLabel").pack(anchor="w")
        self.status = ttk.Label(
            root_frame,
            text="Read-only observer · primary-screen village must be explicitly assigned",
        )
        self.status.pack(anchor="w", pady=(3, 10))
        self.tabs = ttk.Notebook(root_frame)
        self.tabs.pack(fill="both", expand=True)

        self.tab_frames = {}
        for name in (
            "Overview", "Home Village", "Builder Base", "Loot Hunter",
            "Upgrade Priority", "Wall Maxer", "Resource Manager",
            "Daily Missions", "AI Activity Logs", "Settings",
        ):
            frame = ttk.Frame(self.tabs, padding=12)
            self.tabs.add(frame, text=name)
            self.tab_frames[name] = frame

        self._build_overview_tab()
        self._build_village_tab("home", self.tab_frames["Home Village"])
        self._build_village_tab("builder_base", self.tab_frames["Builder Base"])
        self._build_loot_tab()
        self._build_priority_tab()
        self._build_wall_tab()
        self._build_resource_tab()
        self._build_missions_tab()
        self._build_activity_tab()
        self._build_settings_tab()

    def _build_overview_tab(self):
        frame = self.tab_frames["Overview"]
        ttk.Label(frame, text="Village status", style="Section.TLabel").pack(anchor="w")
        self.overview_label = ttk.Label(
            frame,
            text="Home Village: no confident observation\nBuilder Base: no confident observation",
            justify="left",
        )
        self.overview_label.pack(anchor="w", pady=8)
        ttk.Label(frame, text="Next actions", style="Section.TLabel").pack(anchor="w", pady=(16, 5))
        self.overview_text = tk.Text(frame, height=12, wrap="word", state="disabled")
        self.overview_text.pack(fill="both", expand=True)
        self._set_text(
            self.overview_text,
            "Select the village currently shown on the primary display in Settings, "
            "or analyze a local screenshot in its village tab.\n"
            "Building identities, costs, and upgrade levels remain unknown until "
            "confidence-qualified building observations are available.",
        )

    def _build_village_tab(self, village, frame):
        ttk.Label(frame, text=VILLAGES[village], style="Section.TLabel").pack(anchor="w")
        ttk.Label(
            frame,
            text="OCR readings are saved only to this village after you select its screenshot/view.",
            wraplength=950,
        ).pack(anchor="w", pady=(3, 8))
        button = ttk.Button(
            frame,
            text="Analyze a local village screenshot",
            command=lambda selected=village: self._choose_village_screenshot(selected),
        )
        button.pack(anchor="w", pady=(0, 10))
        resources = ttk.LabelFrame(frame, text="Observed resources", padding=10)
        resources.pack(fill="x")
        labels = {}
        for resource in RESOURCE_NAMES:
            label = ttk.Label(resources, text=f"{resource.replace('_', ' ').title()}: Unknown", width=27)
            label.pack(side="left", padx=5)
            labels[resource] = label
        self.resource_labels[village] = labels
        details = ttk.Label(frame, text="Builders: Unknown  |  Town Hall: Unknown")
        details.pack(anchor="w", pady=10)
        warnings = tk.Text(frame, height=7, wrap="word", state="disabled")
        warnings.pack(fill="both", expand=True)
        self.village_details[village] = details
        self.village_warnings[village] = warnings

    def _build_loot_tab(self):
        frame = self.tab_frames["Loot Hunter"]
        ttk.Label(frame, text="Screenshot-based loot estimate", style="Section.TLabel").pack(anchor="w")
        ttk.Label(
            frame,
            text="Local OCR only associates loot with legible resource labels. It does not search for opponents, "
                 "estimate troop outcomes, or initiate attacks.",
            wraplength=950,
        ).pack(anchor="w", pady=6)
        row = ttk.Frame(frame)
        row.pack(anchor="w", pady=8)
        self.loot_village = tk.StringVar(value="home")
        ttk.Label(row, text="Village:").pack(side="left", padx=(0, 5))
        ttk.Combobox(
            row, textvariable=self.loot_village,
            values=("home", "builder_base"), state="readonly", width=16,
        ).pack(side="left", padx=(0, 10))
        ttk.Button(row, text="Choose opponent screenshot", command=self._choose_loot_screenshot).pack(side="left")
        self.loot_result = ttk.Label(frame, text="Loot values: Unknown  |  Difficulty: Unknown", justify="left")
        self.loot_result.pack(anchor="w", pady=12)
        self.loot_warnings = tk.Text(frame, height=8, wrap="word", state="disabled")
        self.loot_warnings.pack(fill="both", expand=True)
        self._set_text(
            self.loot_warnings,
            "No screenshot analyzed. Loot estimates and difficulty will be marked unknown unless read reliably.",
        )

    def _build_priority_tab(self):
        frame = self.tab_frames["Upgrade Priority"]
        ttk.Label(frame, text="Ranked, village-local upgrade queue", style="Section.TLabel").pack(anchor="w")
        ttk.Label(
            frame,
            text="Only confidence-qualified building candidates are scored. A builder slot is reserved only "
                 "for a candidate with known cost and sufficient confidently observed resources.",
            wraplength=950,
        ).pack(anchor="w", pady=6)
        self.priority_village = tk.StringVar(value="home")
        ttk.Combobox(
            frame, textvariable=self.priority_village, values=("home", "builder_base"),
            state="readonly", width=18,
        ).pack(anchor="w", pady=(0, 8))
        self.priority_village.trace_add("write", lambda *_: self._refresh_priority())
        columns = ("rank", "building", "category", "score", "level", "cost", "status")
        self.priority_table = self._make_table(frame, columns, (
            ("rank", "Rank", 55), ("building", "Building", 180), ("category", "Category", 110),
            ("score", "Score", 75), ("level", "Level → next", 100), ("cost", "Cost", 130),
            ("status", "Queue status", 180),
        ))

    def _build_wall_tab(self):
        frame = self.tab_frames["Wall Maxer"]
        ttk.Label(frame, text="Wall progression", style="Section.TLabel").pack(anchor="w")
        self.wall_label = ttk.Label(frame, text="Wall cost and current levels: Unknown")
        self.wall_label.pack(anchor="w", pady=8)
        ttk.Label(
            frame,
            text="Daily target is editable in Settings. Remaining counts are based on locally stored daily "
                 "progress; total resource budget remains unknown until wall upgrade cost is observed.",
            wraplength=950,
        ).pack(anchor="w")

    def _build_resource_tab(self):
        frame = self.tab_frames["Resource Manager"]
        ttk.Label(frame, text="Separate village budgets and deficits", style="Section.TLabel").pack(anchor="w")
        ttk.Label(
            frame,
            text="Balances are never combined between villages. Missing balances, costs, or loot are shown as unknown.",
            wraplength=950,
        ).pack(anchor="w", pady=6)
        self.resource_summary = tk.Text(frame, height=18, wrap="word", state="disabled")
        self.resource_summary.pack(fill="both", expand=True)

    def _build_missions_tab(self):
        frame = self.tab_frames["Daily Missions"]
        ttk.Label(frame, text="Today's mission progress", style="Section.TLabel").pack(anchor="w")
        self.mission_summary_label = ttk.Label(frame, text="")
        self.mission_summary_label.pack(anchor="w", pady=8)
        controls = ttk.Frame(frame)
        controls.pack(anchor="w", pady=8)
        for label, village, mission in (
            ("Home attack +1", "home", "attacks"),
            ("Builder Base attack +1", "builder_base", "attacks"),
            ("Wall upgrade +1", "home", "wall_upgrades"),
            ("Defense upgrade +1", "home", "defense_upgrades"),
            ("Army upgrade +1", "home", "army_upgrades"),
        ):
            ttk.Button(
                controls, text=label,
                command=lambda v=village, m=mission: self._increment_progress(v, m),
            ).pack(anchor="w", pady=2)
        ttk.Label(
            frame,
            text="Progress is stored locally by date. Buttons record user-confirmed progress; the read-only "
                 "observer does not infer completed attacks or upgrades.",
            wraplength=950,
        ).pack(anchor="w", pady=12)

    def _build_activity_tab(self):
        frame = self.tab_frames["AI Activity Logs"]
        columns = ("time", "village", "event")
        self.activity_table = self._make_table(frame, columns, (
            ("time", "Time (UTC)", 190), ("village", "Village", 130), ("event", "Observation / event", 660),
        ), height=18)

    def _build_settings_tab(self):
        frame = self.tab_frames["Settings"]
        ttk.Label(frame, text="Daily mission defaults", style="Section.TLabel").pack(anchor="w")
        settings_frame = ttk.Frame(frame)
        settings_frame.pack(anchor="w", pady=10)
        self.setting_vars = {}
        for row, (key, title) in enumerate((
            ("wall_upgrades", "Wall upgrades"),
            ("defense_upgrades", "Defense upgrades"),
            ("home_attacks", "Home Village attacks"),
            ("builder_base_attacks", "Builder Base attacks"),
        )):
            ttk.Label(settings_frame, text=title, width=28).grid(row=row, column=0, sticky="w", pady=3)
            variable = tk.StringVar(value=str(getattr(self.mission_settings, key)))
            ttk.Spinbox(settings_frame, from_=0, to=100000, textvariable=variable, width=12).grid(
                row=row, column=1, sticky="w", pady=3
            )
            self.setting_vars[key] = variable
        self.army_enabled = tk.BooleanVar(value=self.mission_settings.army_upgrades_enabled)
        ttk.Checkbutton(
            settings_frame, text="Plan army building upgrades",
            variable=self.army_enabled,
        ).grid(row=4, column=0, columnspan=2, sticky="w", pady=4)
        self.loot_preference_setting = tk.StringVar(value=self.mission_settings.loot_preference)
        ttk.Label(settings_frame, text="Loot preference", width=28).grid(row=5, column=0, sticky="w")
        ttk.Combobox(
            settings_frame, textvariable=self.loot_preference_setting,
            values=("maximum", "balanced", "dark_elixir"), state="readonly", width=16,
        ).grid(row=5, column=1, sticky="w")
        ttk.Button(frame, text="Save mission settings", command=self._save_settings).pack(anchor="w", pady=6)
        ttk.Separator(frame).pack(fill="x", pady=12)
        ttk.Label(frame, text="Primary-screen observation", style="Section.TLabel").pack(anchor="w")
        ttk.Label(
            frame,
            text="Choose which village is currently visible before the live observer saves readings. "
                 "Unassigned is the safe default; the observer never guesses the village.",
            wraplength=950,
        ).pack(anchor="w", pady=5)
        self.screen_village = tk.StringVar(value="unassigned")
        ttk.Combobox(
            frame, textvariable=self.screen_village,
            values=("unassigned", "home", "builder_base"), state="readonly", width=18,
        ).pack(anchor="w")
        ttk.Label(
            frame,
            text="Screen capture and selected local screenshots are processed locally. No screenshots are stored. "
                 "The app never controls the game.",
            wraplength=950,
        ).pack(anchor="w", pady=12)

    @staticmethod
    def _make_table(parent, columns, definitions, height=12):
        table = ttk.Treeview(parent, columns=columns, show="headings", height=height)
        for column, title, width in definitions:
            table.heading(column, text=title)
            table.column(column, width=width, anchor="w")
        table.pack(fill="both", expand=True)
        return table

    def _load_saved_state(self):
        for village in VILLAGES:
            previous = self.store.recent_village_observations(village, 1)
            if previous:
                self.observations[village] = previous[0]
                self._render_village(village, previous[0])
        self._refresh_all()

    def _schedule_observation(self):
        if not self.running:
            self.running = True
            village = self.screen_village.get()
            threading.Thread(target=self._observe, args=(village,), daemon=True).start()
        self.root.after(self.interval_ms, self._schedule_observation)

    def _observe(self, village):
        try:
            frame, width, height = capture_primary_screen()
            self.results.put(("observation", observe_frame(frame, width, height), village, None))
        except Exception as exc:
            self.results.put(("error", None, village, str(exc)))

    def _poll_results(self):
        try:
            result = self.results.get_nowait()
        except queue.Empty:
            pass
        else:
            self._handle_result(result)
        try:
            if self.root.winfo_exists():
                self.root.after(100, self._poll_results)
        except tk.TclError:
            return

    def _choose_village_screenshot(self, village):
        path = filedialog.askopenfilename(
            title=f"Choose {VILLAGES[village]} screenshot",
            filetypes=(("Images", "*.png *.jpg *.jpeg *.bmp"), ("All files", "*.*")),
        )
        if path:
            threading.Thread(target=self._analyze_village_file, args=(path, village), daemon=True).start()

    def _analyze_village_file(self, path, village):
        try:
            import cv2
            image = cv2.imread(path)
            if image is None:
                raise RuntimeError("The selected file is not a readable image.")
            frame = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
            observation = observe_frame(frame, image.shape[1], image.shape[0])
            self.results.put(("observation", observation, village, None))
        except Exception as exc:
            self.results.put(("error", None, village, str(exc)))

    def _choose_loot_screenshot(self):
        path = filedialog.askopenfilename(
            title="Choose opponent base screenshot",
            filetypes=(("Images", "*.png *.jpg *.jpeg *.bmp"), ("All files", "*.*")),
        )
        if path:
            village = self.loot_village.get()
            threading.Thread(target=self._analyze_loot_file, args=(path, village), daemon=True).start()

    def _analyze_loot_file(self, path, village):
        try:
            opportunity = observe_loot_screenshot(path, village)
            analysis = analyze_opportunity(opportunity)
            self.results.put(("loot", analysis, village, None))
        except Exception as exc:
            self.results.put(("error", None, village, str(exc)))

    def _handle_result(self, result):
        if result[0] == "loot":
            self.running = False
            self._render_loot(result[1])
            self.store.log_activity("Opponent screenshot OCR analyzed; no game interaction performed.", result[2])
            self._refresh_activity()
            return
        self._handle_observation_result(result)

    def _handle_observation_result(self, result):
        self.running = False
        kind, payload, village, error = result
        if kind == "error":
            self.status.configure(text=f"Observation unavailable: {error}")
            self._log(error, village if village in VILLAGES else None)
            return
        observation = payload
        try:
            self.store.save(observation)
            if village in VILLAGES:
                encoded = asdict(observation)
                self.store.save_village_observation(village, observation.observed_at, encoded)
                self.observations[village] = encoded
                self._render_village(village, encoded)
                assignment = VILLAGES[village]
            else:
                assignment = "unassigned screen"
            self.store.log_activity(
                f"Screen observed ({assignment}); OCR available: {observation.ocr_available}.",
                village if village in VILLAGES else None,
            )
        except Exception as exc:
            self._log(f"Could not persist observation: {exc}")
        self.status.configure(
            text=f"Last observation: {observation.observed_at}  |  "
                 f"{VILLAGES.get(village, 'Unassigned')}  |  Read-only"
        )
        for note in observation.notes:
            self._log(note, village if village in VILLAGES else None)
        self._refresh_all()

    def _render_village(self, village, data):
        resources = data.get("resources", {})
        for name, label in self.resource_labels[village].items():
            reading = resources.get(name, {})
            value = reading.get("value")
            confidence = reading.get("confidence", 0)
            text = f"{value:,} ({confidence:.0%})" if isinstance(value, (int, float)) else "Unknown"
            label.configure(text=f"{name.replace('_', ' ').title()}: {text}")
        builder = data.get("builders_available", {})
        total = data.get("builders_total", {})
        hall = data.get("town_hall_level", {})
        builder_text = (
            f"{builder.get('value')}/{total.get('value')}"
            if builder.get("value") is not None and total.get("value") is not None
            and builder.get("confidence", 0) >= 0.65 and total.get("confidence", 0) >= 0.65
            else "Unknown"
        )
        hall_text = (
            str(hall["value"])
            if hall.get("value") is not None and hall.get("confidence", 0) >= 0.65
            else "Unknown"
        )
        self.village_details[village].configure(text=f"Builders: {builder_text}  |  Town Hall: {hall_text}")
        notes = data.get("notes", [])
        if not notes:
            notes = ["No OCR confidence warnings."]
        self._set_text(self.village_warnings[village], "\n".join(notes))

    def _render_loot(self, analysis):
        loot = analysis["confidence_adjusted_loot"]
        format_value = lambda key: f"{loot[key]:,}" if loot[key] is not None else "Unknown"
        self.loot_result.configure(
            text=f"Village: {VILLAGES[analysis['village']]}  |  "
                 f"Expected Gold: {format_value('gold')}  |  "
                 f"Elixir: {format_value('elixir')}  |  "
                 f"Dark Elixir: {format_value('dark_elixir')}\n"
                 f"Difficulty: {analysis['difficulty_label']}  |  "
                 f"OCR confidence: {analysis['confidence']:.0%}  |  "
                 f"Efficiency: Unknown"
        )
        warnings = [
            f"Observed values: {analysis['observed_loot']}",
            analysis["recommendation"],
            "Attack strategy: recommend only a loot-focused composition using troops the player has unlocked; "
            "composition/outcome is not estimated without validated opponent and army data.",
            "No matchmaking, attacks, or troop deployment are performed.",
        ]
        self._set_text(self.loot_warnings, "\n".join(warnings))

    def _refresh_all(self):
        home = self.observations["home"]
        builder = self.observations["builder_base"]
        self.overview_label.configure(
            text=f"Home Village: {self._observation_summary(home)}\n"
                 f"Builder Base: {self._observation_summary(builder)}"
        )
        self._render_missions()
        self._refresh_priority()
        self._refresh_resources()
        self._refresh_activity()
        self._refresh_walls()
        next_actions = []
        if not home:
            next_actions.append("Assign Home Village in Settings or analyze a local screenshot.")
        if not builder:
            next_actions.append("Analyze a Builder Base screenshot to populate its separate view.")
        if not self._building_candidates(home) and not self._building_candidates(builder):
            next_actions.append("Upgrade recommendations wait for reliable building identities, levels, costs, and builder readings.")
        self._set_text(self.overview_text, "\n".join(next_actions) or "No pending warnings.")

    @staticmethod
    def _observation_summary(data):
        if not data:
            return "not observed"
        resources = data.get("resources", {})
        known = sum(
            1 for value in resources.values()
            if value.get("value") is not None and value.get("confidence", 0) >= 0.65
        )
        return f"{known}/4 confident resource readings; building data {len(data.get('buildings', []))}"

    @staticmethod
    def _building_candidates(data):
        return data.get("buildings", []) if data else []

    def _refresh_priority(self):
        if not hasattr(self, "priority_table"):
            return
        village = self.priority_village.get()
        data = self.observations.get(village)
        candidates = []
        for item in self._building_candidates(data):
            try:
                candidates.append(UpgradeCandidate(village=village, **item))
            except TypeError:
                continue
        resources = self._readings(data)
        builder_reading = (data or {}).get("builders_available", {})
        builders = builder_reading.get("value") if builder_reading.get("confidence", 0) >= 0.65 else None
        queue = rank_upgrades(candidates, resources, builders)
        for row in self.priority_table.get_children():
            self.priority_table.delete(row)
        for rank, item in enumerate(queue, start=1):
            level = f"{item['current_level'] or '?'} → {item['next_level'] or '?'}"
            cost = (
                f"{item['upgrade_cost']:,} {item['currency']}"
                if item["upgrade_cost"] is not None and item["currency"] else "Unknown"
            )
            self.priority_table.insert(
                "", "end",
                values=(rank, item["name"], item["category"], item["score"], level, cost, item["status"]),
            )

    def _refresh_walls(self):
        progress = self.store.get_daily_progress()
        target = self.mission_settings.wall_upgrades
        self.wall_label.configure(
            text=f"Today: {progress['wall_upgrades']}/{target} wall upgrades  |  "
                 f"Remaining: {max(0, target - progress['wall_upgrades'])}  |  "
                 "Wall level and per-upgrade resource cost: Unknown"
        )

    def _refresh_resources(self):
        lines = []
        for village in VILLAGES:
            data = self.observations[village]
            balances = self._readings(data)
            queue = rank_upgrades(
                [UpgradeCandidate(village=village, **candidate) for candidate in self._building_candidates(data)
                 if self._valid_candidate(candidate)],
                balances,
                None,
            )
            allocation = allocate_resources(village, balances, queue)
            lines.append(f"{VILLAGES[village]} (isolated budget):")
            for name in RESOURCE_NAMES:
                reading = balances.get(name)
                amount = (
                    f"{reading.value:,} ({reading.confidence:.0%})"
                    if reading and reading.value is not None and reading.confidence >= 0.65
                    else "Unknown"
                )
                lines.append(f"  {name.replace('_', ' ').title()}: {amount}")
            if queue:
                for item in allocation["upgrades"]:
                    gap = f"{item['shortfall']:,}" if item["shortfall"] is not None else "Unknown"
                    lines.append(f"  {item['name']} resource shortfall: {gap} {item['currency'] or ''}")
            else:
                lines.append("  Upgrade requirements: Unknown (no qualified candidates).")
            lines.append("")
        self._set_text(self.resource_summary, "\n".join(lines))

    @staticmethod
    def _valid_candidate(candidate):
        allowed = set(UpgradeCandidate.__dataclass_fields__) - {"village"}
        return set(candidate).issubset(allowed)

    @staticmethod
    def _readings(data):
        from .models import Reading
        return {
            name: Reading(**data["resources"].get(name, {}))
            for name in RESOURCE_NAMES
        } if data else {}

    def _render_missions(self):
        progress = self.store.get_daily_progress()
        summary = mission_summary(self.mission_settings, progress)
        self.mission_summary_label.configure(
            text="  |  ".join(
                f"{name.replace('_', ' ').title()}: {item['completed']}/{item['target']} "
                f"(remaining {item['remaining']})"
                for name, item in summary.items()
            ) + f"  |  Army upgrades: {'enabled' if self.mission_settings.army_upgrades_enabled else 'disabled'}"
        )

    def _increment_progress(self, village, mission):
        try:
            progress = self.store.increment_daily_progress(village, mission)
            self.store.log_activity(f"Daily progress confirmed: {village} {mission} +1.", village)
            self._render_missions()
            self._refresh_walls()
            self._refresh_activity()
        except (ValueError, OSError) as exc:
            messagebox.showerror("Could not update progress", str(exc))

    def _save_settings(self):
        try:
            settings = MissionSettings(
                wall_upgrades=int(self.setting_vars["wall_upgrades"].get()),
                defense_upgrades=int(self.setting_vars["defense_upgrades"].get()),
                army_upgrades_enabled=self.army_enabled.get(),
                home_attacks=int(self.setting_vars["home_attacks"].get()),
                builder_base_attacks=int(self.setting_vars["builder_base_attacks"].get()),
                loot_preference=self.loot_preference_setting.get(),
            )
            settings.validate()
            self.store.save_mission_settings(settings)
            self.mission_settings = settings
            self.store.log_activity("Daily mission settings saved.")
            self._refresh_all()
            messagebox.showinfo("Settings saved", "Daily mission settings were saved locally.")
        except (ValueError, OSError) as exc:
            messagebox.showerror("Invalid settings", str(exc))

    def _log(self, message, village=None):
        try:
            self.store.log_activity(str(message), village)
        except Exception:
            pass
        self._refresh_activity()

    def _refresh_activity(self):
        if not hasattr(self, "activity_table"):
            return
        for row in self.activity_table.get_children():
            self.activity_table.delete(row)
        for item in reversed(self.store.recent_activity(200)):
            self.activity_table.insert(
                "", "end",
                values=(item["created_at"], VILLAGES.get(item["village"], "Unassigned"), item["message"]),
            )

    @staticmethod
    def _set_text(widget, text):
        widget.configure(state="normal")
        widget.delete("1.0", "end")
        widget.insert("end", text)
        widget.configure(state="disabled")

    def _close(self):
        self.root.destroy()
