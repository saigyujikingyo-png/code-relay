"""Local setup UI; no account access, provider requests, or installer imports.

The controller rereads configuration before each change and delegates validation,
backups, and secret protection to the existing product boundaries. Tk is imported
only when a window is opened, so the controller also works on headless hosts.
"""
from __future__ import annotations

from copy import deepcopy
import os
from pathlib import Path
import queue
import re
import threading
from typing import Callable
import webbrowser

from . import config, credentials
from .common import RelayError, require
from .providers import ProviderError, validate_provider


ELM_GUIDE_URL = (
    "https://information-services.ed.ac.uk/computing/elm/elm-competence-centre/"
    "examples-of-how-to-use-elm-with-python-and-elm-api-key/"
    "interacting-with-elm-using-python-and-the-elm-api"
)
CAPABILITIES = ("tests", "docs", "boilerplate", "mechanical_edit")
PROTOCOLS = {"OpenAI-compatible": "openai", "Anthropic Messages": "anthropic"}
PROFILE_NUMBERS = (
    "priority", "concurrency", "timeout_seconds", "input_limit_bytes", "output_limit_tokens",
)
SETTING_NUMBERS = ("max_parallel", "max_requests_per_run", "daily_request_limit", "state_limit_mb")


def _whole_number(value: object, name: str) -> int:
    if isinstance(value, str) and re.fullmatch(r"[0-9]+", value):
        # Refuse huge pasted numbers before integer conversion.
        require(len(value) <= 10, "invalid_argument", f"{name} must be a bounded whole number.")
        return int(value)
    require(type(value) is int, "invalid_argument", f"{name} must be a whole number.")
    return value


class SetupController:
    """Local persistence operations, deliberately independent from Tk and APIs."""

    def __init__(self, path: Path | None = None, *, windows: bool | None = None):
        self._path = Path(path) if path is not None else None
        self.windows = os.name == "nt" if windows is None else windows

    @property
    def path(self) -> Path:
        return self._path if self._path is not None else config.config_path()

    def load(self) -> dict:
        return config.load_config(self.path)

    @staticmethod
    def new_profile() -> dict:
        return {
            "id": "", "protocol": "openai", "base_url": "", "model": "", "key_env": "",
            "priority": 100, "concurrency": 2, "timeout_seconds": 45,
            "input_limit_bytes": 65536, "output_limit_tokens": 2048,
            "max_tokens_field": "max_tokens", "capabilities": list(CAPABILITIES),
            "enabled": True, "allow_loopback_http": False,
        }

    def duplicate_profile(self, profile_id: str) -> dict:
        current = self.load()
        source = next((p for p in current["providers"] if p["id"] == profile_id), None)
        require(source is not None, "missing_profile", "The selected model no longer exists. Reload setup.")
        duplicate = deepcopy(source)
        taken = {p["id"] for p in current["providers"]}
        count = 1
        while True:
            suffix = "-copy" if count == 1 else f"-copy-{count}"
            identifier = profile_id[:40 - len(suffix)] + suffix
            if identifier not in taken:
                break
            count += 1
        duplicate.update(id=identifier, model="")
        return duplicate

    def save_profile(self, fields: dict, *, original_id: str | None = None, key: str = "") -> dict:
        require(isinstance(fields, dict), "invalid_profile", "Model profile fields must be an object.")
        raw = deepcopy(fields)
        for name in PROFILE_NUMBERS:
            if name in raw:
                raw[name] = _whole_number(raw[name], name.replace("_", " "))
        if raw.get("key_env") == "":
            raw.pop("key_env")
        profile = validate_provider(raw)
        path = self.path
        current = config.load_config(path)
        profiles = current["providers"]
        identifiers = [p["id"] for p in profiles]
        require(original_id is None or original_id in identifiers, "missing_profile",
                "The model being edited no longer exists. Reload setup.")
        require(profile["id"] not in identifiers or profile["id"] == original_id,
                "duplicate_profile", "That profile ID already exists. Choose a different ID.")
        if original_id is None:
            profiles.append(profile)
        else:
            profiles[identifiers.index(original_id)] = profile
        # Validate the entire proposed configuration before touching a credential.
        current = config.validate_config(current)
        require(isinstance(key, str), "invalid_key", "The API key must be text.")
        if key:
            require(self.windows, "credential_store",
                    "Set the named environment variable on this platform; leave the API key field blank.")
            require(len(key) <= 8192 and all(33 <= ord(char) <= 126 for char in key),
                    "invalid_key", "The API key must contain only printable ASCII without whitespace.")
            try:
                credentials.store_key(profile, key)
            except Exception:
                raise RelayError("credential_store", "The Windows credential could not be saved. Configuration was not changed.") from None
        try:
            config.save_config(current, path)
        except Exception:
            if key:
                raise RelayError(
                    "partial_save", "The API key was stored, but configuration could not be saved. "
                    "Retry saving with a blank API key to preserve it."
                ) from None
            raise
        return deepcopy(profile)

    def remove_profile(self, profile_id: str) -> None:
        path = self.path
        current = config.load_config(path)
        require(any(p["id"] == profile_id for p in current["providers"]), "missing_profile",
                "The selected model no longer exists. Reload setup.")
        current["providers"] = [p for p in current["providers"] if p["id"] != profile_id]
        config.save_config(current, path)

    def add_workspace(self, root: str) -> None:
        path = self.path
        current = config.load_config(path)
        require(isinstance(root, str) and bool(root), "invalid_workspace", "Choose a workspace folder.")
        if root not in current["workspaces"]:
            current["workspaces"].append(root)
        config.save_config(current, path)

    def remove_workspace(self, root: str) -> None:
        path = self.path
        current = config.load_config(path)
        require(root in current["workspaces"], "missing_workspace", "The selected workspace grant no longer exists.")
        current["workspaces"].remove(root)
        config.save_config(current, path)

    def save_settings(self, **changes) -> None:
        require(set(changes) <= {"network_enabled", *SETTING_NUMBERS}, "invalid_settings",
                "Unsupported call setting.")
        for name in SETTING_NUMBERS:
            if name in changes:
                changes[name] = _whole_number(changes[name], name.replace("_", " "))
        path = self.path
        current = config.load_config(path)
        current.update(changes)
        config.save_config(current, path)

    def profile_rows(self, current: dict | None = None) -> list[tuple[str, str, str, str]]:
        rows = []
        for profile in (current if current is not None else self.load())["providers"]:
            if not profile["enabled"]:
                readiness = "Disabled; unverified"
            else:
                try:
                    present = credentials.has_key(profile)
                except Exception:
                    readiness = "Credential unavailable"
                else:
                    readiness = "Key set; unverified" if present else "Needs API key"
            rows.append((profile["id"], profile["model"], profile["base_url"], readiness))
        return rows


def _safe_error(error: Exception) -> str:
    if isinstance(error, (RelayError, ProviderError)):
        return str(error)
    return "The local operation failed. Check access to the displayed configuration folder and try again."


class SetupWindow:
    """A local profile manager with separate source grants and call controls."""

    def __init__(self, root, *, controller: SetupController | None = None,
                 install_callback: Callable[[], dict] | None = None):
        import tkinter as tk
        from tkinter import filedialog, messagebox, ttk

        self.root, self.tk, self.ttk = root, tk, ttk
        self.filedialog, self.messagebox = filedialog, messagebox
        self.controller = controller if controller is not None else SetupController()
        self.install_callback = install_callback
        self.installing = False
        self._install_result: queue.Queue[bool] = queue.Queue(maxsize=1)
        self._loaded_path: Path | None = None
        root.title("Code Relay Setup")
        root.geometry("980x690")
        root.minsize(760, 580)
        root.protocol("WM_DELETE_WINDOW", self.close)
        root.columnconfigure(0, weight=1)
        root.rowconfigure(0, weight=1)
        outer = ttk.Frame(root, padding=16)
        outer.grid(sticky="nsew")
        outer.columnconfigure(0, weight=1)
        outer.rowconfigure(3, weight=1)
        ttk.Label(outer, text="Code Relay", font=("TkDefaultFont", 18, "bold")).grid(sticky="w")
        ttk.Label(outer, text="Connect your own model APIs for bounded coding work. Host accounts are managed by the host.",
                  wraplength=880).grid(row=1, sticky="w", pady=(4, 12))
        path_row = ttk.Frame(outer)
        path_row.grid(row=2, sticky="ew", pady=(0, 12))
        path_row.columnconfigure(1, weight=1)
        ttk.Label(path_row, text="Configuration:").grid(row=0, column=0, padx=(0, 8))
        self.path_var = tk.StringVar(root)
        ttk.Entry(path_row, textvariable=self.path_var, state="readonly").grid(row=0, column=1, sticky="ew")
        ttk.Button(path_row, text="Reload", command=lambda: self.perform(self.refresh)).grid(row=0, column=2, padx=(8, 0))
        tabs = ttk.Notebook(outer)
        tabs.grid(row=3, sticky="nsew")
        self._build_models(tabs)
        self._build_workspaces(tabs)
        self._build_settings(tabs)
        self.status_var = tk.StringVar(root)
        ttk.Label(outer, textvariable=self.status_var, wraplength=880).grid(row=4, sticky="ew", pady=(12, 8))
        footer = ttk.Frame(outer)
        footer.grid(row=5, sticky="ew")
        footer.columnconfigure(1, weight=1)
        if install_callback is not None:
            self.install_button = ttk.Button(footer, text="Install / reconnect in Codex", command=self.install)
            self.install_button.grid(row=0, column=0, sticky="w")
        self.close_button = ttk.Button(footer, text="Close", command=self.close)
        self.close_button.grid(row=0, column=2, sticky="e")
        self.refresh()

    def _build_models(self, tabs):
        ttk = self.ttk
        frame = ttk.Frame(tabs, padding=12)
        tabs.add(frame, text="Models")
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(1, weight=1)
        ttk.Label(frame, text="Each profile has one exact model ID. Duplicate a profile to reuse its endpoint and credential.",
                  wraplength=840).grid(row=0, sticky="w", pady=(0, 10))
        table = ttk.Frame(frame)
        table.grid(row=1, sticky="nsew")
        table.columnconfigure(0, weight=1)
        table.rowconfigure(0, weight=1)
        columns = ("id", "model", "endpoint", "readiness")
        self.models = ttk.Treeview(table, columns=columns, show="headings", selectmode="browse", height=9)
        for name, title, width in zip(columns, ("Profile ID", "Exact model ID", "API endpoint", "Local readiness"),
                                      (140, 210, 260, 175)):
            self.models.heading(name, text=title)
            self.models.column(name, width=width, minwidth=100, stretch=True)
        self.models.grid(row=0, column=0, sticky="nsew")
        scroll = ttk.Scrollbar(table, orient="vertical", command=self.models.yview)
        scroll.grid(row=0, column=1, sticky="ns")
        horizontal = ttk.Scrollbar(table, orient="horizontal", command=self.models.xview)
        horizontal.grid(row=1, column=0, sticky="ew")
        self.models.configure(yscrollcommand=scroll.set, xscrollcommand=horizontal.set)
        self.models.bind("<Double-1>", lambda _event: self.perform(self.edit_model))
        buttons = ttk.Frame(frame)
        buttons.grid(row=2, sticky="w", pady=(10, 8))
        for column, (label, action) in enumerate((
            ("Add model", self.add_model), ("Edit", self.edit_model),
            ("Duplicate for another model", self.duplicate_model), ("Remove", self.remove_model),
        )):
            ttk.Button(buttons, text=label, command=lambda action=action: self.perform(action)).grid(
                row=0, column=column, padx=(0, 6))
        ttk.Label(frame, text="All live models are unverified. Setup checks local configuration only and makes no model API requests.",
                  wraplength=840).grid(row=3, sticky="w", pady=(0, 8))
        ttk.Button(frame, text="University of Edinburgh ELM API guide", command=self.open_elm_guide).grid(row=4, sticky="w")

    def _build_workspaces(self, tabs):
        ttk = self.ttk
        frame = ttk.Frame(tabs, padding=12)
        tabs.add(frame, text="Workspaces")
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(1, weight=1)
        ttk.Label(frame, text="Grant an exact project folder. A task must still select the files it sends from within that folder.",
                  wraplength=840).grid(row=0, sticky="w", pady=(0, 10))
        listing = ttk.Frame(frame)
        listing.grid(row=1, sticky="nsew")
        listing.columnconfigure(0, weight=1)
        listing.rowconfigure(0, weight=1)
        self.workspaces = self.tk.Listbox(listing, exportselection=False, height=8, activestyle="none")
        self.workspaces.grid(row=0, column=0, sticky="nsew")
        scroll = ttk.Scrollbar(listing, orient="vertical", command=self.workspaces.yview)
        scroll.grid(row=0, column=1, sticky="ns")
        horizontal = ttk.Scrollbar(listing, orient="horizontal", command=self.workspaces.xview)
        horizontal.grid(row=1, column=0, sticky="ew")
        self.workspaces.configure(yscrollcommand=scroll.set, xscrollcommand=horizontal.set)
        entry_row = ttk.Frame(frame)
        entry_row.grid(row=2, sticky="ew", pady=10)
        entry_row.columnconfigure(0, weight=1)
        self.workspace_var = self.tk.StringVar(self.root)
        ttk.Entry(entry_row, textvariable=self.workspace_var).grid(row=0, column=0, sticky="ew")
        ttk.Button(entry_row, text="Browse…", command=self.browse_workspace).grid(row=0, column=1, padx=(8, 0))
        ttk.Button(entry_row, text="Add workspace grant", command=lambda: self.perform(self.add_workspace)).grid(
            row=0, column=2, padx=(8, 0))
        ttk.Button(frame, text="Remove selected grant", command=lambda: self.perform(self.remove_workspace)).grid(row=3, sticky="w")

    def _build_settings(self, tabs):
        ttk = self.ttk
        frame = ttk.Frame(tabs, padding=16)
        tabs.add(frame, text="Call settings")
        frame.columnconfigure(1, weight=1)
        self.network_var = self.tk.BooleanVar(self.root, value=False)
        ttk.Checkbutton(frame, text="Allow selected source to be sent to my model APIs", variable=self.network_var).grid(
            row=0, column=0, columnspan=2, sticky="w")
        ttk.Label(frame, text="Enabling and saving this setting authorizes billable or campus-quota API calls when a planned task runs. "
                  "It is off for a new configuration. Saving setup does not make a call.", wraplength=810).grid(
            row=1, column=0, columnspan=2, sticky="w", pady=(6, 18))
        self.setting_vars = {}
        for row, (name, label) in enumerate((
            ("max_parallel", "Total concurrent calls (1–4)"),
            ("max_requests_per_run", "Maximum calls per run (1–64)"),
            ("daily_request_limit", "Daily call limit (1–10,000)"),
            ("state_limit_mb", "Local receipt storage limit, MiB (8–1,024)"),
        ), start=2):
            ttk.Label(frame, text=label).grid(row=row, column=0, sticky="w", pady=6, padx=(0, 20))
            variable = self.tk.StringVar(self.root)
            self.setting_vars[name] = variable
            ttk.Entry(frame, textvariable=variable, width=14).grid(row=row, column=1, sticky="w")
        ttk.Label(frame, text="Call counts are limits, not a price estimate. Provider charges and university allowances vary.",
                  wraplength=810).grid(row=6, column=0, columnspan=2, sticky="w", pady=(14, 10))
        ttk.Button(frame, text="Save call settings", command=lambda: self.perform(self.save_settings)).grid(
            row=7, column=0, columnspan=2, sticky="w")

    def refresh(self, message: str | None = None):
        current = self.controller.load()
        self._loaded_path = self.controller.path
        self.path_var.set(str(self._loaded_path))
        selected = self.models.selection()
        self.models.delete(*self.models.get_children())
        for row in self.controller.profile_rows(current):
            self.models.insert("", "end", iid=row[0], values=row)
        if selected and self.models.exists(selected[0]):
            self.models.selection_set(selected[0])
        self.workspaces.delete(0, "end")
        for root in current["workspaces"]:
            self.workspaces.insert("end", root)
        self.network_var.set(current["network_enabled"])
        for name, variable in self.setting_vars.items():
            variable.set(str(current[name]))
        state = "enabled" if current["network_enabled"] else "off"
        status = (f"{len(current['providers'])} model profiles · {len(current['workspaces'])} workspace grants · "
                  f"API calls {state}. Live models and host acceptance are unverified.")
        self.status_var.set(f"{message} {status}" if message else status)

    def ensure_current_path(self):
        if self._loaded_path != self.controller.path:
            self.refresh()
            raise RelayError("config_changed", "The configuration location changed. Settings were reloaded; repeat the change at the displayed location.")

    def perform(self, action):
        try:
            return action()
        except Exception as error:
            message = _safe_error(error)
            self.status_var.set(message)
            self.messagebox.showerror("Code Relay Setup", message, parent=self.root)
            return None

    def selected_profile(self) -> dict:
        self.ensure_current_path()
        selected = self.models.selection()
        require(bool(selected), "select_profile", "Select a model profile first.")
        profile = next((p for p in self.controller.load()["providers"] if p["id"] == selected[0]), None)
        require(profile is not None, "missing_profile", "The selected model no longer exists. Reload setup.")
        return profile

    def add_model(self):
        self.ensure_current_path()
        return ProfileEditor(self, self.controller.new_profile())

    def edit_model(self):
        profile = self.selected_profile()
        return ProfileEditor(self, profile, original_id=profile["id"])

    def duplicate_model(self):
        profile = self.selected_profile()
        return ProfileEditor(self, self.controller.duplicate_profile(profile["id"]))

    def remove_model(self):
        self.controller.remove_profile(self.selected_profile()["id"])
        self.refresh("Model removed. Its shared credential was retained.")

    def browse_workspace(self):
        chosen = self.filedialog.askdirectory(parent=self.root, title="Choose the exact project folder to grant", mustexist=True)
        if chosen:
            self.workspace_var.set(chosen)

    def add_workspace(self):
        self.ensure_current_path()
        self.controller.add_workspace(self.workspace_var.get())
        self.workspace_var.set("")
        self.refresh("Workspace grant saved.")

    def remove_workspace(self):
        self.ensure_current_path()
        selected = self.workspaces.curselection()
        require(bool(selected), "select_workspace", "Select a workspace grant first.")
        self.controller.remove_workspace(self.workspaces.get(selected[0]))
        self.refresh("Workspace grant removed.")

    def save_settings(self):
        self.ensure_current_path()
        self.controller.save_settings(network_enabled=self.network_var.get(),
                                      **{name: value.get() for name, value in self.setting_vars.items()})
        self.refresh("Call settings saved.")

    def open_elm_guide(self):
        try:
            opened = webbrowser.open(ELM_GUIDE_URL, new=2)
        except Exception:
            opened = False
        self.status_var.set("Opened the official ELM API guide. Use the endpoint and exact model IDs from your authorized account."
                            if opened else "The browser could not open the ELM guide. Try your system browser.")

    def install(self):
        if self.install_callback is None or self.installing:
            return
        self.installing = True
        self.install_button.configure(state="disabled")
        self.close_button.configure(state="disabled")
        self.status_var.set("Connecting Code Relay to Codex…")

        def run():
            try:
                result = self.install_callback()
                okay = isinstance(result, dict) and result.get("ok", True) is not False
            except Exception:
                okay = False
            self._install_result.put(okay)

        try:
            threading.Thread(target=run, name="code-relay-setup", daemon=True).start()
        except Exception:
            self._install_result.put(False)
        self.root.after(100, self._poll_install)

    def _poll_install(self):
        try:
            okay = self._install_result.get_nowait()
        except queue.Empty:
            self.root.after(100, self._poll_install)
            return
        self.installing = False
        self.install_button.configure(state="normal")
        self.close_button.configure(state="normal")
        self.status_var.set("Codex setup completed. Restart Codex to load Code Relay. Host and live-model acceptance remain unverified."
                            if okay else "Codex setup failed. Check local installation permissions and use the installer recovery instructions.")

    def close(self):
        if self.installing:
            self.status_var.set("The local Codex setup is still running. This window can close when it finishes.")
            return
        self.root.destroy()


class ProfileEditor:
    """One explicit save commits the profile and, optionally, its masked key."""

    def __init__(self, parent: SetupWindow, profile: dict, *, original_id: str | None = None, show: bool = True):
        self.parent, self.original_id = parent, original_id
        tk, ttk = parent.tk, parent.ttk
        self.window = tk.Toplevel(parent.root)
        self.window.withdraw()
        self.window.title("Edit model" if original_id else "Add model")
        self.window.resizable(True, False)
        self.window.transient(parent.root)
        self.window.protocol("WM_DELETE_WINDOW", self.close)
        self.fields = {}
        frame = ttk.Frame(self.window, padding=16)
        frame.grid(sticky="nsew")
        self.window.columnconfigure(0, weight=1)
        frame.columnconfigure(1, weight=1)
        ttk.Label(frame, text="Enter the connection details supplied by your API provider.", wraplength=570).grid(
            row=0, column=0, columnspan=2, sticky="w", pady=(0, 10))
        text_fields = (
            ("id", "Profile ID (lowercase name)"), ("protocol", "Protocol"),
            ("base_url", "API base URL"), ("model", "Exact model ID"),
            ("key_env", "Credential label / environment variable"),
        )
        for row, (name, label) in enumerate(text_fields, start=1):
            ttk.Label(frame, text=label).grid(row=row, column=0, sticky="w", padx=(0, 14), pady=4)
            value = profile.get(name, "")
            if name == "protocol":
                value = next(label for label, protocol in PROTOCOLS.items() if protocol == value)
            variable = tk.StringVar(self.window, value=value)
            self.fields[name] = variable
            if name == "protocol":
                widget = ttk.Combobox(frame, textvariable=variable, values=tuple(PROTOCOLS), state="readonly", width=36)
                widget.bind("<<ComboboxSelected>>", lambda _event: self.update_protocol())
            else:
                widget = ttk.Entry(frame, textvariable=variable, width=40)
            widget.grid(row=row, column=1, sticky="ew")
        ttk.Label(frame, text="Leave the credential label blank to generate one. Duplicate a model to share its connection and key.",
                  wraplength=580).grid(row=6, column=0, columnspan=2, sticky="w", pady=(4, 8))
        self.secret_var = tk.StringVar(self.window)
        ttk.Label(frame, text="API key (leave blank to keep)").grid(row=7, column=0, sticky="w", padx=(0, 14))
        self.key_entry = ttk.Entry(frame, textvariable=self.secret_var, show="*", width=40)
        self.key_entry.grid(row=7, column=1, sticky="ew")
        if parent.controller.windows:
            key_help = "A new key is encrypted for this Windows user. An existing environment variable takes precedence."
        else:
            self.key_entry.configure(state="disabled")
            key_help = "Set the named environment variable before starting your host. Key storage is available only on Windows."
        ttk.Label(frame, text=key_help, wraplength=580).grid(row=8, column=0, columnspan=2, sticky="w", pady=(5, 12))
        self.capability_vars = {}
        capabilities = ttk.LabelFrame(frame, text="Allowed work categories", padding=8)
        capabilities.grid(row=9, column=0, columnspan=2, sticky="ew")
        for column, (name, label) in enumerate(zip(CAPABILITIES, ("Tests", "Documentation", "Boilerplate", "Mechanical edits"))):
            variable = tk.BooleanVar(self.window, value=name in profile["capabilities"])
            self.capability_vars[name] = variable
            ttk.Checkbutton(capabilities, text=label, variable=variable).grid(row=0, column=column, padx=(0, 8))
        limits = ttk.Frame(frame)
        limits.grid(row=10, column=0, columnspan=2, sticky="ew", pady=10)
        for index, (name, label) in enumerate((
            ("priority", "Priority, lower first (0–1,000)"), ("concurrency", "Concurrent calls (1–4)"),
            ("input_limit_bytes", "Input limit, UTF-8 bytes"), ("output_limit_tokens", "Output limit, tokens"),
            ("timeout_seconds", "Timeout, seconds (1–120)"),
        )):
            row, column = index // 2, (index % 2) * 2
            ttk.Label(limits, text=label).grid(row=row, column=column, sticky="w", padx=(0, 8), pady=4)
            variable = tk.StringVar(self.window, value=str(profile[name]))
            self.fields[name] = variable
            ttk.Entry(limits, textvariable=variable, width=10).grid(row=row, column=column + 1, sticky="w", padx=(0, 16))
        ttk.Label(frame, text="OpenAI token limit field").grid(row=11, column=0, sticky="w", padx=(0, 14))
        self.fields["max_tokens_field"] = tk.StringVar(self.window, value=profile.get("max_tokens_field", "max_tokens"))
        self.token_field = ttk.Combobox(frame, textvariable=self.fields["max_tokens_field"],
                                        values=("max_tokens", "max_completion_tokens"), state="readonly")
        self.token_field.grid(row=11, column=1, sticky="ew")
        self.enabled_var = tk.BooleanVar(self.window, value=profile["enabled"])
        self.http_var = tk.BooleanVar(self.window, value=profile["allow_loopback_http"])
        ttk.Checkbutton(frame, text="Enable this model profile", variable=self.enabled_var).grid(
            row=12, column=0, columnspan=2, sticky="w", pady=(10, 0))
        ttk.Checkbutton(frame, text="Allow HTTP only for a local test server", variable=self.http_var).grid(
            row=13, column=0, columnspan=2, sticky="w")
        actions = ttk.Frame(frame)
        actions.grid(row=14, column=0, columnspan=2, sticky="e", pady=(14, 0))
        ttk.Button(actions, text="Cancel", command=self.close).grid(row=0, column=0, padx=(0, 8))
        ttk.Button(actions, text="Save model", command=self.save).grid(row=0, column=1)
        self.update_protocol()
        if show:
            self.window.deiconify()
            self.window.grab_set()

    def update_protocol(self):
        state = "readonly" if PROTOCOLS[self.fields["protocol"].get()] == "openai" else "disabled"
        self.token_field.configure(state=state)

    def save(self):
        try:
            self.parent.ensure_current_path()
            fields = {name: variable.get() for name, variable in self.fields.items()}
            fields["protocol"] = PROTOCOLS[fields["protocol"]]
            if fields["protocol"] == "anthropic":
                fields.pop("max_tokens_field")
            fields.update(capabilities=[name for name, variable in self.capability_vars.items() if variable.get()],
                          enabled=self.enabled_var.get(), allow_loopback_http=self.http_var.get())
            saved = self.parent.controller.save_profile(fields, original_id=self.original_id, key=self.secret_var.get())
            self.secret_var.set("")
            self.parent.refresh("Model saved.")
            self.parent.models.selection_set(saved["id"])
        except Exception as error:
            self.parent.messagebox.showerror("Save model", _safe_error(error), parent=self.window)
            return
        self.close()

    def close(self):
        self.secret_var.set("")
        self.window.destroy()


def main(install_callback: Callable[[], dict] | None = None) -> int:
    """Open local setup; an optional host installer is supplied by the launcher."""
    try:
        import tkinter as tk
        from tkinter import messagebox
    except ImportError:
        import sys
        print("Code Relay Setup needs Tk. Use the packaged Windows application or install your platform's Tk runtime.", file=sys.stderr)
        return 1
    try:
        root = tk.Tk()
        root.withdraw()
    except tk.TclError:
        import sys
        print("Code Relay Setup could not open a desktop display.", file=sys.stderr)
        return 1
    try:
        SetupWindow(root, install_callback=install_callback)
    except Exception as error:
        messagebox.showerror("Code Relay Setup", _safe_error(error), parent=root)
        root.destroy()
        return 1
    root.deiconify()
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
