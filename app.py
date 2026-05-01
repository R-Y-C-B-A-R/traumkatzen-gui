import customtkinter as ctk
from tkinter import messagebox
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

    # Public API matching CTkEntry / CTkTextbox usage in the form

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
        self.minsize(800, 500)

        self._prefs = cfg.load()
        self._katzen: list[dict] = []
        self._selected_id: int | None = None
        self._dirty = False

        self._build_ui()
        self._load_list()

    # ── Layout ────────────────────────────────────────────────────────────────

    def _build_ui(self):
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        sidebar = ctk.CTkFrame(self, width=220, corner_radius=0)
        sidebar.grid(row=0, column=0, sticky="nsew")
        sidebar.grid_columnconfigure(0, weight=1)
        sidebar.grid_rowconfigure(3, weight=1)

        # Title
        ctk.CTkLabel(sidebar, text="Traumkatzen",
                     font=ctk.CTkFont(size=18, weight="bold")).grid(
            row=0, column=0, padx=16, pady=(16, 8), sticky="w")

        # Filter checkboxes
        filter_frame = ctk.CTkFrame(sidebar, fg_color=("gray90", "gray20"),
                                    corner_radius=8)
        filter_frame.grid(row=1, column=0, padx=10, pady=(0, 8), sticky="ew")
        filter_frame.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(filter_frame, text="Filter",
                     font=ctk.CTkFont(size=12, weight="bold")).grid(
            row=0, column=0, padx=10, pady=(8, 4), sticky="w")

        self._chk_aktiv = ctk.BooleanVar(value=self._prefs["filter_aktiv"])
        self._chk_pausiert = ctk.BooleanVar(value=self._prefs["filter_pausiert"])
        self._chk_vermittelt = ctk.BooleanVar(value=self._prefs["filter_vermittelt"])

        for row, (var, label) in enumerate([
            (self._chk_aktiv,     "Aktiv"),
            (self._chk_pausiert,  "Pausiert ⏸"),
            (self._chk_vermittelt,"Vermittelt ✓"),
        ], start=1):
            ctk.CTkCheckBox(filter_frame, text=label, variable=var,
                            command=self._on_filter_change).grid(
                row=row, column=0, padx=12, pady=3, sticky="w")

        ctk.CTkFrame(filter_frame, height=6, fg_color="transparent").grid(row=4, column=0)

        # Search
        self._search_var = ctk.StringVar()
        self._search_var.trace_add("write", lambda *_: self._on_search())
        ctk.CTkEntry(sidebar, placeholder_text="Suchen…",
                     textvariable=self._search_var).grid(
            row=2, column=0, padx=10, pady=(0, 6), sticky="ew")

        # Cat list
        self._listbox = ctk.CTkScrollableFrame(sidebar)
        self._listbox.grid(row=3, column=0, padx=4, pady=0, sticky="nsew")
        self._listbox.grid_columnconfigure(0, weight=1)

        self._status_label = ctk.CTkLabel(sidebar, text="",
                                          font=ctk.CTkFont(size=11))
        self._status_label.grid(row=4, column=0, padx=12, pady=6)

        # Detail panel
        detail = ctk.CTkScrollableFrame(self)
        detail.grid(row=0, column=1, padx=16, pady=16, sticky="nsew")
        detail.grid_columnconfigure(1, weight=1)
        self._detail = detail
        self._build_detail_form(detail)

    def _build_detail_form(self, parent):
        # _fields maps key → widget (CTkEntry | DatePickerFrame | CTkTextbox)
        self._fields: dict = {}

        plain_fields = [
            ("name",                   "Name"),
            ("url",                    "URL"),
            ("krankheiten_handicaps",  "Krankheiten / Handicaps"),
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

    # ── Data loading ──────────────────────────────────────────────────────────

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
            "filter_aktiv":     self._chk_aktiv.get(),
            "filter_pausiert":  self._chk_pausiert.get(),
            "filter_vermittelt": self._chk_vermittelt.get(),
        })
        cfg.save(self._prefs)
        self._load_list(self._search_var.get().strip())

    # ── Selection & form ──────────────────────────────────────────────────────

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
            if hasattr(raw, "isoformat"):
                value = raw.isoformat()
            else:
                value = str(raw) if raw is not None else ""

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
            elif isinstance(widget, ctk.CTkTextbox):
                widget.configure(state=state)
            else:
                widget.configure(state=state)

    # ── Save / Discard ────────────────────────────────────────────────────────

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

        # Validate dates
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


if __name__ == "__main__":
    app = App()
    app.mainloop()
