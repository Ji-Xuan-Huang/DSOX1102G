import csv
import math
import queue
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

import pyvisa
from pyvisa.highlevel import list_backends


class ScopeToolsApp:
    def __init__(self, root):
        self.root = root
        self.root.title("VISA Scope Tools")
        self.root.minsize(720, 560)
        self.results = queue.Queue()
        self.is_busy = False
        self.action_buttons = []
        self.waveform = None
        self.live_waveform = False
        self.live_after_id = None

        try:
            self.backends = list_backends()
        except Exception as error:
            messagebox.showerror("VISA Backend Error", str(error), parent=root)
            root.destroy()
            return

        if not self.backends:
            messagebox.showerror(
                "VISA Backend Error",
                "No PyVISA backends are installed.",
                parent=root,
            )
            root.destroy()
            return

        self.backend_var = tk.StringVar(value=self.backends[0])
        self.resource_var = tk.StringVar()
        self.library_var = tk.StringVar(value="Not connected")
        self.status_var = tk.StringVar(value="Ready")

        self._build_connection_panel()
        self._build_tabs()
        self._refresh_resources()
        self.root.after(100, self._check_results)

    def _build_connection_panel(self):
        frame = ttk.LabelFrame(self.root, text="VISA Connection", padding=10)
        frame.grid(row=0, column=0, sticky="ew", padx=12, pady=(12, 6))
        frame.columnconfigure(1, weight=1)
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(1, weight=1)

        ttk.Label(frame, text="Backend:").grid(row=0, column=0, sticky="w", padx=4, pady=3)
        backend_state = "readonly" if len(self.backends) > 1 else "disabled"
        self.backend_combo = ttk.Combobox(
            frame,
            textvariable=self.backend_var,
            values=self.backends,
            state=backend_state,
        )
        self.backend_combo.grid(row=0, column=1, sticky="ew", padx=4, pady=3)
        self.backend_combo.bind("<<ComboboxSelected>>", self._refresh_resources)

        ttk.Label(frame, text="VISA library:").grid(
            row=1, column=0, sticky="w", padx=4, pady=3
        )
        ttk.Label(frame, textvariable=self.library_var).grid(
            row=1, column=1, columnspan=2, sticky="w", padx=4, pady=3
        )

        ttk.Label(frame, text="Instrument:").grid(
            row=2, column=0, sticky="w", padx=4, pady=3
        )
        self.resource_combo = ttk.Combobox(
            frame, textvariable=self.resource_var, state="readonly"
        )
        self.resource_combo.grid(row=2, column=1, sticky="ew", padx=4, pady=3)
        refresh_button = ttk.Button(
            frame, text="Refresh Resources", command=self._refresh_resources
        )
        refresh_button.grid(row=2, column=2, padx=4, pady=3)
        self.action_buttons.append(refresh_button)

    def _build_tabs(self):
        notebook = ttk.Notebook(self.root)
        notebook.grid(row=1, column=0, sticky="nsew", padx=12, pady=6)

        self.status_tab = ttk.Frame(notebook, padding=12)
        self.measurement_tab = ttk.Frame(notebook, padding=12)
        self.settings_tab = ttk.Frame(notebook, padding=12)
        self.waveform_tab = ttk.Frame(notebook, padding=12)
        notebook.add(self.status_tab, text="Status")
        notebook.add(self.measurement_tab, text="Measurements")
        notebook.add(self.settings_tab, text="Settings")
        notebook.add(self.waveform_tab, text="Waveform")

        self._build_status_tab()
        self._build_measurement_tab()
        self._build_settings_tab()
        self._build_waveform_tab()

        ttk.Label(self.root, textvariable=self.status_var, anchor="w").grid(
            row=2, column=0, sticky="ew", padx=16, pady=(2, 10)
        )

    def _add_action_button(self, parent, text, command, **grid_options):
        button = ttk.Button(parent, text=text, command=command)
        button.grid(**grid_options)
        self.action_buttons.append(button)
        return button

    def _build_status_tab(self):
        self.status_tab.columnconfigure(0, weight=1)
        self.status_tab.rowconfigure(1, weight=1)
        self._add_action_button(
            self.status_tab,
            "Read Status",
            self._read_status,
            row=0,
            column=0,
            sticky="w",
            pady=(0, 10),
        )
        self.status_text = self._create_output(self.status_tab, row=1)

    def _build_measurement_tab(self):
        self.measurement_tab.columnconfigure(1, weight=1)
        self.measurement_tab.rowconfigure(2, weight=1)
        self.measurement_channel = tk.StringVar(value="1")
        ttk.Label(self.measurement_tab, text="Channel:").grid(
            row=0, column=0, sticky="w", padx=(0, 8), pady=4
        )
        ttk.Combobox(
            self.measurement_tab,
            textvariable=self.measurement_channel,
            values=("1", "2"),
            state="readonly",
            width=8,
        ).grid(row=0, column=1, sticky="w", pady=4)
        self._add_action_button(
            self.measurement_tab,
            "Measure Vpp and Frequency",
            self._read_measurements,
            row=1,
            column=0,
            columnspan=2,
            sticky="w",
            pady=(8, 10),
        )
        self.measurement_text = self._create_output(self.measurement_tab, row=2)

    def _build_settings_tab(self):
        self.settings_tab.columnconfigure(1, weight=1)
        self.settings_channel = tk.StringVar(value="1")
        self.scale_var = tk.StringVar()
        self.timebase_var = tk.StringVar()

        ttk.Label(self.settings_tab, text="Channel:").grid(
            row=0, column=0, sticky="w", padx=4, pady=5
        )
        ttk.Combobox(
            self.settings_tab,
            textvariable=self.settings_channel,
            values=("1", "2"),
            state="readonly",
            width=8,
        ).grid(row=0, column=1, sticky="w", padx=4, pady=5)

        ttk.Label(self.settings_tab, text="Channel scale (V/div):").grid(
            row=1, column=0, sticky="w", padx=4, pady=5
        )
        ttk.Entry(self.settings_tab, textvariable=self.scale_var).grid(
            row=1, column=1, sticky="ew", padx=4, pady=5
        )
        ttk.Label(self.settings_tab, text="Timebase scale (s/div):").grid(
            row=2, column=0, sticky="w", padx=4, pady=5
        )
        ttk.Entry(self.settings_tab, textvariable=self.timebase_var).grid(
            row=2, column=1, sticky="ew", padx=4, pady=5
        )
        self.read_settings_button = self._add_action_button(
            self.settings_tab,
            "Read Current Settings",
            self._read_settings,
            row=3,
            column=0,
            sticky="w",
            padx=4,
            pady=(10, 4),
        )
        self.apply_settings_button = self._add_action_button(
            self.settings_tab,
            "Apply Settings",
            self._apply_settings,
            row=3,
            column=1,
            sticky="w",
            padx=4,
            pady=(10, 4),
        )
        ttk.Label(
            self.settings_tab,
            text="Changing these values will modify the oscilloscope settings.",
            wraplength=560,
        ).grid(row=4, column=0, columnspan=2, sticky="w", padx=4, pady=8)

    def _build_waveform_tab(self):
        self.waveform_tab.columnconfigure(1, weight=1)
        self.waveform_tab.rowconfigure(2, weight=1)
        self.waveform_channel = tk.StringVar(value="1")
        selection_controls = ttk.Frame(self.waveform_tab)
        selection_controls.grid(
            row=0, column=0, columnspan=2, sticky="ew", pady=4
        )
        ttk.Label(selection_controls, text="Channel:").pack(
            side="left", padx=(0, 8)
        )
        self.waveform_channel_combo = ttk.Combobox(
            selection_controls,
            textvariable=self.waveform_channel,
            values=("1", "2", "Both"),
            state="readonly",
            width=8,
        )
        self.waveform_channel_combo.pack(side="left")
        self.waveform_background = tk.StringVar(value="White")
        ttk.Label(selection_controls, text="Background:").pack(
            side="left", padx=(20, 8)
        )
        self.background_combo = ttk.Combobox(
            selection_controls,
            textvariable=self.waveform_background,
            values=("White", "Black"),
            state="readonly",
            width=8,
        )
        self.background_combo.pack(side="left")
        self.background_combo.bind(
            "<<ComboboxSelected>>", self._change_waveform_background
        )
        self._add_action_button(
            self.waveform_tab,
            "Fetch and Plot Waveform",
            self._fetch_waveform,
            row=1,
            column=0,
            sticky="w",
            pady=(8, 8),
        )
        controls = ttk.Frame(self.waveform_tab)
        controls.grid(row=1, column=1, sticky="e", pady=(8, 8))
        self.live_interval = tk.StringVar(value="1")
        ttk.Label(controls, text="Update interval (s):").pack(
            side="left", padx=(0, 4)
        )
        self.live_interval_combo = ttk.Combobox(
            controls,
            textvariable=self.live_interval,
            values=("0.05", "0.1", "0.5", "1", "2", "5"),
            state="readonly",
            width=5,
        )
        self.live_interval_combo.pack(side="left", padx=(0, 6))
        self.live_start_button = ttk.Button(
            controls,
            text="Start Live",
            command=self._start_live_waveform,
        )
        self.live_start_button.pack(side="left", padx=3)
        self.live_stop_button = ttk.Button(
            controls,
            text="Stop Live",
            command=self._stop_live_waveform,
            state="disabled",
        )
        self.live_stop_button.pack(side="left", padx=3)
        self.save_button = ttk.Button(
            controls, text="Save CSV", command=self._save_waveform_csv
        )
        self.save_button.pack(side="left", padx=(6, 0))
        self.action_buttons.append(self.save_button)
        self.save_button.configure(state="disabled")
        self.waveform_canvas = tk.Canvas(
            self.waveform_tab,
            background="#ffffff",
            highlightthickness=1,
            highlightbackground="#a0a0a0",
        )
        self.waveform_canvas.grid(row=2, column=0, columnspan=2, sticky="nsew")
        self.waveform_canvas.bind("<Configure>", self._draw_waveform)
        self.waveform_info_var = tk.StringVar(value="No waveform loaded.")
        ttk.Label(self.waveform_tab, textvariable=self.waveform_info_var).grid(
            row=3, column=0, columnspan=2, sticky="w", pady=(6, 0)
        )

    def _change_waveform_background(self, _event=None):
        palette = self._waveform_palette()
        self.waveform_canvas.configure(
            background=palette["background"],
            highlightbackground=palette["border"],
        )
        self._draw_waveform()

    def _waveform_palette(self):
        if self.waveform_background.get() == "Black":
            return {
                "background": "#000000",
                "grid": "#404040",
                "text": "#d0d0d0",
                "border": "#808080",
            }
        return {
            "background": "#ffffff",
            "grid": "#e0e0e0",
            "text": "#303030",
            "border": "#a0a0a0",
        }

    @staticmethod
    def _create_output(parent, row):
        output = tk.Text(parent, height=12, wrap="word", state="disabled")
        output.grid(row=row, column=0, sticky="nsew")
        return output

    @staticmethod
    def _set_output(widget, value):
        widget.configure(state="normal")
        widget.delete("1.0", tk.END)
        widget.insert("1.0", value)
        widget.configure(state="disabled")

    def _refresh_resources(self, _event=None):
        manager = None
        try:
            manager = pyvisa.ResourceManager(f"@{self.backend_var.get()}")
            resources = manager.list_resources()
            self.library_var.set(str(manager.visalib))
            self.resource_combo["values"] = resources
            self.resource_var.set(resources[0] if resources else "")
            self.status_var.set(
                f"Found {len(resources)} VISA resource(s)."
                if resources
                else "No VISA instruments found."
            )
        except Exception as error:
            self.library_var.set("Unavailable")
            self.resource_combo["values"] = ()
            self.resource_var.set("")
            self.status_var.set("Could not list VISA resources.")
            messagebox.showerror("VISA Error", str(error), parent=self.root)
        finally:
            if manager is not None:
                manager.close()

    def _read_status(self):
        def operation(instrument):
            channel_1_scale = instrument.query(":CHANnel1:SCALe?").strip()
            channel_2_scale = instrument.query(":CHANnel2:SCALe?").strip()
            timebase_scale = instrument.query(":TIMebase:SCALe?").strip()
            error = instrument.query(":SYSTem:ERRor?").strip()
            return (
                f"Channel 1 scale: {channel_1_scale} V/div\n"
                f"Channel 2 scale: {channel_2_scale} V/div\n"
                f"Timebase scale: {timebase_scale} s/div\n"
                f"Instrument error queue: {error}"
            )

        self._start_task("Reading instrument status", operation, self.status_text)

    def _read_measurements(self):
        channel = self.measurement_channel.get()

        def operation(instrument):
            source = f"CHANnel{channel}"
            vpp = instrument.query(f":MEASure:VPP? {source}").strip()
            frequency = instrument.query(f":MEASure:FREQuency? {source}").strip()
            return (
                f"Channel {channel}\n"
                f"Vpp: {self._format_measurement(vpp, 'V')}\n"
                f"Frequency: {self._format_measurement(frequency, 'Hz')}"
            )

        self._start_task("Measuring signal", operation, self.measurement_text)

    @staticmethod
    def _format_measurement(value, unit):
        try:
            numeric_value = float(value)
        except ValueError:
            return f"{value} {unit}"
        if not math.isfinite(numeric_value) or abs(numeric_value) >= 1e36:
            return "N/A (no valid measurement)"
        return f"{value} {unit}"

    def _read_settings(self):
        channel = self.settings_channel.get()

        def operation(instrument):
            scale = instrument.query(f":CHANnel{channel}:SCALe?").strip()
            timebase = instrument.query(":TIMebase:SCALe?").strip()
            return scale, timebase

        self._start_task(
            "Reading settings",
            operation,
            on_success=lambda values: self._show_settings(values, channel),
        )

    def _show_settings(self, values, channel):
        scale, timebase = values
        self.scale_var.set(scale)
        self.timebase_var.set(timebase)
        self.status_var.set(f"Read settings for channel {channel}.")

    def _apply_settings(self):
        channel = self.settings_channel.get()
        try:
            scale = float(self.scale_var.get())
            timebase = float(self.timebase_var.get())
            if not math.isfinite(scale) or scale <= 0:
                raise ValueError("Channel scale must be a positive finite number.")
            if not math.isfinite(timebase) or timebase <= 0:
                raise ValueError("Timebase scale must be a positive finite number.")
        except ValueError as error:
            messagebox.showerror("Invalid Settings", str(error), parent=self.root)
            return

        if not messagebox.askyesno(
            "Confirm Instrument Changes",
            f"Apply these settings to the oscilloscope?\n\n"
            f"Channel {channel} scale: {scale:g} V/div\n"
            f"Timebase scale: {timebase:g} s/div",
            parent=self.root,
        ):
            return

        def operation(instrument):
            instrument.write(f":CHANnel{channel}:SCALe {scale:.12g}")
            instrument.write(f":TIMebase:SCALe {timebase:.12g}")
            actual_scale = instrument.query(f":CHANnel{channel}:SCALe?").strip()
            actual_timebase = instrument.query(":TIMebase:SCALe?").strip()
            error = instrument.query(":SYSTem:ERRor?").strip()
            return actual_scale, actual_timebase, error

        self._start_task(
            "Applying settings",
            operation,
            on_success=lambda values: self._settings_applied(values, channel),
        )

    def _settings_applied(self, values, channel):
        scale, timebase, error = values
        self.scale_var.set(scale)
        self.timebase_var.set(timebase)
        self.status_var.set(f"Applied settings to channel {channel}.")
        try:
            error_code = float(error.partition(",")[0].strip())
        except ValueError:
            error_code = None
        if error_code != 0:
            messagebox.showwarning(
                "Instrument Error",
                f"The instrument reported an error after applying settings:\n{error}",
                parent=self.root,
            )

    def _fetch_waveform(self):
        selection = self.waveform_channel.get()
        channels = ("1", "2") if selection == "Both" else (selection,)

        def operation(instrument):
            previous_source = instrument.query(":WAVeform:SOURce?").strip()
            previous_format = instrument.query(":WAVeform:FORMat?").strip()
            try:
                instrument.write(":WAVeform:FORMat BYTE")
                timebase_scale = float(instrument.query(":TIMebase:SCALe?"))
                time_position = float(instrument.query(":TIMebase:POSition?"))
                channel_data = {}
                for channel in channels:
                    instrument.write(f":WAVeform:SOURce CHANnel{channel}")
                    preamble = instrument.query_ascii_values(":WAVeform:PREamble?")
                    if len(preamble) < 10:
                        raise ValueError(
                            f"Unexpected channel {channel} waveform preamble: "
                            f"expected 10 fields, got {len(preamble)}."
                        )

                    points = instrument.query_binary_values(
                        ":WAVeform:DATA?",
                        datatype="B",
                        container=list,
                        header_fmt="ieee",
                    )
                    if not points:
                        raise ValueError(
                            f"The instrument returned no waveform points for channel {channel}."
                        )

                    channel_scale = float(
                        instrument.query(f":CHANnel{channel}:SCALe?")
                    )
                    channel_offset = float(
                        instrument.query(f":CHANnel{channel}:OFFSet?")
                    )
                    x_increment, x_origin, x_reference = preamble[4:7]
                    y_increment, y_origin, y_reference = preamble[7:10]
                    times = [
                        (index - x_reference) * x_increment + x_origin
                        for index in range(len(points))
                    ]
                    volts = [
                        (value - y_reference) * y_increment + y_origin
                        for value in points
                    ]
                    channel_data[channel] = {
                        "times": times,
                        "volts": volts,
                        "scale": channel_scale,
                        "offset": channel_offset,
                    }

                return {
                    "channels": channel_data,
                    "timebase_scale": timebase_scale,
                    "time_position": time_position,
                }
            finally:
                instrument.write(f":WAVeform:SOURce {previous_source}")
                instrument.write(f":WAVeform:FORMat {previous_format}")

        label = "Updating live waveform" if self.live_waveform else "Fetching waveform data"
        self.waveform_info_var.set(f"{label} ...")
        self._start_task(
            label,
            operation,
            on_success=self._waveform_received,
        )

    def _waveform_received(self, result):
        self.waveform = result
        channels = result["channels"]
        channel_labels = ", ".join(
            f"CH{channel} ({len(data['times'])} points, {data['scale']:g} V/div)"
            for channel, data in channels.items()
        )
        timebase_scale = result["timebase_scale"]
        self.waveform_info_var.set(
            f"{channel_labels}, {timebase_scale:g} s/div."
        )
        self.save_button.configure(state="normal")
        self._draw_waveform()
        if self.live_waveform:
            self.waveform_info_var.set(
                f"Live: {channel_labels}, {timebase_scale:g} s/div."
            )
            self.status_var.set("Live waveform updated.")
            interval_ms = int(float(self.live_interval.get()) * 1000)
            self.live_after_id = self.root.after(
                interval_ms, self._live_refresh
            )

    def _live_refresh(self):
        self.live_after_id = None
        if not self.live_waveform:
            return
        if self.is_busy:
            self.live_after_id = self.root.after(50, self._live_refresh)
            return
        self._fetch_waveform()

    def _start_live_waveform(self):
        if self.is_busy or not self.resource_var.get():
            if not self.resource_var.get():
                messagebox.showwarning(
                    "No Instrument Selected",
                    "Select a VISA instrument before starting live waveform display.",
                    parent=self.root,
                )
            return
        self.live_waveform = True
        self.live_interval_combo.configure(state="disabled")
        self.waveform_channel_combo.configure(state="disabled")
        self.resource_combo.configure(state="disabled")
        self.backend_combo.configure(state="disabled")
        self._update_live_button_states()
        self._update_action_button_states()
        self.status_var.set("Starting live waveform display ...")
        self._fetch_waveform()

    def _stop_live_waveform(self):
        self.live_waveform = False
        if self.live_after_id is not None:
            self.root.after_cancel(self.live_after_id)
            self.live_after_id = None
        self.live_interval_combo.configure(state="readonly")
        self.waveform_channel_combo.configure(state="readonly")
        self.resource_combo.configure(state="readonly")
        self.backend_combo.configure(
            state="readonly" if len(self.backends) > 1 else "disabled"
        )
        self._update_live_button_states()
        self._update_action_button_states()
        if not self.is_busy:
            self.status_var.set("Live waveform display stopped.")
            if self.waveform is not None:
                channels = ", ".join(
                    f"CH{channel}"
                    for channel in self.waveform["channels"]
                )
                self.waveform_info_var.set(
                    f"Stopped: {channels}."
                )

    def _draw_waveform(self, _event=None):
        canvas = self.waveform_canvas
        canvas.delete("all")
        palette = self._waveform_palette()
        canvas.configure(
            background=palette["background"],
            highlightbackground=palette["border"],
        )
        if self.waveform is None:
            return

        channels = self.waveform["channels"]
        timebase_scale = self.waveform["timebase_scale"]
        time_position = self.waveform["time_position"]
        width = max(canvas.winfo_width(), 2)
        height = max(canvas.winfo_height(), 2)
        left, right, top, bottom = 86, width - 18, 24, height - 54
        if right <= left or bottom <= top:
            return

        time_start = time_position - 5 * timebase_scale
        time_end = time_position + 5 * timebase_scale
        time_span = time_end - time_start

        for division in range(11):
            x = left + (right - left) * division / 10
            canvas.create_line(x, top, x, bottom, fill=palette["grid"])
            if division % 2 == 0:
                tick_time = time_start + time_span * division / 10
                canvas.create_text(
                    x,
                    bottom + 16,
                    text=f"{tick_time:.3g}",
                    fill=palette["text"],
                )
        for division in range(9):
            y = top + (bottom - top) * division / 8
            canvas.create_line(left, y, right, y, fill=palette["grid"])
            for channel, label_x, anchor in (
                (next(iter(channels)), left - 8, "e"),
                (next(reversed(channels)), right + 8, "w"),
            ):
                if label_x == right + 8 and len(channels) == 1:
                    continue
                data = channels[channel]
                voltage = data["offset"] + (
                    4 - division
                ) * data["scale"]
                canvas.create_text(
                    label_x,
                    y,
                    text=f"{voltage:.3g}",
                    anchor=anchor,
                    fill=self._channel_color(
                        channel, self.waveform_background.get()
                    ),
                )
        canvas.create_rectangle(
            left, top, right, bottom, outline=palette["border"]
        )
        for channel, data in channels.items():
            times = data["times"]
            volts = data["volts"]
            voltage_min = data["offset"] - 4 * data["scale"]
            voltage_span = 8 * data["scale"]
            stride = max(1, len(volts) // 5000)
            coordinates = []
            for index in range(0, len(volts), stride):
                x = left + (times[index] - time_start) / time_span * (right - left)
                y = top + (voltage_min + 8 * data["scale"] - volts[index]) / voltage_span * (bottom - top)
                coordinates.extend((x, y))
            if len(volts) > 1 and (len(volts) - 1) % stride:
                index = len(volts) - 1
                x = left + (times[index] - time_start) / time_span * (right - left)
                y = top + (voltage_min + 8 * data["scale"] - volts[index]) / voltage_span * (bottom - top)
                coordinates.extend((x, y))
            if len(coordinates) >= 4:
                canvas.create_line(
                    *coordinates,
                    fill=self._channel_color(
                        channel, self.waveform_background.get()
                    ),
                    width=1.5,
                )
            canvas.create_text(
                left + 52 + (int(channel) - 1) * 74,
                top + 10,
                text=f"CH{channel}",
                fill=self._channel_color(
                    channel, self.waveform_background.get()
                ),
                anchor="w",
            )

        canvas.create_text(
            (left + right) / 2,
            height - 16,
            text=f"Time (s), {timebase_scale:g} s/div",
            fill=palette["text"],
        )
        canvas.create_text(
            left - 12,
            (top + bottom) / 2,
            text=f"CH{next(iter(channels))} Voltage (V)",
            angle=90,
            fill=palette["text"],
        )
        if len(channels) > 1:
            canvas.create_text(
                right + 22,
                (top + bottom) / 2,
                text=f"CH{next(reversed(channels))} Voltage (V)",
                angle=90,
                fill=palette["text"],
            )

    def _save_waveform_csv(self):
        if self.waveform is None:
            return
        path = filedialog.asksaveasfilename(
            parent=self.root,
            title="Save waveform data",
            defaultextension=".csv",
            filetypes=(("CSV files", "*.csv"), ("All files", "*.*")),
        )
        if not path:
            return

        try:
            with open(path, "w", newline="", encoding="utf-8") as csv_file:
                writer = csv.writer(csv_file)
                channels = self.waveform["channels"]
                first_channel = next(iter(channels.values()))
                headers = ["Time (s)"]
                for channel in channels:
                    headers.append(f"Channel {channel} Voltage (V)")
                writer.writerow(headers)
                rows = [first_channel["times"]]
                rows.extend(data["volts"] for data in channels.values())
                writer.writerows(zip(*rows))
        except OSError as error:
            messagebox.showerror("CSV Save Error", str(error), parent=self.root)
            return
        self.status_var.set(f"Saved waveform data to {path}")

    @staticmethod
    def _channel_color(channel, background):
        if background == "Black":
            return {"1": "#ffff00", "2": "#00ff00"}[channel]
        return {"1": "#b88600", "2": "#008000"}[channel]

    def _start_task(self, label, operation, output_widget=None, on_success=None):
        if self.is_busy:
            return
        backend = self.backend_var.get()
        resource = self.resource_var.get()
        if not resource:
            messagebox.showwarning(
                "No Instrument Selected",
                "Select a VISA instrument before starting a test.",
                parent=self.root,
            )
            return
        self.is_busy = True
        self.is_busy = True
        self._update_live_button_states()
        self._update_action_button_states()
        self.status_var.set(f"{label} ...")
        if output_widget is not None:
            self._set_output(output_widget, "")

        threading.Thread(
            target=self._run_task,
            args=(backend, resource, label, operation, output_widget, on_success),
            daemon=True,
        ).start()

    def _run_task(self, backend, resource, label, operation, output_widget, on_success):
        manager = None
        instrument = None
        result = None
        error_message = None
        try:
            manager = pyvisa.ResourceManager(f"@{backend}")
            instrument = manager.open_resource(resource)
            instrument.timeout = 10000
            result = operation(instrument)
        except Exception as error:
            error_message = str(error)
        finally:
            for handle in (instrument, manager):
                if handle is not None:
                    try:
                        handle.close()
                    except Exception as error:
                        if error_message is None:
                            error_message = f"Failed to close VISA connection: {error}"

        self.results.put(
            (label, result, error_message, output_widget, on_success)
        )

    def _check_results(self):
        try:
            label, result, error, output_widget, on_success = self.results.get_nowait()
        except queue.Empty:
            pass
        else:
            self.is_busy = False
            self._update_live_button_states()
            self._update_action_button_states()
            self.status_var.set(f"{label} failed." if error else f"{label} completed.")
            if error:
                messagebox.showerror("VISA Operation Error", error, parent=self.root)
                if self.live_waveform and label == "Updating live waveform":
                    self._stop_live_waveform()
            elif on_success is not None:
                on_success(result)
            elif output_widget is not None:
                self._set_output(output_widget, result)

            if label == "Updating live waveform" and not self.live_waveform and not error:
                self.status_var.set("Live waveform display stopped.")
        self.root.after(100, self._check_results)

    def _update_action_button_states(self):
        for button in self.action_buttons:
            if self.is_busy:
                state = "disabled"
            elif self.live_waveform:
                state = (
                    "normal"
                    if button in (self.read_settings_button, self.apply_settings_button)
                    or (button is self.save_button and self.waveform)
                    else "disabled"
                )
            elif button is self.save_button:
                state = "normal" if self.waveform is not None else "disabled"
            else:
                state = "normal"
            button.configure(state=state)

    def _update_live_button_states(self):
        if self.live_waveform:
            start_state, stop_state = "disabled", "normal"
        elif self.is_busy:
            start_state, stop_state = "disabled", "disabled"
        else:
            start_state, stop_state = "normal", "disabled"
        self.live_start_button.configure(state=start_state)
        self.live_stop_button.configure(state=stop_state)


def main():
    root = tk.Tk()
    ScopeToolsApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
