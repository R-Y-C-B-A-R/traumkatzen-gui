import customtkinter as ctk
from tkinter import messagebox, filedialog
from pathlib import Path
import threading
import datetime
import db
import settings as cfg

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")


# ── Date picker widget ────────────────────────────────────────────────────────

class DatePickerFrame(ctk.CTkFrame):
    """Entry + calendar-popup + clear button for a nullable DATE field."""

    def __init__(self, parent, change_callback=None, **kwargs):
        super().__init__(parent, fg_color="transparent", **kwargs)
        self._callback = change_callback
        self._suppress = False

        self._var = ctk.StringVar()
        self._var.trace_add("write", self._on_var_change)

        self._entry = ctk.CTkEntry(self, textvariable=self._var, width=112,
                                   placeholder_text="JJJJ-MM-TT")
        self._entry.pack(side="left", padx=(0, 4))

        self._cal_btn = ctk.CTkButton(self, text="📅", width=34,
                                      command=self._open_calendar)
        self._cal_btn.pack(side="left", padx=(0, 4))

        self._clear_btn = ctk.CTkButton(self, text="✕", width=34,
                                        fg_color="gray40", hover_color="gray30",
                                        command=self._clear)
        self._clear_btn.pack(side="left")

    def _on_var_change(self, *_):
        if not self._suppress and self._callback:
            self._callback()

    def _open_calendar(self):
        from tkcalendar import Calendar
        top = ctk.CTkToplevel(self)
        top.title("Datum wählen")
        top.resizable(False, False)
        top.grab_set()
        current = self._var.get().strip()
        try:
            d = datetime.date.fromisoformat(current)
        except ValueError:
            d = datetime.date.today()
        cal = Calendar(top, selectmode="day",
                       year=d.year, month=d.month, day=d.day,
                       date_pattern="yyyy-mm-dd")
        cal.pack(padx=12, pady=12)

        def confirm():
            self._var.set(cal.get_date())
            top.destroy()

        ctk.CTkButton(top, text="Übernehmen", command=confirm).pack(pady=(0, 12))

    def _clear(self):
        self._var.set("")

    def get(self) -> str:
        return self._var.get().strip()

    def set_value(self, value: str, silent: bool = False):
        self._suppress = silent
        self._var.set(value or "")
        self._suppress = False

    def set_state(self, state: str):
        self._entry.configure(state=state)
        self._cal_btn.configure(state=state)
        self._clear_btn.configure(state=state)


# ── Main application ──────────────────────────────────────────────────────────

class App(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("Traumkatzen")
        self.geometry("1100x700")
        self.minsize(900, 520)

        icon_path = Path(__file__).parent / "cat.ico"
        if icon_path.exists():
            self.iconbitmap(str(icon_path))

        self._prefs = cfg.load()

        # Katzen state
        self._katzen: list[dict] = []
        self._selected_id: int | None = None
        self._dirty = False

        # Gruppen state
        self._gruppen: list[dict] = []
        self._grp_id: int | None = None
        self._grp_members: list[dict] = []
        self._grp_dirty = False
        self._all_katzen_simple: list[dict] = []

        self._build_ui()
        self._load_list()
        self._load_gruppen()
        threading.Thread(target=self._fetch_all_katzen_simple,
                         daemon=True).start()

    # ── Top-level layout ──────────────────────────────────────────────────────

    def _build_ui(self):
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)

        tabs = ctk.CTkTabview(self)
        tabs.grid(row=0, column=0, sticky="nsew", padx=6, pady=6)

        tabs.add("🐱  Katzen")
        tabs.add("👥  Gruppen")
        tabs.add("💾  Backup")

        self._build_katzen_tab(tabs.tab("🐱  Katzen"))
        self._build_gruppen_tab(tabs.tab("👥  Gruppen"))
        self._build_backup_tab(tabs.tab("💾  Backup"))

    # ════════════════════════════════════════════════════════════════════════
    # KATZEN TAB
    # ════════════════════════════════════════════════════════════════════════

    def _build_katzen_tab(self, tab):
        tab.grid_columnconfigure(1, weight=1)
        tab.grid_rowconfigure(0, weight=1)

        # ── Sidebar ──
        sidebar = ctk.CTkFrame(tab, width=220, corner_radius=8)
        sidebar.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        sidebar.grid_columnconfigure(0, weight=1)
        sidebar.grid_rowconfigure(3, weight=1)

        # Filter
        filter_frame = ctk.CTkFrame(sidebar, fg_color=("gray85", "gray20"),
                                    corner_radius=8)
        filter_frame.grid(row=0, column=0, padx=10, pady=(10, 6), sticky="ew")
        filter_frame.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(filter_frame, text="Filter",
                     font=ctk.CTkFont(size=12, weight="bold")).grid(
            row=0, column=0, padx=10, pady=(8, 4), sticky="w")

        self._chk_aktiv     = ctk.BooleanVar(value=self._prefs["filter_aktiv"])
        self._chk_pausiert  = ctk.BooleanVar(value=self._prefs["filter_pausiert"])
        self._chk_vermittelt = ctk.BooleanVar(value=self._prefs["filter_vermittelt"])

        for i, (var, label) in enumerate([
            (self._chk_aktiv,      "Aktiv"),
            (self._chk_pausiert,   "Pausiert ⏸"),
            (self._chk_vermittelt, "Vermittelt ✓"),
        ], start=1):
            ctk.CTkCheckBox(filter_frame, text=label, variable=var,
                            command=self._on_filter_change).grid(
                row=i, column=0, padx=12, pady=3, sticky="w")

        ctk.CTkFrame(filter_frame, height=6, fg_color="transparent").grid(row=4, column=0)

        # Search
        self._search_var = ctk.StringVar()
        self._search_var.trace_add("write", lambda *_: self._on_search())
        ctk.CTkEntry(sidebar, placeholder_text="Suchen…",
                     textvariable=self._search_var).grid(
            row=1, column=0, padx=10, pady=(0, 6), sticky="ew")

        # Cat list
        self._listbox = ctk.CTkScrollableFrame(sidebar)
        self._listbox.grid(row=3, column=0, padx=4, sticky="nsew")
        self._listbox.grid_columnconfigure(0, weight=1)

        self._status_label = ctk.CTkLabel(sidebar, text="",
                                          font=ctk.CTkFont(size=11))
        self._status_label.grid(row=4, column=0, padx=12, pady=6)

        # ── Detail panel ──
        detail = ctk.CTkScrollableFrame(tab)
        detail.grid(row=0, column=1, sticky="nsew")
        detail.grid_columnconfigure(1, weight=1)
        self._build_katze_form(detail)

    def _build_katze_form(self, parent):
        self._fields: dict = {}

        plain_fields = [
            ("name",                  "Name"),
            ("url",                   "URL"),
            ("krankheiten_handicaps", "Krankheiten / Handicaps"),
        ]
        date_fields = [
            ("vermittelt", "Vermittelt"),
            ("pausiert",   "Pausiert"),
        ]

        row = 0
        for key, label in plain_fields:
            ctk.CTkLabel(parent, text=label, anchor="w").grid(
                row=row, column=0, padx=(8, 12), pady=6, sticky="w")
            entry = ctk.CTkEntry(parent)
            entry.grid(row=row, column=1, padx=(0, 8), pady=6, sticky="ew")
            entry.bind("<KeyRelease>", self._on_field_change)
            self._fields[key] = entry
            row += 1

        for key, label in date_fields:
            ctk.CTkLabel(parent, text=label, anchor="w").grid(
                row=row, column=0, padx=(8, 12), pady=6, sticky="w")
            picker = DatePickerFrame(parent, change_callback=self._on_field_change)
            picker.grid(row=row, column=1, padx=(0, 8), pady=6, sticky="w")
            self._fields[key] = picker
            row += 1

        ctk.CTkLabel(parent, text="Patenschaft Text", anchor="nw").grid(
            row=row, column=0, padx=(8, 12), pady=6, sticky="nw")
        textbox = ctk.CTkTextbox(parent, height=180, wrap="word")
        textbox.grid(row=row, column=1, padx=(0, 8), pady=6, sticky="ew")
        textbox.bind("<KeyRelease>", self._on_field_change)
        self._fields["patenschaft_text"] = textbox
        row += 1

        btn_frame = ctk.CTkFrame(parent, fg_color="transparent")
        btn_frame.grid(row=row, column=0, columnspan=2, pady=(12, 4), sticky="e")

        self._save_btn = ctk.CTkButton(btn_frame, text="Speichern",
                                       command=self._save, state="disabled", width=120)
        self._save_btn.pack(side="right", padx=(8, 0))

        self._discard_btn = ctk.CTkButton(btn_frame, text="Verwerfen",
                                          command=self._discard, state="disabled",
                                          width=120, fg_color="gray40",
                                          hover_color="gray30")
        self._discard_btn.pack(side="right")

        self._set_form_state("disabled")

    # ── Katzen: data ──────────────────────────────────────────────────────────

    def _load_list(self, search: str = ""):
        self._status_label.configure(text="Lade…")
        threading.Thread(target=self._fetch_list, args=(search,), daemon=True).start()

    def _fetch_list(self, search: str):
        try:
            katzen = db.fetch_all_katzen(
                search=search,
                show_aktiv=self._chk_aktiv.get(),
                show_pausiert=self._chk_pausiert.get(),
                show_vermittelt=self._chk_vermittelt.get(),
            )
        except Exception as e:
            self.after(0, lambda: messagebox.showerror("Datenbankfehler", str(e)))
            self.after(0, lambda: self._status_label.configure(text="Fehler"))
            return
        self.after(0, lambda: self._populate_list(katzen))

    def _populate_list(self, katzen: list[dict]):
        self._katzen = katzen
        for w in self._listbox.winfo_children():
            w.destroy()
        for cat in katzen:
            label = cat["name"] or f"#{cat['id']}"
            if cat["vermittelt"]:
                label += " ✓"
            elif cat["pausiert"]:
                label += " ⏸"
            btn = ctk.CTkButton(
                self._listbox, text=label, anchor="w",
                fg_color="transparent",
                hover_color=("gray80", "gray30"),
                text_color=("gray10", "gray90"),
                command=lambda cid=cat["id"]: self._select(cid),
            )
            btn.grid(sticky="ew", padx=2, pady=1)
        self._status_label.configure(text=f"{len(katzen)} Katzen")

    def _on_search(self):
        self._load_list(self._search_var.get().strip())

    def _on_filter_change(self):
        self._prefs.update({
            "filter_aktiv":      self._chk_aktiv.get(),
            "filter_pausiert":   self._chk_pausiert.get(),
            "filter_vermittelt": self._chk_vermittelt.get(),
        })
        cfg.save(self._prefs)
        self._load_list(self._search_var.get().strip())

    # ── Katzen: selection & form ──────────────────────────────────────────────

    def _select(self, katze_id: int):
        if self._dirty:
            if not messagebox.askyesno("Ungespeicherte Änderungen",
                                       "Änderungen verwerfen?"):
                return
        self._selected_id = katze_id
        threading.Thread(target=self._fetch_detail, args=(katze_id,), daemon=True).start()

    def _fetch_detail(self, katze_id: int):
        try:
            katze = db.fetch_katze(katze_id)
        except Exception as e:
            self.after(0, lambda: messagebox.showerror("Datenbankfehler", str(e)))
            return
        self.after(0, lambda: self._fill_form(katze))

    def _fill_form(self, katze: dict):
        self._set_form_state("normal")
        self._dirty = False
        for key, widget in self._fields.items():
            raw = katze.get(key)
            value = raw.isoformat() if hasattr(raw, "isoformat") else (str(raw) if raw is not None else "")
            if isinstance(widget, DatePickerFrame):
                widget.set_value(value, silent=True)
            elif isinstance(widget, ctk.CTkTextbox):
                widget.delete("1.0", "end")
                widget.insert("1.0", value)
            else:
                widget.delete(0, "end")
                widget.insert(0, value)
        self._save_btn.configure(state="disabled")
        self._discard_btn.configure(state="disabled")

    def _on_field_change(self, _event=None):
        if not self._dirty:
            self._dirty = True
            self._save_btn.configure(state="normal")
            self._discard_btn.configure(state="normal")

    def _set_form_state(self, state: str):
        for widget in self._fields.values():
            if isinstance(widget, DatePickerFrame):
                widget.set_state(state)
            else:
                widget.configure(state=state)

    def _collect_form(self) -> dict:
        data = {}
        for key, widget in self._fields.items():
            if isinstance(widget, DatePickerFrame):
                data[key] = widget.get()
            elif isinstance(widget, ctk.CTkTextbox):
                data[key] = widget.get("1.0", "end").strip()
            else:
                data[key] = widget.get().strip()
        return data

    def _save(self):
        if self._selected_id is None:
            return
        data = self._collect_form()
        for key in ("vermittelt", "pausiert"):
            val = data.get(key, "")
            if val:
                try:
                    datetime.date.fromisoformat(val)
                except ValueError:
                    messagebox.showerror("Ungültiges Datum",
                                         f"'{val}' ist kein gültiges Datum (JJJJ-MM-TT).")
                    return
        try:
            db.save_katze(self._selected_id, data)
        except Exception as e:
            messagebox.showerror("Speicherfehler", str(e))
            return
        self._dirty = False
        self._save_btn.configure(state="disabled")
        self._discard_btn.configure(state="disabled")
        self._load_list(self._search_var.get().strip())

    def _discard(self):
        if self._selected_id is not None:
            threading.Thread(target=self._fetch_detail,
                             args=(self._selected_id,), daemon=True).start()

    # ════════════════════════════════════════════════════════════════════════
    # GRUPPEN TAB
    # ════════════════════════════════════════════════════════════════════════

    def _build_gruppen_tab(self, tab):
        tab.grid_columnconfigure(1, weight=1)
        tab.grid_rowconfigure(0, weight=1)

        # ── Sidebar ──
        sidebar = ctk.CTkFrame(tab, width=220, corner_radius=8)
        sidebar.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        sidebar.grid_columnconfigure(0, weight=1)
        sidebar.grid_rowconfigure(1, weight=1)

        ctk.CTkButton(sidebar, text="+ Neue Gruppe",
                      command=self._neue_gruppe).grid(
            row=0, column=0, padx=10, pady=10, sticky="ew")

        self._grp_listbox = ctk.CTkScrollableFrame(sidebar)
        self._grp_listbox.grid(row=1, column=0, padx=4, pady=(0, 4), sticky="nsew")
        self._grp_listbox.grid_columnconfigure(0, weight=1)

        self._grp_status = ctk.CTkLabel(sidebar, text="",
                                        font=ctk.CTkFont(size=11))
        self._grp_status.grid(row=2, column=0, padx=12, pady=6)

        # ── Detail panel ──
        detail = ctk.CTkScrollableFrame(tab)
        detail.grid(row=0, column=1, sticky="nsew")
        detail.grid_columnconfigure(1, weight=1)
        self._build_grp_form(detail)

    def _build_grp_form(self, parent):
        # Name
        ctk.CTkLabel(parent, text="Gruppenname", anchor="w").grid(
            row=0, column=0, padx=(8, 12), pady=8, sticky="w")
        self._grp_name_entry = ctk.CTkEntry(parent,
                                            placeholder_text="Name der Gruppe")
        self._grp_name_entry.grid(row=0, column=1, padx=(0, 8), pady=8, sticky="ew")
        self._grp_name_entry.bind("<KeyRelease>", self._on_grp_change)

        # Members list
        ctk.CTkLabel(parent, text="Mitglieder", anchor="nw").grid(
            row=1, column=0, padx=(8, 12), pady=(8, 4), sticky="nw")
        self._grp_members_frame = ctk.CTkFrame(
            parent, fg_color=("gray85", "gray20"), corner_radius=8)
        self._grp_members_frame.grid(row=1, column=1, padx=(0, 8),
                                     pady=(8, 4), sticky="ew")
        self._grp_members_frame.grid_columnconfigure(0, weight=1)

        # Add member row
        ctk.CTkLabel(parent, text="Hinzufügen", anchor="w").grid(
            row=2, column=0, padx=(8, 12), pady=4, sticky="w")
        add_frame = ctk.CTkFrame(parent, fg_color="transparent")
        add_frame.grid(row=2, column=1, padx=(0, 8), pady=4, sticky="ew")
        add_frame.grid_columnconfigure(0, weight=1)

        self._grp_add_combo = ctk.CTkComboBox(add_frame, values=[],
                                              state="readonly")
        self._grp_add_combo.grid(row=0, column=0, padx=(0, 8), sticky="ew")
        self._grp_add_btn = ctk.CTkButton(add_frame, text="Hinzufügen",
                                          width=120,
                                          command=self._add_grp_member)
        self._grp_add_btn.grid(row=0, column=1)

        # Action buttons
        btn_frame = ctk.CTkFrame(parent, fg_color="transparent")
        btn_frame.grid(row=3, column=0, columnspan=2,
                       pady=(16, 4), padx=8, sticky="ew")

        self._grp_delete_btn = ctk.CTkButton(
            btn_frame, text="Gruppe löschen", width=140,
            fg_color="#8B0000", hover_color="#5a0000",
            command=self._delete_gruppe)
        self._grp_delete_btn.pack(side="left")

        self._grp_save_btn = ctk.CTkButton(
            btn_frame, text="Speichern", width=120,
            command=self._save_gruppe, state="disabled")
        self._grp_save_btn.pack(side="right", padx=(8, 0))

        self._grp_discard_btn = ctk.CTkButton(
            btn_frame, text="Verwerfen", width=120,
            fg_color="gray40", hover_color="gray30",
            command=self._discard_gruppe, state="disabled")
        self._grp_discard_btn.pack(side="right")

        self._set_grp_form_state("disabled")

    # ── Gruppen: data ─────────────────────────────────────────────────────────

    def _load_gruppen(self):
        self._grp_status.configure(text="Lade…")
        threading.Thread(target=self._fetch_gruppen, daemon=True).start()

    def _fetch_gruppen(self):
        try:
            gruppen = db.fetch_all_gruppen()
        except Exception as e:
            self.after(0, lambda: messagebox.showerror("Datenbankfehler", str(e)))
            return
        self.after(0, lambda: self._populate_gruppen(gruppen))

    def _populate_gruppen(self, gruppen: list[dict]):
        self._gruppen = gruppen
        for w in self._grp_listbox.winfo_children():
            w.destroy()
        for g in gruppen:
            label = f"{g['name']}  ({g['anzahl']})"
            btn = ctk.CTkButton(
                self._grp_listbox, text=label, anchor="w",
                fg_color="transparent",
                hover_color=("gray80", "gray30"),
                text_color=("gray10", "gray90"),
                command=lambda gid=g["id"]: self._select_gruppe(gid),
            )
            btn.grid(sticky="ew", padx=2, pady=1)
        self._grp_status.configure(text=f"{len(gruppen)} Gruppen")

    def _fetch_all_katzen_simple(self):
        try:
            katzen = db.fetch_all_katzen_simple()
        except Exception:
            katzen = []
        self.after(0, lambda: setattr(self, "_all_katzen_simple", katzen))

    # ── Gruppen: selection & form ─────────────────────────────────────────────

    def _select_gruppe(self, gruppen_id: int):
        if self._grp_dirty:
            if not messagebox.askyesno("Ungespeicherte Änderungen",
                                       "Änderungen verwerfen?"):
                return
        self._grp_id = gruppen_id
        threading.Thread(target=self._fetch_gruppe_detail,
                         args=(gruppen_id,), daemon=True).start()

    def _fetch_gruppe_detail(self, gruppen_id: int):
        try:
            mitglieder = db.fetch_gruppe_mitglieder(gruppen_id)
            gruppe = next(g for g in self._gruppen if g["id"] == gruppen_id)
        except Exception as e:
            self.after(0, lambda: messagebox.showerror("Datenbankfehler", str(e)))
            return
        self.after(0, lambda: self._fill_grp_form(gruppe["name"], mitglieder))

    def _fill_grp_form(self, name: str, mitglieder: list[dict]):
        self._set_grp_form_state("normal")
        self._grp_dirty = False
        self._grp_members = list(mitglieder)

        self._grp_name_entry.delete(0, "end")
        self._grp_name_entry.insert(0, name)

        self._refresh_members_display()
        self._refresh_add_dropdown()
        self._grp_save_btn.configure(state="disabled")
        self._grp_discard_btn.configure(state="disabled")
        self._grp_delete_btn.configure(state="normal")

    def _neue_gruppe(self):
        if self._grp_dirty:
            if not messagebox.askyesno("Ungespeicherte Änderungen",
                                       "Änderungen verwerfen?"):
                return
        self._grp_id = None
        self._grp_members = []
        self._grp_dirty = False
        self._set_grp_form_state("normal")
        self._grp_name_entry.delete(0, "end")
        self._grp_name_entry.insert(0, "Neue Gruppe")
        self._grp_name_entry.focus()
        self._grp_name_entry.select_range(0, "end")
        self._refresh_members_display()
        self._refresh_add_dropdown()
        self._grp_save_btn.configure(state="normal")
        self._grp_discard_btn.configure(state="normal")
        self._grp_delete_btn.configure(state="disabled")
        self._grp_dirty = True

    def _on_grp_change(self, _event=None):
        if not self._grp_dirty:
            self._grp_dirty = True
            self._grp_save_btn.configure(state="normal")
            self._grp_discard_btn.configure(state="normal")

    def _set_grp_form_state(self, state: str):
        self._grp_name_entry.configure(state=state)
        self._grp_add_combo.configure(state="readonly" if state == "normal" else state)
        self._grp_add_btn.configure(state=state)
        self._grp_save_btn.configure(state=state if state == "disabled" else "disabled")
        self._grp_discard_btn.configure(state=state if state == "disabled" else "disabled")
        self._grp_delete_btn.configure(state=state)

    def _refresh_members_display(self):
        for w in self._grp_members_frame.winfo_children():
            w.destroy()
        self._grp_members_frame.grid_columnconfigure(0, weight=1)

        if not self._grp_members:
            ctk.CTkLabel(self._grp_members_frame, text="Keine Mitglieder",
                         text_color="gray50").grid(
                row=0, column=0, padx=10, pady=8, sticky="w")
            return

        for i, member in enumerate(self._grp_members):
            row_f = ctk.CTkFrame(self._grp_members_frame, fg_color="transparent")
            row_f.grid(row=i, column=0, sticky="ew", padx=6, pady=2)
            row_f.grid_columnconfigure(0, weight=1)
            ctk.CTkLabel(row_f, text=member["name"], anchor="w").grid(
                row=0, column=0, sticky="w")
            ctk.CTkButton(
                row_f, text="✕", width=28,
                fg_color="gray40", hover_color="gray30",
                command=lambda m=member: self._remove_grp_member(m),
            ).grid(row=0, column=1, padx=(8, 0))

    def _refresh_add_dropdown(self):
        member_ids = {m["id"] for m in self._grp_members}
        available = [k for k in self._all_katzen_simple
                     if k["id"] not in member_ids]
        self._grp_add_map = {k["name"]: k["id"] for k in available}
        values = list(self._grp_add_map.keys())
        self._grp_add_combo.configure(values=values)
        self._grp_add_combo.set(values[0] if values else "")

    def _add_grp_member(self):
        name = self._grp_add_combo.get()
        if not name or name not in self._grp_add_map:
            return
        katze_id = self._grp_add_map[name]
        self._grp_members.append({"id": katze_id, "name": name})
        self._grp_members.sort(key=lambda m: m["name"])
        self._on_grp_change()
        self._refresh_members_display()
        self._refresh_add_dropdown()

    def _remove_grp_member(self, member: dict):
        self._grp_members = [m for m in self._grp_members
                             if m["id"] != member["id"]]
        self._on_grp_change()
        self._refresh_members_display()
        self._refresh_add_dropdown()

    # ── Gruppen: save / discard / delete ─────────────────────────────────────

    def _save_gruppe(self):
        name = self._grp_name_entry.get().strip()
        if not name:
            messagebox.showerror("Fehler", "Bitte einen Gruppennamen eingeben.")
            return
        katzen_ids = [m["id"] for m in self._grp_members]
        try:
            if self._grp_id is None:
                self._grp_id = db.create_gruppe(name)
                db.save_gruppe(self._grp_id, name, katzen_ids)
            else:
                db.save_gruppe(self._grp_id, name, katzen_ids)
        except Exception as e:
            messagebox.showerror("Speicherfehler", str(e))
            return
        self._grp_dirty = False
        self._grp_save_btn.configure(state="disabled")
        self._grp_discard_btn.configure(state="disabled")
        self._grp_delete_btn.configure(state="normal")
        self._load_gruppen()

    def _discard_gruppe(self):
        if self._grp_id is not None:
            self._select_gruppe(self._grp_id)
        else:
            self._set_grp_form_state("disabled")
            self._grp_dirty = False

    def _delete_gruppe(self):
        if self._grp_id is None:
            return
        name = self._grp_name_entry.get().strip() or f"#{self._grp_id}"
        if not messagebox.askyesno("Gruppe löschen",
                                   f'Gruppe "{name}" wirklich loeschen?'):
            return
        try:
            db.delete_gruppe(self._grp_id)
        except Exception as e:
            messagebox.showerror("Fehler", str(e))
            return
        self._grp_id = None
        self._grp_members = []
        self._grp_dirty = False
        self._set_grp_form_state("disabled")
        self._grp_name_entry.delete(0, "end")
        self._refresh_members_display()
        self._load_gruppen()


    # ════════════════════════════════════════════════════════════════════════
    # BACKUP TAB
    # ════════════════════════════════════════════════════════════════════════

    def _build_backup_tab(self, tab):
        tab.grid_columnconfigure(0, weight=1)
        tab.grid_rowconfigure(2, weight=1)

        # ── Backup-Verzeichnis ──
        dir_frame = ctk.CTkFrame(tab, corner_radius=8)
        dir_frame.grid(row=0, column=0, sticky="ew", padx=12, pady=(12, 6))
        dir_frame.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(dir_frame, text="Backup-Verzeichnis",
                     font=ctk.CTkFont(weight="bold")).grid(
            row=0, column=0, padx=(12, 8), pady=10, sticky="w")

        self._backup_dir_var = ctk.StringVar(value=self._prefs.get("backup_dir", ""))
        dir_entry = ctk.CTkEntry(dir_frame, textvariable=self._backup_dir_var,
                                 state="readonly")
        dir_entry.grid(row=0, column=1, padx=(0, 8), pady=10, sticky="ew")

        ctk.CTkButton(dir_frame, text="Ordner wählen", width=130,
                      command=self._choose_backup_dir).grid(
            row=0, column=2, padx=(0, 12), pady=10)

        # ── Backup erstellen ──
        action_frame = ctk.CTkFrame(tab, corner_radius=8)
        action_frame.grid(row=1, column=0, sticky="ew", padx=12, pady=6)
        action_frame.grid_columnconfigure(1, weight=1)

        self._backup_btn = ctk.CTkButton(action_frame, text="Backup erstellen",
                                         width=160, command=self._create_backup)
        self._backup_btn.grid(row=0, column=0, padx=12, pady=12)

        self._backup_status = ctk.CTkLabel(action_frame, text="",
                                           font=ctk.CTkFont(size=12))
        self._backup_status.grid(row=0, column=1, padx=8, pady=12, sticky="w")

        # ── Backup-Liste ──
        list_frame = ctk.CTkFrame(tab, corner_radius=8)
        list_frame.grid(row=2, column=0, sticky="nsew", padx=12, pady=(6, 12))
        list_frame.grid_columnconfigure(0, weight=1)
        list_frame.grid_rowconfigure(1, weight=1)

        ctk.CTkLabel(list_frame, text="Vorhandene Backups",
                     font=ctk.CTkFont(weight="bold")).grid(
            row=0, column=0, padx=12, pady=(10, 4), sticky="w")

        self._backup_list_frame = ctk.CTkScrollableFrame(list_frame)
        self._backup_list_frame.grid(row=1, column=0, sticky="nsew",
                                     padx=8, pady=(0, 8))
        self._backup_list_frame.grid_columnconfigure(0, weight=1)

        self._refresh_backup_list()

    # ── Backup: actions ───────────────────────────────────────────────────────

    def _choose_backup_dir(self):
        current = self._backup_dir_var.get()
        chosen = filedialog.askdirectory(
            title="Backup-Verzeichnis wählen",
            initialdir=current if Path(current).exists() else str(Path.home()),
        )
        if chosen:
            self._backup_dir_var.set(chosen)
            self._prefs["backup_dir"] = chosen
            cfg.save(self._prefs)
            self._refresh_backup_list()

    def _create_backup(self):
        backup_dir = Path(self._backup_dir_var.get())
        if not backup_dir.exists():
            try:
                backup_dir.mkdir(parents=True)
            except Exception as e:
                messagebox.showerror("Fehler", f"Verzeichnis konnte nicht erstellt werden:\n{e}")
                return

        ts = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        filepath = backup_dir / f"traumkatzen_{ts}.sql"

        self._backup_btn.configure(state="disabled")
        self._backup_status.configure(text="Erstelle Backup…")

        def run():
            try:
                total = db.backup_database(str(filepath))
                self.after(0, lambda: self._on_backup_done(filepath, total))
            except Exception as e:
                self.after(0, lambda: self._on_backup_error(str(e)))

        threading.Thread(target=run, daemon=True).start()

    def _on_backup_done(self, filepath: Path, total: int):
        self._backup_btn.configure(state="normal")
        self._backup_status.configure(
            text=f"Gespeichert: {filepath.name}  ({total} Zeilen)")
        self._refresh_backup_list()

    def _on_backup_error(self, error: str):
        self._backup_btn.configure(state="normal")
        self._backup_status.configure(text="Fehler!")
        messagebox.showerror("Backup fehlgeschlagen", error)

    def _refresh_backup_list(self):
        for w in self._backup_list_frame.winfo_children():
            w.destroy()

        backup_dir = Path(self._backup_dir_var.get())
        if not backup_dir.exists():
            ctk.CTkLabel(self._backup_list_frame,
                         text="Verzeichnis existiert noch nicht.",
                         text_color="gray50").grid(row=0, column=0,
                                                    padx=10, pady=8, sticky="w")
            return

        files = sorted(backup_dir.glob("traumkatzen_*.sql"), reverse=True)
        if not files:
            ctk.CTkLabel(self._backup_list_frame, text="Keine Backups vorhanden.",
                         text_color="gray50").grid(row=0, column=0,
                                                    padx=10, pady=8, sticky="w")
            return

        for i, f in enumerate(files):
            size_kb = f.stat().st_size // 1024
            row_f = ctk.CTkFrame(self._backup_list_frame,
                                 fg_color=("gray85", "gray20"), corner_radius=6)
            row_f.grid(row=i, column=0, sticky="ew", padx=4, pady=3)
            row_f.grid_columnconfigure(0, weight=1)

            ctk.CTkLabel(row_f, text=f.name, anchor="w",
                         font=ctk.CTkFont(family="Courier")).grid(
                row=0, column=0, padx=10, pady=6, sticky="w")
            ctk.CTkLabel(row_f, text=f"{size_kb} KB",
                         text_color="gray60", width=70, anchor="e").grid(
                row=0, column=1, padx=4)
            ctk.CTkButton(row_f, text="Wiederherstellen", width=150,
                          fg_color="#8B0000", hover_color="#5a0000",
                          command=lambda p=f: self._restore_backup(p)).grid(
                row=0, column=2, padx=(4, 8), pady=6)


    def _restore_backup(self, filepath: Path):
        if not messagebox.askyesno(
            "Wiederherstellen",
            f"Backup '{filepath.name}' wiederherstellen?\n\n"
            "ACHTUNG: Alle aktuellen Daten werden überschrieben!",
        ):
            return

        self._backup_status.configure(text="Stelle wieder her…")

        def run():
            try:
                count = db.restore_database(str(filepath))
                self.after(0, lambda: self._on_restore_done(filepath.name, count))
            except Exception as e:
                self.after(0, lambda: self._on_restore_error(str(e)))

        threading.Thread(target=run, daemon=True).start()

    def _on_restore_done(self, filename: str, count: int):
        self._backup_status.configure(text=f"Wiederhergestellt: {filename}")
        messagebox.showinfo("Fertig",
                            f"Backup erfolgreich wiederhergestellt.\n({count} Befehle ausgefuehrt)")
        self._load_list()
        self._load_gruppen()

    def _on_restore_error(self, error: str):
        self._backup_status.configure(text="Fehler beim Wiederherstellen!")
        messagebox.showerror("Fehler", error)


if __name__ == "__main__":
    app = App()
    app.mainloop()
