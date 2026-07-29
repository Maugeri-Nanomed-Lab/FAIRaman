# ─────────────────────────────────────────────────────────────────────────────
# GRAPHICAL USER INTERFACE
# ─────────────────────────────────────────────────────────────────────────────
import ctypes
import sys
from pathlib import Path
import pandas as pd
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from pathlib import Path
from fairaman.metadata_management import _guess_hdf5_mapping
from fairaman.schema import HDF5_FIELDS
from fairaman.metadata import parse_txt_metadata
from fairaman.conversion.wdf_pipeline import _run_conversion_wdf
from fairaman.conversion.ascii_pipeline import _run_conversion_txt
from fairaman.readers.wdf_reader import process_wdf

# ── Optional: Renishaw WDF reader ─────────────────────────────────────────────
try:
    from renishawWiRE import WDFReader
    HAS_WDF = True
except ImportError:
    HAS_WDF = False
    print(
        "[FAIRaman] INFO: renishawWiRE is not installed — WDF mode unavailable.\n"
        "           To enable: pip install renishawWiRE"
    )

# ── Windows DPI awareness ─────────────────────────────────────────────────────
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(1)
except Exception:
    pass

def _pick_path(key: str, is_file: bool, state: dict, entries: dict,
               frames: dict, parent: tk.Widget) -> None:
    """
    Open a file or directory browser dialog and update the application state.

    When a metadata file (TXT or Excel) is selected, the corresponding
    mapping panel is rebuilt to reflect the new field set.
    """
    path = filedialog.askopenfilename() if is_file else filedialog.askdirectory()
    if not path:
        return

    state["paths"][key] = Path(path)
    entries[key].delete(0, tk.END)
    entries[key].insert(0, path)

    if key == "excel":
        if "excel" in frames:
            frames["excel"].destroy()
            del frames["excel"]
        try:
            df = pd.read_excel(path)
            if not df.empty:
                frames["excel"] = _build_mapping_frame(
                    parent, df.iloc[0].to_dict(),
                    "Excel → NeXus mapping  (Sample level)"
                )
                frames["excel"].pack(fill="both", expand=True, padx=10, pady=5)
        except Exception as exc:
            messagebox.showerror("Error", f"Could not read Excel file:\n{exc}")

    if key == "txt":
        if "txt" in frames:
            frames["txt"].destroy()
            del frames["txt"]
        try:
            meta = parse_txt_metadata(Path(path))
            if meta:
                frames["txt"] = _build_mapping_frame(
                    parent, meta,
                    "Metadata TXT → NeXus mapping  (Investigation / Assay level)"
                )
                frames["txt"].pack(fill="both", expand=True, padx=10, pady=5)
            else:
                messagebox.showwarning(
                    "Warning",
                    "No metadata fields found in the selected TXT file.\n"
                    "Expected format: one 'key: value' pair per line."
                )
        except Exception as exc:
            messagebox.showerror("Error", f"Could not read TXT file:\n{exc}")

def launch_gui() -> None:
    """
    Initialise and display the FAIRaman graphical user interface.

    Styled to match H5Extractor: dark Catppuccin-inspired theme,
    Courier New monospace font, coloured section headers.
    All functional logic (paths, mapping panels, conversion) is unchanged.
    """
    root = tk.Tk()
    root.title("FAIRaman  \u2014  FAIR/MIABIS-compliant Raman Spectroscopy Converter")
    root.geometry("1200x920")
    root.resizable(True, True)

    # ── Theme constants (identical to H5Extractor) ────────────────────────────
    BG        = "#1e1e2e"
    BG_PANEL  = "#2a2a3e"
    FG        = "#cdd6f4"
    ACCENT    = "#89b4fa"
    ACCENT2   = "#a6e3a1"
    WARN      = "#f38ba8"
    BORDER    = "#45475a"
    FONT_HEAD = ("Courier New", 11, "bold")
    FONT_BODY = ("Courier New", 10)
    FONT_SM   = ("Courier New", 9)

    root.configure(bg=BG)

    style = ttk.Style(root)
    try:
        style.theme_use("clam")
    except Exception:
        pass
    style.configure("TFrame",      background=BG)
    style.configure("TLabel",      background=BG,       foreground=FG,     font=FONT_BODY)
    style.configure("TLabelframe", background=BG_PANEL, foreground=ACCENT, font=FONT_HEAD,
                    bordercolor=BORDER, relief="solid")
    style.configure("TLabelframe.Label", background=BG_PANEL, foreground=ACCENT, font=FONT_HEAD)
    style.configure("TEntry",      fieldbackground=BG_PANEL, foreground=FG,
                    insertcolor=FG, bordercolor=BORDER)
    style.configure("TButton",     background=ACCENT,  foreground=BG,
                    font=("Courier New", 10, "bold"), borderwidth=0)
    style.map("TButton",
              background=[("active", ACCENT2), ("pressed", ACCENT2)],
              foreground=[("active", BG)])
    style.configure("TRadiobutton", background=BG_PANEL, foreground=FG, font=FONT_BODY)
    style.map("TRadiobutton", background=[("active", BG_PANEL)])
    style.configure("TCheckbutton", background=BG_PANEL, foreground=FG, font=FONT_BODY)
    style.map("TCheckbutton", background=[("active", BG_PANEL)])
    style.configure("TProgressbar", troughcolor=BG_PANEL, background=ACCENT,
                    bordercolor=BORDER)
    style.configure("TCombobox", fieldbackground=BG_PANEL, foreground=FG,
                    selectbackground=ACCENT, selectforeground=BG)

    # ── Header ────────────────────────────────────────────────────────────────
    hdr = tk.Frame(root, bg=BG, pady=12)
    hdr.pack(fill="x", padx=20)
    tk.Label(hdr, text="FAIRaman", bg=BG, fg=ACCENT,
             font=("Courier New", 20, "bold")).pack(side="left")
    tk.Label(hdr, text="  FAIR/MIABIS-compliant Raman Spectroscopy Converter",
             bg=BG, fg=FG, font=FONT_BODY).pack(side="left", pady=4)

    # ── Scrollable main area ──────────────────────────────────────────────────
    main_canvas  = tk.Canvas(root, bg=BG, highlightthickness=0)
    v_scrollbar  = ttk.Scrollbar(root, orient="vertical", command=main_canvas.yview)
    scroll_frame = tk.Frame(main_canvas, bg=BG)
    scroll_frame.bind(
        "<Configure>",
        lambda e: main_canvas.configure(scrollregion=main_canvas.bbox("all"))
    )
    win_id = main_canvas.create_window((0, 0), window=scroll_frame, anchor="nw")
    main_canvas.configure(yscrollcommand=v_scrollbar.set)
    main_canvas.pack(side="left", fill="both", expand=True, padx=(20, 0), pady=(0, 10))
    v_scrollbar.pack(side="right", fill="y", pady=(0, 10))

    # Resize inner frame to always match canvas width
    def _on_canvas_resize(event):
        main_canvas.itemconfig(win_id, width=event.width)
    main_canvas.bind("<Configure>", _on_canvas_resize)

    # Mousewheel: scroll main canvas only when NOT over a widget with its own scroll
    def _on_mousewheel(event):
        w = event.widget
        # Walk up the widget tree to find if we are inside a mapping sub-canvas
        # (the inner scrollable area of Excel/TXT mapping panels)
        try:
            node = w
            while node:
                if isinstance(node, tk.Canvas) and node is not main_canvas:
                    # It's a sub-canvas (mapping panel) — scroll it, not the page
                    node.yview_scroll(int(-1 * (event.delta / 120)), "units")
                    return
                node = node.master
        except Exception:
            pass
        # Default: scroll the main page canvas
        main_canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

    root.bind_all("<MouseWheel>", _on_mousewheel)

    state:  dict = {"paths": {}}
    frames: dict = {}
    entries: dict = {}

    # ── Widget helpers ────────────────────────────────────────────────────────
    def _lf(parent, title):
        return tk.LabelFrame(parent, text=f" {title} ", bg=BG_PANEL, fg=ACCENT,
                             font=FONT_HEAD, bd=1, relief="solid",
                             highlightbackground=BORDER)

    def _lbl(parent, text, small=False, muted=False):
        return tk.Label(parent, text=text, bg=BG_PANEL,
                        fg="#6c7086" if muted else FG,
                        font=FONT_SM if small else FONT_BODY)

    def _ent(parent, textvariable=None, width=55):
        return tk.Entry(parent, textvariable=textvariable, bg=BG, fg=FG,
                        insertbackground=FG, font=FONT_BODY, width=width,
                        relief="flat", highlightthickness=1,
                        highlightcolor=ACCENT, highlightbackground=BORDER)

    def _btn(parent, text, command, big=False):
        bg = ACCENT2 if big else ACCENT
        return tk.Button(parent, text=text, bg=bg, fg=BG,
                         font=("Courier New", 12 if big else 10, "bold"),
                         relief="flat", cursor="hand2", padx=8,
                         activebackground=ACCENT, activeforeground=BG,
                         command=command)

    def _rb(parent, text, value, var):
        return tk.Radiobutton(parent, text=text, variable=var, value=value,
                              bg=BG_PANEL, fg=FG, selectcolor=BG,
                              activebackground=BG_PANEL, font=FONT_BODY,
                              command=lambda: _refresh_path_panel())

    def _cb(parent, text, variable):
        return tk.Checkbutton(parent, text=text, variable=variable,
                              bg=BG_PANEL, fg=FG, selectcolor=BG,
                              activebackground=BG_PANEL, font=FONT_BODY)

    # ── Section 1: Input mode ─────────────────────────────────────────────────
    mode_lf = _lf(scroll_frame, "Input mode")
    mode_lf.pack(fill="x", padx=10, pady=8)
    rb_row = tk.Frame(mode_lf, bg=BG_PANEL)
    rb_row.pack(anchor="w", padx=10, pady=8)

    mode_var = tk.StringVar(value="wdf")
    rb_wdf = _rb(rb_row, "WDF mode  (Renishaw WiRE .wdf files)", "wdf", mode_var)
    rb_txt = _rb(rb_row, "ASCII mode  (two-column text: wavenumber | intensity)", "txt", mode_var)
    rb_wdf.pack(side="left", padx=(0, 24))
    rb_txt.pack(side="left")

    if not HAS_WDF:
        rb_wdf.config(state="disabled")
        mode_var.set("txt")
        tk.Label(rb_row, text="(renishawWiRE not installed)",
                 bg=BG_PANEL, fg=WARN, font=FONT_SM).pack(side="left", padx=8)

    # ── Section 2: Path panel ─────────────────────────────────────────────────
    path_lf = _lf(scroll_frame, "File and folder paths")
    path_lf.pack(fill="x", padx=10, pady=8)

    _anchors: dict = {}
    def _make_row(label: str, key: str, is_file: bool, row: int):
        lbl_w = _lbl(path_lf, label)
        lbl_w.grid(row=row, column=0, sticky="w", padx=10, pady=5)
        ent = _ent(path_lf, width=68)
        ent.grid(row=row, column=1, padx=8, pady=5, sticky="ew")
        entries[key] = ent

        def _browse(k=key, f=is_file, e=ent):
            # Open dialog exactly once, then update state + rebuild mapping if needed
            path = (filedialog.askopenfilename() if f else filedialog.askdirectory())
            if not path:
                return
            state["paths"][k] = Path(path)
            e.delete(0, tk.END)
            e.insert(0, path)
            # Rebuild mapping panel for excel/txt keys
            if k == "excel":
                if "excel" in frames:
                    frames["excel"].destroy()
                    del frames["excel"]
                try:
                    df = pd.read_excel(path)
                    if not df.empty:
                        frames["excel"] = _build_mapping_frame(
                            scroll_frame, df.iloc[0].to_dict(),
                            "Excel \u2192 NeXus mapping  (Sample level)"
                        )
                        frames["excel"].pack(fill="both", expand=True,
                                             padx=10, pady=5, before=_anchors["opt_lf"])
                except Exception as exc:
                    messagebox.showerror("Error", f"Could not read Excel file:\n{exc}")
            elif k == "txt":
                if "txt" in frames:
                    frames["txt"].destroy()
                    del frames["txt"]
                try:
                    meta = parse_txt_metadata(Path(path))
                    if meta:
                        frames["txt"] = _build_mapping_frame(
                            scroll_frame, meta,
                            "Metadata TXT \u2192 NeXus mapping  (Investigation / Assay level)"
                        )
                        frames["txt"].pack(fill="both", expand=True,
                                           padx=10, pady=5, before=_anchors["opt_lf"])
                    else:
                        messagebox.showwarning(
                            "Warning",
                            "No metadata fields found in the TXT file.\n"
                            "Expected format: one 'key: value' pair per line."
                        )
                except Exception as exc:
                    messagebox.showerror("Error", f"Could not read TXT file:\n{exc}")

        b = _btn(path_lf, "Browse\u2026", _browse)
        b.grid(row=row, column=2, padx=(0, 10))
        path_lf.columnconfigure(1, weight=1)
        return lbl_w, ent, b

    row_wdf     = _make_row("WDF folder:",               "wdf",         False, 0)
    row_spectra = _make_row("Spectra folder:",            "spectra_dir", False, 0)
    row_excel   = _make_row("Sample metadata (Excel):",  "excel",       True,  1)
    row_txt_    = _make_row("Shared metadata (TXT):",    "txt",         True,  2)
    row_out     = _make_row("Output folder:",            "out",         False, 3)

    def _refresh_path_panel():
        if mode_var.get() == "wdf":
            for w in row_wdf:     w.grid()
            for w in row_spectra: w.grid_remove()
        else:
            for w in row_spectra: w.grid()
            for w in row_wdf:     w.grid_remove()

    _refresh_path_panel()

    # Section 3: mapping panels are inserted dynamically before opt_lf when
    # the user picks an Excel or TXT file (see _browse inside _make_row).

    # ── Section 4: Output options ─────────────────────────────────────────────
    opt_lf = _lf(scroll_frame, "Output formats")
    _anchors["opt_lf"] = opt_lf
    opt_lf.pack(fill="x", padx=10, pady=8)
    opt_row = tk.Frame(opt_lf, bg=BG_PANEL)
    opt_row.pack(anchor="w", padx=10, pady=8)

    var_hdf5    = tk.BooleanVar(value=True)
    var_json    = tk.BooleanVar(value=True)
    var_csv     = tk.BooleanVar(value=True)


    _cb(opt_row, "HDF5 / NeXus (NXraman)",       var_hdf5).pack(side="left", padx=(0, 16))
    _cb(opt_row, "JSON metadata sidecar",         var_json).pack(side="left", padx=(0, 16))
    _cb(opt_row, "CSV spectral matrix",           var_csv).pack(side="left",  padx=(0, 16))


    help_lf = _lf(scroll_frame, "References")
    help_lf.pack(fill="x", padx=10, pady=8)
    help_row = tk.Frame(help_lf, bg=BG_PANEL)
    help_row.pack(anchor="w", padx=10, pady=8)
    _lbl(help_row, "Ontology references (UBERON, ICD-10, MIABIS, NXraman):").pack(
        side="left", padx=(0, 12))
    _btn(help_row, "\U0001f4da Open reference guide", _show_ontology_help).pack(side="left")

    # ── Progress ──────────────────────────────────────────────────────────────
    prog_frame = tk.Frame(scroll_frame, bg=BG)
    prog_frame.pack(fill="x", padx=10, pady=4)
    progress_var = tk.StringVar(value="Ready.")
    tk.Label(prog_frame, textvariable=progress_var, bg=BG, fg=FG,
             font=FONT_SM, anchor="w").pack(fill="x")
    progress_bar = ttk.Progressbar(prog_frame, mode="determinate")
    progress_bar.pack(fill="x", pady=4)

    # ── Console log ───────────────────────────────────────────────────────────
    log_lf = _lf(scroll_frame, "Console log")
    log_lf.pack(fill="both", expand=True, padx=10, pady=8)
    log_text = tk.Text(log_lf, bg=BG, fg=FG, font=("Courier New", 9),
                       height=8, relief="flat", wrap="word",
                       insertbackground=FG, state="disabled")
    log_scroll = ttk.Scrollbar(log_lf, command=log_text.yview)
    log_text.configure(yscrollcommand=log_scroll.set)
    log_text.pack(side="left", fill="both", expand=True, padx=4, pady=4)
    log_scroll.pack(side="right", fill="y", pady=4)
    log_text.tag_configure("ok",   foreground=ACCENT2)
    log_text.tag_configure("warn", foreground="#fab387")
    log_text.tag_configure("err",  foreground=WARN)
    log_text.tag_configure("info", foreground=FG)

    _orig_stdout = sys.stdout

    class _LogRedirect:
        def write(self, s):
            _orig_stdout.write(s)
            if s.strip():
                tag = ("warn" if "WARNING" in s
                       else "err"  if ("ERROR" in s or "SKIP" in s)
                       else "ok"   if ("written" in s.lower() or "complete" in s.lower())
                       else "info")
                log_text.configure(state="normal")
                log_text.insert("end", s if s.endswith("\n") else s + "\n", tag)
                log_text.see("end")
                log_text.configure(state="disabled")
                root.update_idletasks()
        def flush(self): _orig_stdout.flush()

    sys.stdout = _LogRedirect()

    # ── Run conversion ────────────────────────────────────────────────────────
    def _on_run():
        log_text.configure(state="normal")
        log_text.delete("1.0", "end")
        log_text.configure(state="disabled")
        if mode_var.get() == "wdf":
            _run_conversion_wdf(
                state, frames, var_hdf5, var_json, var_csv,
                progress_var, progress_bar, root
            )
        else:
            _run_conversion_txt(
                state, frames, var_hdf5, var_json, var_csv,
                progress_var, progress_bar, root
            )


    btn_frame = tk.Frame(scroll_frame, bg=BG)
    btn_frame.pack(pady=12)
    tk.Button(
        btn_frame, text="\u25b6  Run conversion",
        bg=ACCENT2, fg=BG, font=("Courier New", 12, "bold"),
        relief="flat", cursor="hand2", padx=24, pady=8,
        command=_on_run,
        activebackground=ACCENT, activeforeground=BG,
    ).pack()

    root.mainloop()
    sys.stdout = _orig_stdout

def _create_filterable_combobox(parent: tk.Widget, width: int = 60):
    """
    Finestrella selezione 
    """
    BG      = "#1e1e2e"
    BG_SEL  = "#89b4fa"
    FG      = "#cdd6f4"
    FG_SEL  = "#1e1e2e"
    BORDER  = "#45475a"
    FONT    = ("Courier New", 9)

    frame = tk.Frame(parent, bg=BORDER, bd=1, relief="flat")
    var   = tk.StringVar(value="Do not map")

    entry = tk.Entry(frame, textvariable=var, bg="#2a2a3e", fg=FG,
                     insertbackground=FG, font=FONT, relief="flat",
                     bd=4, width=width)
    entry.pack(fill="x")

    # ── Floating dropdown ────────────────────────────────────────────────────
    popup    = None   
    listbox  = None
    _open    = [False]

    def _filtered():
        q = var.get().lower().strip()
        if not q or q == "do not map":
            return HDF5_FIELDS
        starts   = [f for f in HDF5_FIELDS if f.lower().startswith(q)]
        contains = [f for f in HDF5_FIELDS if q in f.lower() and f not in starts]
        return starts + contains

    def _open_popup(*_):
        nonlocal popup, listbox
        if _open[0]:
            _refresh_list()
            return
        _open[0] = True

        popup = tk.Toplevel(entry)
        popup.wm_overrideredirect(True)
        popup.wm_attributes("-topmost", True)

        # Position below the entry
        entry.update_idletasks()
        x = entry.winfo_rootx()
        y = entry.winfo_rooty() + entry.winfo_height()
        w = max(entry.winfo_width(), 380)
        popup.geometry(f"{w}x220+{x}+{y}")

        sb = tk.Scrollbar(popup, orient="vertical")
        listbox = tk.Listbox(popup, yscrollcommand=sb.set,
                             bg=BG, fg=FG, selectbackground=BG_SEL,
                             selectforeground=FG_SEL, font=FONT,
                             relief="flat", bd=0,
                             activestyle="none", exportselection=False)
        sb.config(command=listbox.yview)
        sb.pack(side="right", fill="y")
        listbox.pack(side="left", fill="both", expand=True)

        # Scroll wheel on listbox scrolls
        def _lb_scroll(event):
            listbox.yview_scroll(int(-1*(event.delta/120)), "units")
            return "break"
        listbox.bind("<MouseWheel>", _lb_scroll)
        popup.bind("<MouseWheel>", _lb_scroll)

        listbox.bind("<ButtonRelease-1>", _select)
        listbox.bind("<Return>",          _select)

        _refresh_list()

        # Close when clicking outside
        popup.bind("<FocusOut>", lambda e: _maybe_close())

    def _refresh_list():
        if not listbox:
            return
        items = _filtered()
        listbox.delete(0, "end")
        for item in items:
            listbox.insert("end", item)
        # Highlight current value
        cur = var.get()
        if cur in items:
            idx = items.index(cur)
            listbox.selection_set(idx)
            listbox.see(idx)

    def _select(event=None):
        if not listbox:
            return
        sel = listbox.curselection()
        if sel:
            var.set(listbox.get(sel[0]))
        _close()

    def _close():
        nonlocal popup, listbox
        _open[0] = False
        if popup:
            try: popup.destroy()
            except Exception: pass
        popup   = None
        listbox = None

    def _on_root_click(event):
        if not _open[0]:
            return
        w = event.widget
        try:
            if w is entry or w is frame:
                return
            if popup and str(w).startswith(str(popup)):
                return
        except Exception:
            pass
        _close()

    entry.after(1, lambda: entry.winfo_toplevel().bind_all(
        "<Button-1>", _on_root_click, add="+"
    ))

    def _maybe_close():
        entry.after(150, lambda: _close() if not _open[0] else None)

    def _on_key(event):
        if event.keysym == "Escape":
            _close(); return
        if event.keysym in ("Return", "Tab"):
            _select(); return
        if event.keysym in ("Down", "Up"):
            if not _open[0]:
                _open_popup()
            if listbox:
                sel = listbox.curselection()
                idx = sel[0] if sel else -1
                if event.keysym == "Down":
                    idx = min(idx + 1, listbox.size() - 1)
                else:
                    idx = max(idx - 1, 0)
                listbox.selection_clear(0, "end")
                listbox.selection_set(idx)
                listbox.see(idx)
            return "break"
        # Any other key: open and refresh
        entry.after(10, lambda: (_open_popup() if not _open[0] else _refresh_list()))

    entry.bind("<KeyPress>",    _on_key)
    entry.bind("<FocusOut>",    lambda e: entry.after(200, lambda: _close() if popup and not popup.focus_get() else None))
    entry.bind("<Button-1>",    _open_popup)
    entry.bind("<MouseWheel>",  lambda e: "break")   # absorb — don't scroll page
    frame.bind("<MouseWheel>",  lambda e: "break")

    frame.get = var.get
    frame.set = var.set
    frame.var = var
    return frame

def _build_mapping_frame(parent: tk.Widget, source_dict: dict,
                         title: str, use_first_guess: bool = True) -> tk.LabelFrame:
    
    """
    Fa funzionare la finestra scrollabile laga ves
    """
    BG       = "#1e1e2e"
    BG_PANEL = "#2a2a3e"
    FG       = "#cdd6f4"
    ACCENT   = "#89b4fa"
    BORDER   = "#45475a"
    FONT_SM  = ("Courier New", 9)
    FONT_B   = ("Courier New", 9, "bold")

    frame  = tk.LabelFrame(parent, text=f" {title} ", bg=BG_PANEL, fg=ACCENT,
                           font=("Courier New", 11, "bold"), bd=1, relief="solid",
                           highlightbackground=BORDER)
    canvas = tk.Canvas(frame, height=260, bg=BG_PANEL, highlightthickness=0)
    sb     = ttk.Scrollbar(frame, orient="vertical", command=canvas.yview)
    inner  = tk.Frame(canvas, bg=BG_PANEL)

    inner.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
    canvas.create_window((0, 0), window=inner, anchor="nw")
    canvas.configure(yscrollcommand=sb.set)
    canvas.pack(side="left", fill="both", expand=True, padx=4, pady=4)
    sb.pack(side="right", fill="y", pady=4)

    def _sub_scroll(event):
        canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
        return "break"
    canvas.bind("<MouseWheel>", _sub_scroll)
    inner.bind("<MouseWheel>",  _sub_scroll)

    # Header row
    tk.Label(inner, text="Campo sorgente", font=FONT_B,
             bg=BG_PANEL, fg=ACCENT).grid(row=0, column=0, sticky="w", padx=8, pady=4)
    tk.Label(inner, text="→  HDF5 target path", font=FONT_B,
             bg=BG_PANEL, fg=ACCENT).grid(row=0, column=1, sticky="w", padx=8, pady=4)

    combos: dict = {}
    for i, (key, val) in enumerate(source_dict.items(), 1):
        tk.Label(inner, text=f"{key}: {str(val)[:60]}",
                 bg=BG_PANEL, fg=FG, font=FONT_SM,
                 wraplength=460, anchor="w").grid(
            row=i, column=0, sticky="w", padx=8, pady=2)

        cb = _create_filterable_combobox(inner)

        if use_first_guess:
            guess = _guess_hdf5_mapping(key)
            if guess in HDF5_FIELDS:
                cb.set(guess)

        cb.grid(row=i, column=1, sticky="ew", padx=8, pady=2)
        combos[key] = cb

    inner.columnconfigure(1, weight=1)
    frame.get_mapping = lambda: {k: cb.get() for k, cb in combos.items()}
    return frame

def _show_ontology_help() -> None:
    hw = tk.Toplevel()
    hw.title("FAIRaman — Ontology Reference")
    hw.geometry("620x380")

    tf = ttk.Frame(hw)
    tf.pack(fill="both", expand=True, padx=10, pady=10)
    tw = tk.Text(tf, wrap="word", font=("Consolas", 10))
    sb = ttk.Scrollbar(tf, command=tw.yview)
    tw.configure(yscrollcommand=sb.set)
    tw.pack(side="left", fill="both", expand=True)
    sb.pack(side="right", fill="y")

    content = (
        "═══ ONTOLOGY AND STANDARD REFERENCES ═══\n\n"
        "Anatomical site (anatomical_site_cs):\n"
        "  UBERON: https://www.ebi.ac.uk/ols/ontologies/uberon\n"
        "  Format: UBERON:<numeric_id>  (e.g. UBERON:0000178 for blood)\n\n"
        "Diagnosis coding (diagnosis_code / diagnosis_ontology):\n"
        "  ICD-10:  https://icd.who.int/browse10/2019/en\n"
        "  ICD-O-3: https://www.who.int/standards/classifications\n"
        "  Format: ICD-10:<code>  (e.g. ICD-10:K50.0 for Crohn's disease)\n\n"
        "Biobanking standard:\n"
        "  MIABIS v3: https://github.com/BBMRI-ERIC/miabis\n\n"
        "NeXus / NXraman:\n"
        "  https://manual.nexusformat.org/classes/applications/NXraman.html\n\n"
        "FAIR principles:\n"
        "  Wilkinson et al. (2016) Sci. Data 3, 160018\n"
        "  https://doi.org/10.1038/sdata.2016.18\n"
    )
    tw.insert("1.0", content)
    tw.config(state="disabled")
    ttk.Button(hw, text="Close", command=hw.destroy).pack(pady=10)

def _show_completion_report(progress_var: tk.StringVar, success: int,
                            total: int, failed: list, out_dir: Path) -> None:
    """Display a modal summary dialog at the end of a batch conversion."""
    progress_var.set("Conversion complete.")
    msg = f"Conversion complete.\n\n✅ Files processed: {success}/{total}\n"
    if failed:
        msg += f"\n❌ Files with errors: {len(failed)}\n"
        msg += "\n".join(f"  • {e}" for e in failed[:5])
        if len(failed) > 5:
            msg += f"\n  … and {len(failed) - 5} more"
    msg += f"\n\n📁 Output written to:\n{out_dir}"
    messagebox.showinfo("FAIRaman — Conversion complete", msg)