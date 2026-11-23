import tkinter as tk
from tkinter import ttk
from tkinter import filedialog, messagebox
import csv
import json
import os

import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.patches import Polygon
from matplotlib.backends.backend_pdf import PdfPages

from beam_calculations import (
    PointLoad,
    UniformLoad,
    analyze_beam,
    check_section,
    find_recommended_section,
    sections_for_material,
)


ACCENT = "#2563eb"
GREEN = "#16834d"
AMBER = "#d97706"
RED = "#dc2626"
TEXT = "#172033"
MUTED = "#667085"


class ToolTip:
    def __init__(self, widget, text):
        self.widget = widget
        self.text = text
        self.tip = None
        widget.bind("<Enter>", self.show)
        widget.bind("<Leave>", self.hide)

    def show(self, _event):
        x = self.widget.winfo_rootx() + 20
        y = self.widget.winfo_rooty() + self.widget.winfo_height() + 8
        self.tip = tk.Toplevel(self.widget)
        self.tip.wm_overrideredirect(True)
        self.tip.wm_geometry(f"+{x}+{y}")
        tk.Label(
            self.tip,
            text=self.text,
            justify="left",
            background="#172033",
            foreground="white",
            relief="solid",
            borderwidth=1,
            padx=8,
            pady=6,
        ).pack()

    def hide(self, _event=None):
        if self.tip is not None:
            self.tip.destroy()
            self.tip = None


class BeamDesignerApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Beam Designer")
        self.root.geometry("1280x820")
        self.root.minsize(900, 650)

        self.support = tk.StringVar(value="Simply Supported")
        self.span = tk.DoubleVar(value=20.0)
        self.material = tk.StringVar(value="Steel")
        self.section_name = tk.StringVar(value="W12x26")
        self.deflection_limit = tk.StringVar(value="L/360")
        self.waste_factor = tk.IntVar(value=5)
        self.point_loads = []
        self.uniform_loads = [UniformLoad(1.0, 0.0, 20.0)]

        self.load_widgets = []
        self._span_updating = False

        self._build_ui()
        self.drag_point_index = None
        self._schedule_update()

    def _build_ui(self):
        style = ttk.Style(self.root)
        style.theme_use("clam")
        style.configure("TFrame", background="#eef3f9")
        style.configure("TLabel", background="#ffffff", foreground=TEXT)
        style.configure("Card.TFrame", background="#ffffff", relief="flat")
        style.configure("Title.TLabel", background="#ffffff", foreground=TEXT,
                        font=("Segoe UI", 11, "bold"))
        style.configure("Muted.TLabel", background="#ffffff", foreground=MUTED,
                        font=("Segoe UI", 9))
        style.configure("Accent.TButton", foreground="white",
                        background=ACCENT, borderwidth=0,
                        focusscolor=ACCENT)

        top = ttk.Frame(self.root)
        top.pack(fill="x")
        header = tk.Frame(top, height=58, bg="#ffffff", highlightthickness=0)
        header.pack(fill="x")
        header.pack_propagate(False)
        menubar = tk.Menu(self.root)
        file_menu = tk.Menu(menubar, tearoff=False)
        file_menu.add_command(label="Save", command=self.save_design)
        file_menu.add_command(label="Open", command=self.open_design)
        menubar.add_cascade(label="File", menu=file_menu)
        self.root.config(menu=menubar)
        tk.Label(
            header,
            text="Beam Designer",
            bg="#ffffff",
            fg=TEXT,
            font=("Segoe UI", 17, "bold"),
        ).pack(side="left", padx=20, pady=12)

        body = tk.Frame(self.root, bg="#eef3f9")
        body.pack(fill="both", expand=True)

        paned = tk.PanedWindow(
            body,
            orient="horizontal",
            sashwidth=6,
            sashrelief="flat",
            bg="#eef3f9",
        )
        paned.pack(fill="both", expand=True, padx=12, pady=12)

        left = tk.Frame(paned, bg="#ffffff", padx=14, pady=12)
        paned.add(left, width=330, minsize=300)
        right = tk.Frame(paned, bg="#eef3f9")
        paned.add(right, minsize=520)

        self._build_input_panel(left)
        self._build_output_panel(right)

    def _card_label(self, parent, text):
        ttk.Label(parent, text=text, style="Title.TLabel").pack(
            anchor="w", pady=(0, 8)
        )

    def _build_input_panel(self, parent):
        canvas = tk.Canvas(parent, bg="#ffffff", highlightthickness=0)
        scrollbar = ttk.Scrollbar(parent, orient="vertical", command=canvas.yview)
        inner = tk.Frame(canvas, bg="#ffffff")
        inner.bind(
            "<Configure>",
            lambda _event: canvas.configure(scrollregion=canvas.bbox("all")),
        )
        canvas.create_window((0, 0), window=inner, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        canvas.bind_all("<MouseWheel>", lambda event: canvas.yview_scroll(
            int(-1 * (event.delta / 120)), "units"
        ))

        self._card_label(inner, "Support")
        support_row = tk.Frame(inner, bg="#edf1f7", padx=4, pady=4)
        support_row.pack(fill="x", pady=(0, 14))
        for text in ("Simply Supported", "Cantilever"):
            tk.Radiobutton(
                support_row,
                text="Cantilever" if text == "Cantilever" else "Simply supported",
                variable=self.support,
                value=text,
                indicatoron=False,
                selectcolor=ACCENT,
                activebackground=ACCENT,
                activeforeground="white",
                fg=TEXT,
                bg="#edf1f7",
                padx=6,
                pady=6,
                font=("Segoe UI", 9),
                command=self._schedule_update,
            ).pack(side="left", expand=True, fill="x")

        self._card_label(inner, "Span")
        span_row = tk.Frame(inner, bg="#ffffff")
        span_row.pack(fill="x", pady=(0, 14))
        self.span_scale = tk.Scale(
            span_row,
            from_=4,
            to=20,
            resolution=1,
            orient="horizontal",
            variable=self.span,
            command=self._span_scale_changed,
            showvalue=True,
            troughcolor="#dfe7f2",
            activebackground=ACCENT,
            highlightthickness=0,
        )
        self.span_scale.pack(side="left", fill="x", expand=True)

        self._card_label(inner, "Loads")
        self.loads_container = tk.Frame(inner, bg="#ffffff")
        self.loads_container.pack(fill="x", pady=(0, 8))
        self._render_loads()

        add_row = tk.Frame(inner, bg="#ffffff")
        add_row.pack(fill="x", pady=(0, 14))
        tk.Button(
            add_row,
            text="+ Add point load",
            command=self._add_point_load,
            bg="#eff6ff",
            fg="#1d4ed8",
            relief="flat",
            padx=6,
            pady=7,
        ).pack(side="left", expand=True, fill="x", padx=(0, 4))
        tk.Button(
            add_row,
            text="+ Add uniform load",
            command=self._add_uniform_load,
            bg="#eff6ff",
            fg="#1d4ed8",
            relief="flat",
            padx=6,
            pady=7,
        ).pack(side="left", expand=True, fill="x", padx=(4, 0))

        self._card_label(inner, "Material")
        tk.OptionMenu(
            inner,
            self.material,
            "Steel",
            "Douglas Fir-Larch No. 2",
            command=self._material_changed,
        ).pack(fill="x", pady=(0, 10))

        ttk.Label(inner, text="Section", style="Title.TLabel").pack(
            anchor="w", pady=(2, 6)
        )
        self.section_menu = tk.OptionMenu(inner, self.section_name, "")
        self.section_menu.pack(fill="x", pady=(0, 14))
        self._refresh_section_menu()

        ttk.Label(inner, text="Deflection limit", style="Title.TLabel").pack(
            anchor="w", pady=(2, 6)
        )
        limit_row = tk.Frame(inner, bg="#edf1f7", padx=4, pady=4)
        limit_row.pack(fill="x", pady=(0, 14))
        for text in ("L/240", "L/360"):
            tk.Radiobutton(
                limit_row,
                text=text,
                variable=self.deflection_limit,
                value=text,
                indicatoron=False,
                selectcolor=ACCENT,
                activebackground=ACCENT,
                activeforeground="white",
                fg=TEXT,
                bg="#edf1f7",
                padx=6,
                pady=6,
                command=self._schedule_update,
            ).pack(side="left", expand=True, fill="x")

        ttk.Label(inner, text="Waste factor", style="Title.TLabel").pack(
            anchor="w", pady=(2, 6)
        )
        waste_row = tk.Frame(inner, bg="#ffffff")
        waste_row.pack(fill="x")
        tk.Scale(
            waste_row,
            from_=0,
            to=15,
            resolution=1,
            orient="horizontal",
            variable=self.waste_factor,
            command=lambda _value: self._schedule_update(),
            showvalue=True,
            troughcolor="#dfe7f2",
            activebackground=ACCENT,
            highlightthickness=0,
        ).pack(side="left", fill="x", expand=True)

    def _build_output_panel(self, parent):
        top_row = tk.Frame(parent, bg="#eef3f9")
        top_row.pack(fill="both", expand=True)

        beam_card = tk.Frame(top_row, bg="#ffffff", highlightthickness=1,
                             highlightbackground="#edf0f5")
        beam_card.pack(side="top", fill="both", expand=True, pady=(0, 8))

        plt.rcParams.update({
            "font.family": "Segoe UI",
            "font.size": 9,
            "axes.edgecolor": "#b8c1cf",
            "axes.labelcolor": MUTED,
            "xtick.color": MUTED,
            "ytick.color": MUTED,
        })
        self.fig = plt.Figure(figsize=(9, 6.6), dpi=100)
        self.fig.patch.set_facecolor("#ffffff")
        grid = self.fig.add_gridspec(
            4, 1, height_ratios=[1.15, 1, 1, 1],
            hspace=0.18,
            left=0.07,
            right=0.98,
            top=0.97,
            bottom=0.07,
        )
        self.beam_ax = self.fig.add_subplot(grid[0])
        self.shear_ax = self.fig.add_subplot(grid[1], sharex=self.beam_ax)
        self.moment_ax = self.fig.add_subplot(grid[2], sharex=self.beam_ax)
        self.deflection_ax = self.fig.add_subplot(grid[3], sharex=self.beam_ax)

        self.canvas = FigureCanvasTkAgg(self.fig, master=beam_card)
        self.canvas.get_tk_widget().pack(fill="both", expand=True)
        self.canvas.mpl_connect("motion_notify_event", self._on_hover)
        self.canvas.mpl_connect("button_press_event", self._on_load_press)
        self.canvas.mpl_connect("button_release_event", self._on_load_release)

        cards = tk.Frame(parent, bg="#eef3f9")
        cards.pack(fill="x", pady=(0, 0))
        self.bending_card = self._make_check_card(
            cards, "Bending", "fb = |Mmax| x 12 / Sx"
        )
        self.deflection_card = self._make_check_card(
            cards, "Deflection", "Check = |ymax| <= L/240 or L/360"
        )
        self.recommend_card = self._make_recommend_card(cards)

    def _make_check_card(self, parent, title, formula):
        card = tk.Frame(parent, bg="#ffffff", highlightthickness=1,
                        highlightbackground="#edf0f5")
        card.pack(side="left", fill="both", expand=True, padx=(0, 8))
        tk.Label(
            card,
            text=title,
            bg="#ffffff",
            fg=TEXT,
            font=("Segoe UI", 11, "bold"),
        ).pack(anchor="w", padx=10, pady=(8, 2))
        value = tk.Label(
            card,
            text="",
            bg="#ffffff",
            fg=MUTED,
            font=("Segoe UI", 9),
        )
        value.pack(anchor="w", padx=10)
        bar = tk.Canvas(card, height=8, bg="#ffffff", highlightthickness=0)
        bar.pack(fill="x", padx=10, pady=(6, 3))
        status = tk.Label(
            card,
            text="",
            bg="#ffffff",
            fg=TEXT,
            font=("Segoe UI", 10, "bold"),
        )
        status.pack(anchor="e", padx=10, pady=(0, 8))
        ToolTip(card, formula)
        return {"card": card, "value": value, "bar": bar, "status": status}

    def _make_recommend_card(self, parent):
        card = tk.Frame(parent, bg="#ffffff", highlightthickness=1,
                        highlightbackground="#edf0f5")
        card.pack(side="left", fill="both", expand=True)
        tk.Label(
            card,
            text="Recommended section",
            bg="#ffffff",
            fg=TEXT,
            font=("Segoe UI", 11, "bold"),
        ).pack(anchor="w", padx=10, pady=(8, 2))
        message = tk.Label(
            card,
            text="",
            bg="#ffffff",
            fg=MUTED,
            justify="left",
            wraplength=270,
            font=("Segoe UI", 9),
        )
        message.pack(anchor="w", padx=10)
        button = tk.Button(
            card,
            text="Use section",
            command=self._use_recommended,
            bg=ACCENT,
            fg="white",
            relief="flat",
            padx=8,
            pady=5,
        )
        button.pack(anchor="e", padx=10, pady=(4, 8))
        export_row = tk.Frame(card, bg="#ffffff")
        export_row.pack(fill="x", padx=10, pady=(0, 8))
        tk.Button(
            export_row,
            text="Export Results",
            command=self.export_results,
            bg="#eff6ff",
            fg="#1d4ed8",
            relief="flat",
            padx=6,
            pady=5,
        ).pack(side="left", expand=True, fill="x", padx=(0, 4))
        tk.Button(
            export_row,
            text="Calculation Sheet",
            command=self.export_pdf,
            bg="#eff6ff",
            fg="#1d4ed8",
            relief="flat",
            padx=6,
            pady=5,
        ).pack(side="left", expand=True, fill="x", padx=(4, 0))
        return {"card": card, "message": message, "button": button}

    def _span_scale_changed(self, _value):
        self._schedule_update()

    def _schedule_update(self, _event=None):
        if hasattr(self, "canvas"):
            self.root.after_cancel(getattr(self, "_pending_update", ""))
        self._pending_update = self.root.after(30, self._update)

    def _material_changed(self, _material):
        sections = sections_for_material(self.material.get())
        self.section_name.set(sections[0].name)
        self._refresh_section_menu()
        self._schedule_update()

    def _refresh_section_menu(self):
        menu = self.section_menu["menu"]
        menu.delete(0, "end")
        sections = sections_for_material(self.material.get())
        for section in sections:
            menu.add_command(
                label=section.name,
                command=lambda name=section.name: (
                    self.section_name.set(name),
                    self._schedule_update(),
                ),
            )
        if self.section_name.get() not in [section.name for section in sections]:
            self.section_name.set(sections[0].name)
        self.section_menu.config(textvariable=self.section_name)

    def _render_loads(self):
        for widget in self.load_widgets:
            widget.destroy()
        self.load_widgets = []

        for index, load in enumerate(self.point_loads):
            frame = tk.Frame(
                self.loads_container,
                bg="#f8fafc",
                highlightthickness=1,
                highlightbackground="#e3e9f1",
                padx=8,
                pady=6,
            )
            frame.pack(fill="x", pady=(0, 6))
            self.load_widgets.append(frame)
            tk.Label(
                frame,
                text=f"Point {index + 1}",
                bg="#f8fafc",
                fg=MUTED,
                font=("Segoe UI", 8, "bold"),
            ).grid(row=0, column=0, columnspan=3, sticky="w")
            tk.Label(frame, text="kips", bg="#f8fafc", fg=MUTED).grid(
                row=1, column=0, sticky="w"
            )
            mag = tk.DoubleVar(value=load.magnitude)
            mag_entry = tk.Spinbox(
                frame,
                from_=0.1,
                to=100,
                increment=0.1,
                textvariable=mag,
                width=8,
                command=lambda i=index, v=mag: self._edit_point(i, v.get(), None),
            )
            mag_entry.bind("<KeyRelease>", lambda _e, i=index, v=mag:
                           self._edit_point(i, v.get(), None))
            mag_entry.grid(row=2, column=0, sticky="ew", padx=(0, 5))
            tk.Label(frame, text="Position ft", bg="#f8fafc", fg=MUTED).grid(
                row=1, column=1, sticky="w"
            )
            pos = tk.DoubleVar(value=load.position)
            pos_entry = tk.Spinbox(
                frame,
                from_=(-1 * self.span.get()),
                to=(2 * self.span.get()),
                increment=0.25,
                textvariable=pos,
                width=8,
                command=lambda i=index, v=pos: self._edit_point(i, None, v.get()),
            )
            pos_entry.bind("<KeyRelease>", lambda _e, i=index, v=pos:
                           self._edit_point(i, None, v.get()))
            pos_entry.grid(row=2, column=1, sticky="ew", padx=(0, 5))
            remove = tk.Button(
                frame,
                text="Remove",
                command=lambda i=index: self._remove_point(i),
                bg="#fee2e2",
                fg="#b91c1c",
                relief="flat",
                padx=4,
            )
            remove.grid(row=2, column=2)
            frame.grid_columnconfigure(0, weight=1)
            frame.grid_columnconfigure(1, weight=1)
            if len(self.point_loads) + len(self.uniform_loads) == 1:
                remove.configure(state="disabled")

        for index, load in enumerate(self.uniform_loads):
            frame = tk.Frame(
                self.loads_container,
                bg="#f8fafc",
                highlightthickness=1,
                highlightbackground="#e3e9f1",
                padx=8,
                pady=6,
            )
            frame.pack(fill="x", pady=(0, 6))
            self.load_widgets.append(frame)
            tk.Label(
                frame,
                text=f"Uniform {index + 1}",
                bg="#f8fafc",
                fg=MUTED,
                font=("Segoe UI", 8, "bold"),
            ).grid(row=0, column=0, columnspan=4, sticky="w")
            mag = tk.DoubleVar(value=load.magnitude)
            start = tk.DoubleVar(value=load.start)
            end = tk.DoubleVar(value=load.end)
            fields = (
                ("kips/ft", mag, 0.01, 10.0),
                ("Start ft", start, -1 * self.span.get(), 2 * self.span.get()),
                ("End ft", end, -1 * self.span.get(), 2 * self.span.get()),
            )
            for column, (label, variable, minimum, maximum) in enumerate(fields):
                tk.Label(frame, text=label, bg="#f8fafc", fg=MUTED).grid(
                    row=1, column=column, sticky="w"
                )
                entry = tk.Spinbox(
                    frame,
                    from_=minimum,
                    to=maximum,
                    increment=0.01 if column == 0 else 0.25,
                    textvariable=variable,
                    width=7,
                )
                entry.grid(row=2, column=column, sticky="ew", padx=(0, 4))
                entry.bind(
                    "<KeyRelease>",
                    lambda _e, i=index, m=mag, s=start, z=end:
                    self._edit_uniform(i, m.get(), s.get(), z.get()),
                )
                entry.configure(
                    command=lambda i=index, m=mag, s=start, z=end:
                    self._edit_uniform(i, m.get(), s.get(), z.get())
                )
            remove = tk.Button(
                frame,
                text="Remove",
                command=lambda i=index: self._remove_uniform(i),
                bg="#fee2e2",
                fg="#b91c1c",
                relief="flat",
                padx=4,
            )
            remove.grid(row=2, column=3)
            for column in range(3):
                frame.grid_columnconfigure(column, weight=1)
            if len(self.point_loads) + len(self.uniform_loads) == 1:
                remove.configure(state="disabled")

    def _valid_float(self, variable, minimum, maximum, fallback):
        try:
            value = float(variable)
            if minimum <= value <= maximum:
                return value
        except (TypeError, ValueError):
            pass
        return fallback

    def _edit_point(self, index, magnitude, position):
        load = self.point_loads[index]
        new_magnitude = self._valid_float(
            load.magnitude if magnitude is None else magnitude,
            0.1,
            100,
            load.magnitude,
        )
        new_position = self._valid_float(
            load.position if position is None else position,
            -self.span.get(),
            2 * self.span.get(),
            load.position,
        )
        new_position = round(new_position * 4) / 4
        self.point_loads[index] = PointLoad(new_magnitude, new_position)
        self._schedule_update()

    def _edit_uniform(self, index, magnitude, start, end):
        load = self.uniform_loads[index]
        magnitude = self._valid_float(magnitude, 0.01, 10, load.magnitude)
        start = self._valid_float(
            start, -self.span.get(), 2 * self.span.get(), load.start
        )
        end = self._valid_float(
            end, -self.span.get(), 2 * self.span.get(), load.end
        )
        start = round(start * 4) / 4
        end = round(end * 4) / 4
        if start <= end:
            self.uniform_loads[index] = UniformLoad(magnitude, start, end)
        self._schedule_update()

    def _add_point_load(self):
        position = self.span.get() / 2
        self.point_loads.append(PointLoad(1.0, position))
        self._render_loads()
        self._schedule_update()

    def _add_uniform_load(self):
        self.uniform_loads.append(
            UniformLoad(1.0, 0.0, self.span.get())
        )
        self._render_loads()
        self._schedule_update()

    def _remove_point(self, index):
        if len(self.point_loads) + len(self.uniform_loads) > 1:
            del self.point_loads[index]
            self._render_loads()
            self._schedule_update()

    def _remove_uniform(self, index):
        if len(self.point_loads) + len(self.uniform_loads) > 1:
            del self.uniform_loads[index]
            self._render_loads()
            self._schedule_update()

    def _current_section(self):
        for section in sections_for_material(self.material.get()):
            if section.name == self.section_name.get():
                return section
        sections = sections_for_material(self.material.get())
        return sections[0]

    def _schedule_update(self, _event=None):
        if hasattr(self, "_pending_update"):
            try:
                self.root.after_cancel(self._pending_update)
            except tk.TclError:
                pass
        self._pending_update = self.root.after(30, self._update)

    def _update(self):
        span = min(20.0, max(4.0, float(self.span.get())))
        self.span.set(span)
        section = self._current_section()
        point_loads = list(self.point_loads)
        uniform_loads = list(self.uniform_loads)
        support = self.support.get()
        limit = self.deflection_limit.get()

        analysis = analyze_beam(
            support,
            span,
            point_loads,
            uniform_loads,
            section,
        )
        bending = check_section(
            support,
            span,
            point_loads,
            uniform_loads,
            section,
            limit,
        )
        recommended = find_recommended_section(
            support,
            span,
            point_loads,
            uniform_loads,
            self.material.get(),
            limit,
        )
        self.recommended = recommended
        self.analysis = analysis
        self._draw(analysis)
        self._update_checks(bending, recommended)

    def _draw(self, analysis):
        for ax in (
            self.beam_ax,
            self.shear_ax,
            self.moment_ax,
            self.deflection_ax,
        ):
            ax.clear()
            ax.set_facecolor("#ffffff")
            ax.grid(True, axis="x", color="#edf0f5", linewidth=0.8)

        span = analysis.span_ft
        support = analysis.support

        self.beam_ax.set_xlim(-0.02 * span, 1.02 * span)
        self.beam_ax.set_ylim(-0.8, 1.2)
        self.beam_ax.axis("off")
        self.beam_ax.plot([0, span], [0.35, 0.35], color="#344054",
                          linewidth=10, solid_capstyle="butt")

        if support == "Simply Supported":
            triangle = Polygon([(-0.035 * span, 0.12),
                                (0.035 * span, 0.12),
                                (0, -0.05)],
                               closed=True, facecolor="#344054")
            self.beam_ax.add_patch(triangle)
            triangle2 = Polygon(
                [(span - 0.035 * span, 0.12),
                 (span + 0.035 * span, 0.12),
                 (span, -0.05)],
                closed=True,
                facecolor="#344054",
            )
            self.beam_ax.add_patch(triangle2)
        else:
            self.beam_ax.add_patch(Polygon(
                [(-0.045 * span, -0.08),
                 (-0.045 * span, 0.78),
                 (0.02 * span, 0.78),
                 (0.02 * span, -0.08)],
                closed=True,
                facecolor="#344054",
            ))

        for load in self.point_loads:
            if 0 <= load.position <= span:
                arrow_height = 0.48
                self.beam_ax.annotate(
                    "",
                    xy=(load.position, 0.35),
                    xytext=(load.position, 0.35 + arrow_height),
                    arrowprops=dict(
                        arrowstyle="-|>",
                        lw=1.8,
                        color=ACCENT,
                        mutation_scale=14,
                    ),
                )
                self.beam_ax.text(
                    load.position,
                    0.88,
                    f"{load.magnitude:g} k",
                    ha="center",
                    va="bottom",
                    color=ACCENT,
                    fontsize=8,
                    fontweight="bold",
                )

        for load in self.uniform_loads:
            start = max(0, load.start)
            end = min(span, load.end)
            if end > start:
                positions = [
                    start + i * 0.5
                    for i in range(int((end - start) / 0.5) + 1)
                ]
                positions = [p for p in positions if p <= end]
                for position in positions:
                    self.beam_ax.annotate(
                        "",
                        xy=(position, 0.35),
                        xytext=(position, 0.83),
                        arrowprops=dict(
                            arrowstyle="-|>",
                            lw=1.0,
                            color=ACCENT,
                            mutation_scale=9,
                        ),
                    )
                self.beam_ax.text(
                    (start + end) / 2,
                    0.88,
                    f"{load.magnitude:g} k/ft",
                    ha="center",
                    va="bottom",
                    color=ACCENT,
                    fontsize=8,
                    fontweight="bold",
                )

        self._draw_reaction(analysis)
        self._plot_filled(
            self.shear_ax,
            analysis.x_ft,
            analysis.shear_kips,
            "Shear V (kips)",
            8,
            "k",
        )
        self._plot_filled(
            self.moment_ax,
            analysis.x_ft,
            analysis.moment_kipft,
            "Moment M (kip-ft)",
            analysis.max_moment_location_ft,
            "kip-ft",
        )
        self._plot_filled(
            self.deflection_ax,
            analysis.x_ft,
            analysis.deflection_in,
            "Deflected shape (in)",
            analysis.max_deflection_location_ft,
            "in",
        )

        self.hover_lines = []
        for ax in (self.shear_ax, self.moment_ax, self.deflection_ax):
            line = ax.axvline(
                0,
                color="#98a2b3",
                linewidth=1,
                linestyle="--",
                visible=False,
            )
            ax.set_xlabel("")
            self.hover_lines.append(line)
        self.hover_text = self.deflection_ax.text(
            0.995,
            0.03,
            "",
            transform=self.deflection_ax.transAxes,
            ha="right",
            va="bottom",
            color=MUTED,
            fontsize=8,
            bbox=dict(
                boxstyle="round,pad=0.25",
                facecolor="#ffffff",
                edgecolor="#dfe5ee",
                alpha=0.95,
            ),
        )
        self.deflection_ax.set_xlabel("Position (ft)")
        self.canvas.draw_idle()

    def _draw_reaction(self, analysis):
        span = analysis.span_ft
        if analysis.support == "Simply Supported":
            positions = (0.0, span)
            values = (
                analysis.left_reaction_kips,
                analysis.right_reaction_kips,
            )
        else:
            positions = (0.0,)
            values = (analysis.left_reaction_kips,)
        for position, value in zip(positions, values):
            if abs(value) > 1e-9:
                self.beam_ax.annotate(
                    "",
                    xy=(position, 0.1),
                    xytext=(position, -0.28),
                    arrowprops=dict(
                        arrowstyle="-|>",
                        lw=1.5,
                        color=GREEN,
                        mutation_scale=12,
                    ),
                )
                self.beam_ax.text(
                    position,
                    -0.38,
                    f"{value:.1f} k",
                    ha="center",
                    va="top",
                    color=GREEN,
                    fontsize=8,
                    fontweight="bold",
                )
        if analysis.support == "Cantilever":
            self.beam_ax.text(
                0.02 * span,
                -0.38,
                f"M = {analysis.fixed_end_moment_kipft:.1f} kip-ft",
                ha="left",
                va="top",
                color=GREEN,
                fontsize=8,
                fontweight="bold",
            )

    def _plot_filled(self, ax, x, y, title, location, units):
        ax.plot(x, y, color=ACCENT, linewidth=1.6)
        ax.fill_between(x, y, 0, color="#dbeafe", alpha=0.9)
        ax.axhline(0, color="#344054", linewidth=0.7)
        ax.set_title(title, loc="left", fontsize=9, fontweight="bold",
                      color=MUTED, pad=3)
        ax.set_xlim(-0.01 * (x[-1] - x[0]), 1.01 * x[-1])
        ax.tick_params(labelsize=8)
        max_index = int(abs(y).argmax())
        max_value = y[max_index]
        ax.annotate(
            f"{abs(max_value):.3g} {units}",
            xy=(x[max_index], max_value),
            xytext=(0, 12 if max_value >= 0 else -12),
            textcoords="offset points",
            ha="center",
            va="bottom" if max_value >= 0 else "top",
            fontsize=8,
            color=TEXT,
            fontweight="bold",
            bbox=dict(
                boxstyle="round,pad=0.2",
                facecolor="#ffffff",
                edgecolor="#e2e8f0",
                alpha=0.95,
            ),
        )

    def _on_hover(self, event):
        if self.drag_point_index is not None:
            return
        if event.inaxes not in (
            self.shear_ax,
            self.moment_ax,
            self.deflection_ax,
        ):
            return
        if event.xdata is None:
            return
        x = min(max(event.xdata, 0), self.analysis.span_ft)
        index = int(abs(self.analysis.x_ft - x).argmin())
        shear = self.analysis.shear_kips[index]
        moment = self.analysis.moment_kipft[index]
        deflection = self.analysis.deflection_in[index]
        for line in self.hover_lines:
            line.set_xdata([self.analysis.x_ft[index],
                            self.analysis.x_ft[index]])
            line.set_visible(True)
        self.hover_text.set_text(
            f"x={self.analysis.x_ft[index]:.2f} ft\n"
            f"V={shear:.2f} k  M={moment:.2f} kip-ft  y={deflection:.3f} in"
        )
        self.canvas.draw_idle()

    def _on_load_press(self, event):
        if event.inaxes is not self.beam_ax or event.xdata is None:
            return
        span = self.span.get()
        nearest_index = None
        nearest_distance = float("inf")
        for index, load in enumerate(self.point_loads):
            if 0 <= load.position <= span:
                distance = abs(event.xdata - load.position)
                if distance < nearest_distance:
                    nearest_distance = distance
                    nearest_index = index
        tolerance = span * 0.025
        if nearest_index is not None and nearest_distance <= tolerance:
            self.drag_point_index = nearest_index

    def _on_load_release(self, event):
        if self.drag_point_index is None:
            return
        if event.xdata is not None:
            position = round(
                min(max(event.xdata, -self.span.get()),
                    2 * self.span.get()) * 4
            ) / 4
            load = self.point_loads[self.drag_point_index]
            self.point_loads[self.drag_point_index] = PointLoad(
                load.magnitude,
                position,
            )
        self.drag_point_index = None
        self._render_loads()
        self._schedule_update()

    def _status_color(self, ratio):
        if ratio < 0.70:
            return GREEN
        if ratio <= 1.0:
            return AMBER
        return RED

    def _update_check_card(self, card, actual, allowable, passed, unit):
        ratio = actual / allowable if allowable else 0
        card["value"].configure(
            text=f"Actual {actual:.3g} {unit}   |   Allowable {allowable:.3g} {unit}"
        )
        card["status"].configure(
            text="PASS" if passed else "FAIL",
            fg=GREEN if passed else RED,
        )
        bar = card["bar"]
        bar.delete("all")
        width = bar.winfo_width()
        if width < 2:
            width = 220
        bar.create_rectangle(0, 1, width, 7, fill="#edf0f5", outline="")
        fill_width = min(width, max(0, width * ratio))
        bar.create_rectangle(
            0,
            1,
            fill_width,
            7,
            fill=self._status_color(ratio),
            outline="",
        )

    def _update_checks(self, bending, recommended):
        self._update_check_card(
            self.bending_card,
            bending.bending_stress_ksi,
            bending.allowable_bending_ksi,
            bending.bending_pass,
            "ksi",
        )
        self._update_check_card(
            self.deflection_card,
            bending.max_deflection_in,
            bending.allowable_deflection_in,
            bending.deflection_pass,
            "in",
        )
        if recommended is None:
            self.recommend_card["message"].configure(
                text="No section in this material passes both checks."
            )
            self.recommend_card["button"].configure(state="disabled")
            self.recommended = None
        else:
            section = recommended.section
            extra = ""
            if section.weight_lbft is not None:
                weight = section.weight_lbft * (
                    1 + self.waste_factor.get() / 100
                )
                extra = f"\nAdjusted weight: {weight:.2f} lb/ft"
            self.recommend_card["message"].configure(
                text=f"{section.name}{extra}"
            )
            self.recommend_card["button"].configure(
                state="normal",
                command=self._use_recommended,
            )

    def _use_recommended(self):
        if getattr(self, "recommended", None) is None:
            return
        self.section_name.set(self.recommended.section.name)
        self._schedule_update()

    def save_design(self):
        path = filedialog.asksaveasfilename(
            title="Save beam design",
            defaultextension=".beam.json",
            filetypes=[
                ("Beam design", "*.beam.json"),
                ("JSON file", "*.json"),
            ],
        )
        if not path:
            return
        data = {
            "support": self.support.get(),
            "span_ft": float(self.span.get()),
            "material": self.material.get(),
            "section": self.section_name.get(),
            "deflection_limit": self.deflection_limit.get(),
            "waste_factor": int(self.waste_factor.get()),
            "point_loads": [
                {
                    "magnitude": load.magnitude,
                    "position": load.position,
                }
                for load in self.point_loads
            ],
            "uniform_loads": [
                {
                    "magnitude": load.magnitude,
                    "start": load.start,
                    "end": load.end,
                }
                for load in self.uniform_loads
            ],
        }
        try:
            with open(path, "w", encoding="utf-8") as file:
                json.dump(data, file, indent=2)
        except OSError as error:
            messagebox.showerror("Save failed", str(error))

    def open_design(self):
        path = filedialog.askopenfilename(
            title="Open beam design",
            filetypes=[
                ("Beam design", "*.beam.json"),
                ("JSON file", "*.json"),
            ],
        )
        if not path:
            return
        try:
            with open(path, "r", encoding="utf-8") as file:
                data = json.load(file)

            support = data["support"]
            if support not in ("Simply Supported", "Cantilever"):
                raise ValueError("Invalid support type")
            span = min(20.0, max(4.0, float(data["span_ft"])))
            material = data["material"]
            if material not in ("Steel", "Douglas Fir-Larch No. 2"):
                raise ValueError("Invalid material")
            deflection_limit = data["deflection_limit"]
            if deflection_limit not in ("L/240", "L/360"):
                raise ValueError("Invalid deflection limit")
            waste_factor = min(15, max(0, int(data["waste_factor"])))

            point_loads = []
            for item in data.get("point_loads", []):
                magnitude = float(item["magnitude"])
                position = float(item["position"])
                if not 0.1 <= magnitude <= 100:
                    raise ValueError("Invalid point-load magnitude")
                if not -span <= position <= 2 * span:
                    raise ValueError("Invalid point-load position")
                point_loads.append(
                    PointLoad(magnitude, round(position * 4) / 4)
                )

            uniform_loads = []
            for item in data.get("uniform_loads", []):
                magnitude = float(item["magnitude"])
                start = float(item["start"])
                end = float(item["end"])
                if not 0.01 <= magnitude <= 10:
                    raise ValueError("Invalid uniform-load magnitude")
                if not -span <= start <= 2 * span:
                    raise ValueError("Invalid uniform-load start")
                if not -span <= end <= 2 * span or start > end:
                    raise ValueError("Invalid uniform-load end")
                uniform_loads.append(
                    UniformLoad(
                        magnitude,
                        round(start * 4) / 4,
                        round(end * 4) / 4,
                    )
                )

            if not point_loads and not uniform_loads:
                raise ValueError("At least one load is required")

            sections = sections_for_material(material)
            section_names = [section.name for section in sections]
            section_name = data["section"]
            if section_name not in section_names:
                section_name = sections[0].name

            self.support.set(support)
            self.span.set(span)
            self.material.set(material)
            self.section_name.set(section_name)
            self.deflection_limit.set(deflection_limit)
            self.waste_factor.set(waste_factor)
            self.point_loads = point_loads
            self.uniform_loads = uniform_loads
            self._refresh_section_menu()
            self._render_loads()
            self._schedule_update()
        except (OSError, json.JSONDecodeError, KeyError, TypeError, ValueError) as error:
            messagebox.showerror("Open failed", str(error))

    def export_results(self):
        if not hasattr(self, "analysis"):
            messagebox.showinfo("Export Results", "The beam has not been calculated.")
            return
        path = filedialog.asksaveasfilename(
            title="Export beam results",
            defaultextension=".csv",
            filetypes=[("CSV file", "*.csv")],
        )
        if not path:
            return
        try:
            with open(path, "w", newline="", encoding="utf-8-sig") as file:
                writer = csv.writer(file)
                writer.writerow(["x (ft)", "V (kips)", "M (kip-ft)", "y (in)"])
                for x, shear, moment, deflection in zip(
                    self.analysis.x_ft,
                    self.analysis.shear_kips,
                    self.analysis.moment_kipft,
                    self.analysis.deflection_in,
                ):
                    writer.writerow([
                        f"{x:.4f}",
                        f"{shear:.6f}",
                        f"{moment:.6f}",
                        f"{deflection:.6f}",
                    ])
            if os.name == "nt":
                os.startfile(path)
        except OSError as error:
            messagebox.showerror("Export failed", str(error))

    def export_pdf(self):
        if not hasattr(self, "analysis"):
            messagebox.showinfo("Calculation Sheet", "The beam has not been calculated.")
            return
        path = filedialog.asksaveasfilename(
            title="Save calculation sheet",
            defaultextension=".pdf",
            filetypes=[("PDF file", "*.pdf")],
        )
        if not path:
            return
        try:
            section = self._current_section()
            bending = check_section(
                self.support.get(),
                float(self.span.get()),
                self.point_loads,
                self.uniform_loads,
                section,
                self.deflection_limit.get(),
            )
            recommended = getattr(self, "recommended", None)

            with PdfPages(path) as pdf:
                sheet = plt.Figure(figsize=(11, 8.5), dpi=150)
                sheet.patch.set_facecolor("white")
                grid = sheet.add_gridspec(
                    2,
                    1,
                    height_ratios=[0.42, 1.58],
                    hspace=0.25,
                    left=0.08,
                    right=0.96,
                    top=0.96,
                    bottom=0.08,
                )
                input_ax = sheet.add_subplot(grid[0])
                input_ax.axis("off")
                input_ax.set_title("Beam Calculation Sheet", fontsize=16, fontweight="bold")

                point_text = "; ".join(
                    f"{load.magnitude:g} k at {load.position:g} ft"
                    for load in self.point_loads
                ) or "None"
                uniform_text = "; ".join(
                    f"{load.magnitude:g} k/ft from {load.start:g} to {load.end:g} ft"
                    for load in self.uniform_loads
                ) or "None"
                inputs = (
                    f"Support: {self.support.get()}    "
                    f"Span: {self.span.get():g} ft\n"
                    f"Material: {self.material.get()}    "
                    f"Section: {section.name}\n"
                    f"Deflection limit: {self.deflection_limit.get()}    "
                    f"Waste factor: {self.waste_factor.get()}%\n"
                    f"Point loads: {point_text}\n"
                    f"Uniform loads: {uniform_text}"
                )
                input_ax.text(
                    0,
                    0.88,
                    inputs,
                    transform=input_ax.transAxes,
                    va="top",
                    fontsize=10,
                    linespacing=1.5,
                )

                plot_ax = sheet.add_subplot(grid[1])
                plot_ax.axis("off")
                export_grid = plot_ax.get_subplotspec().subgridspec(
                    3, 1, hspace=0.45
                )
                shear_ax = sheet.add_subplot(export_grid[0])
                moment_ax = sheet.add_subplot(export_grid[1])
                deflection_ax = sheet.add_subplot(export_grid[2])
                for ax, y, title in (
                    (shear_ax, self.analysis.shear_kips, "Shear V (kips)"),
                    (moment_ax, self.analysis.moment_kipft, "Moment M (kip-ft)"),
                    (deflection_ax, self.analysis.deflection_in, "Deflection y (in)"),
                ):
                    ax.plot(self.analysis.x_ft, y, color=ACCENT)
                    ax.fill_between(
                        self.analysis.x_ft,
                        y,
                        0,
                        color="#dbeafe",
                        alpha=0.9,
                    )
                    ax.axhline(0, color="#344054", linewidth=0.8)
                    ax.set_title(title, loc="left", fontsize=10)
                    ax.set_xlim(0, self.analysis.span_ft)
                    ax.grid(True, axis="x", color="#edf0f5")
                deflection_ax.set_xlabel("Position (ft)")

                check_text = (
                    f"Bending: {bending.bending_stress_ksi:.3f} ksi actual; "
                    f"{bending.allowable_bending_ksi:.3f} ksi allowable; "
                    f"{'PASS' if bending.bending_pass else 'FAIL'}\n"
                    f"Deflection: {bending.max_deflection_in:.3f} in actual; "
                    f"{bending.allowable_deflection_in:.3f} in allowable; "
                    f"{'PASS' if bending.deflection_pass else 'FAIL'}\n"
                )
                if recommended is not None:
                    check_text += (
                        f"Recommended section: {recommended.section.name}"
                    )
                deflection_ax.text(
                    1.0,
                    -0.55,
                    check_text,
                    transform=deflection_ax.transAxes,
                    ha="right",
                    va="top",
                    fontsize=9,
                    bbox=dict(
                        boxstyle="round,pad=0.35",
                        facecolor="#f8fafc",
                        edgecolor="#dfe5ee",
                    ),
                )
                pdf.savefig(sheet)
            if os.name == "nt":
                os.startfile(path)
        except (OSError, ValueError) as error:
            messagebox.showerror("Calculation sheet failed", str(error))


def main():
    root = tk.Tk()
    BeamDesignerApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
