import queue
import threading
import tkinter as tk
from tkinter import messagebox, ttk

import pyvisa
from pyvisa.highlevel import list_backends


class ScopeApp:
    def __init__(self, root):
        self.root = root
        self.root.title("VISA Test")
        self.root.minsize(560, 300)
        self.results = queue.Queue()
        self.is_querying = False

        try:
            self.backends = list_backends()
        except Exception as error:
            messagebox.showerror("VISA Backend Error", str(error), parent=self.root)
            self.root.destroy()
            return

        if not self.backends:
            messagebox.showerror(
                "VISA Backend Error",
                "No PyVISA backends are installed.",
                parent=self.root,
            )
            self.root.destroy()
            return

        self.backend_var = tk.StringVar(value=self.backends[0])
        self.resource_var = tk.StringVar()
        self.library_var = tk.StringVar(value="Not connected")
        self.status_var = tk.StringVar(value="Ready")

        frame = ttk.Frame(root, padding=16)
        frame.grid(row=0, column=0, sticky="nsew")
        root.columnconfigure(0, weight=1)
        root.rowconfigure(0, weight=1)
        frame.columnconfigure(1, weight=1)

        ttk.Label(frame, text="VISA backend:").grid(row=0, column=0, sticky="w", pady=4)
        backend_state = "readonly" if len(self.backends) > 1 else "disabled"
        self.backend_combo = ttk.Combobox(
            frame,
            textvariable=self.backend_var,
            values=self.backends,
            state=backend_state,
        )
        self.backend_combo.grid(row=0, column=1, sticky="ew", pady=4)
        self.backend_combo.bind("<<ComboboxSelected>>", self.refresh_resources)

        ttk.Label(frame, text="VISA library:").grid(row=1, column=0, sticky="w", pady=4)
        ttk.Label(frame, textvariable=self.library_var).grid(
            row=1, column=1, sticky="w", pady=4
        )

        ttk.Label(frame, text="Instrument:").grid(row=2, column=0, sticky="w", pady=4)
        self.resource_combo = ttk.Combobox(
            frame, textvariable=self.resource_var, state="readonly"
        )
        self.resource_combo.grid(row=2, column=1, sticky="ew", pady=4)

        self.refresh_button = ttk.Button(
            frame, text="Refresh Resources", command=self.refresh_resources
        )
        self.refresh_button.grid(row=3, column=0, sticky="w", pady=(8, 12))
        self.query_button = ttk.Button(
            frame, text="Query *IDN?", command=self.query_idn, state="disabled"
        )
        self.query_button.grid(row=3, column=1, sticky="e", pady=(8, 12))

        ttk.Label(frame, text="Status:").grid(row=4, column=0, sticky="nw", pady=4)
        ttk.Label(frame, textvariable=self.status_var).grid(
            row=4, column=1, sticky="w", pady=4
        )

        ttk.Label(frame, text="Response:").grid(row=5, column=0, sticky="nw", pady=4)
        self.response = tk.Text(frame, height=4, wrap="word", state="disabled")
        self.response.grid(row=5, column=1, sticky="nsew", pady=4)
        frame.rowconfigure(5, weight=1)

        self.refresh_resources()
        self.root.after(100, self.check_results)

    def refresh_resources(self, _event=None):
        resource_manager = None
        try:
            resource_manager = pyvisa.ResourceManager(f"@{self.backend_var.get()}")
            resources = resource_manager.list_resources()
            self.library_var.set(str(resource_manager.visalib))
            self.resource_combo["values"] = resources
            self.resource_var.set(resources[0] if resources else "")
            if resources:
                self.status_var.set(f"Found {len(resources)} VISA resource(s).")
                self.query_button.configure(state="normal")
            else:
                self.status_var.set("No VISA instruments found.")
                self.query_button.configure(state="disabled")
        except Exception as error:
            self.library_var.set("Unavailable")
            self.resource_combo["values"] = ()
            self.resource_var.set("")
            self.query_button.configure(state="disabled")
            self.status_var.set("Could not list VISA resources.")
            messagebox.showerror("VISA Error", str(error), parent=self.root)
        finally:
            if resource_manager is not None:
                resource_manager.close()

    def query_idn(self):
        resource = self.resource_var.get()
        backend = self.backend_var.get()
        if not resource or self.is_querying:
            return

        self.is_querying = True
        self.query_button.configure(state="disabled")
        self.status_var.set(f"Querying {resource} ...")
        self.set_response("")
        threading.Thread(
            target=self.run_idn_query,
            args=(backend, resource),
            daemon=True,
        ).start()

    def run_idn_query(self, backend, resource):
        resource_manager = None
        instrument = None
        try:
            resource_manager = pyvisa.ResourceManager(f"@{backend}")
            instrument = resource_manager.open_resource(resource)
            instrument.timeout = 5000
            response = instrument.query("*IDN?").strip()
            self.results.put(("success", response))
        except Exception as error:
            self.results.put(("error", str(error)))
        finally:
            if instrument is not None:
                instrument.close()
            if resource_manager is not None:
                resource_manager.close()

    def check_results(self):
        try:
            result_type, result = self.results.get_nowait()
        except queue.Empty:
            pass
        else:
            self.is_querying = False
            self.query_button.configure(state="normal")
            if result_type == "success":
                self.set_response(result)
                self.status_var.set("Query completed.")
            else:
                self.status_var.set("Query failed.")
                messagebox.showerror("VISA Query Error", result, parent=self.root)
        self.root.after(100, self.check_results)

    def set_response(self, value):
        self.response.configure(state="normal")
        self.response.delete("1.0", tk.END)
        self.response.insert("1.0", value)
        self.response.configure(state="disabled")


def main():
    root = tk.Tk()
    ScopeApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
