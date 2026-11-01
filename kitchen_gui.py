"""
Chapter 2 Project - Threaded Pizza Kitchen (GUI)
------------------------------------------------
Tkinter front-end for the kitchen simulation. Same Chapter 2 primitives:

  Thread subclass -> Customer, Cook, Waiter      Queue     -> orders
  Semaphore       -> limited ovens               Lock      -> log + counters
  RLock           -> Ledger (nested locking)     Condition -> shelf (Waiter)
  Event           -> kitchen closed              Barrier   -> cooks start together

IMPORTANT: Tkinter is not thread-safe. Worker threads never touch widgets;
they put messages on `ui_events` (a Queue) and the main thread drains it
every 50 ms with root.after().

Run:  python kitchen_gui.py
"""
import queue
import random
import threading
import time
import tkinter as tk
from tkinter import ttk

PRICES = {"Margherita": 8.0, "Pepperoni": 10.0, "Veggie": 9.0}
EMOJI = {"Margherita": "🍕", "Pepperoni": "🌶️", "Veggie": "🥦"}


class Ledger:
    """RLock demo: record_sale() -> add_to_total(), both take the same lock."""

    def __init__(self):
        self.lock = threading.RLock()
        self.total = 0.0
        self.sales = 0

    def add_to_total(self, amount):
        with self.lock:
            self.total += amount

    def record_sale(self, pizza):
        with self.lock:
            self.add_to_total(PRICES[pizza])
            self.sales += 1


class Simulation:
    """Holds every synchronisation object for ONE run of the kitchen."""

    def __init__(self, n_cooks, n_customers, n_orders, n_ovens, speed, ui_events):
        self.n_cooks, self.n_customers = n_cooks, n_customers
        self.n_orders, self.n_ovens = n_orders, n_ovens
        self.speed = speed                         # >1 = faster
        self.ui = ui_events
        self.orders = queue.Queue()                # Queue
        self.ovens = threading.Semaphore(n_ovens)  # Semaphore
        self.start_barrier = threading.Barrier(n_cooks)   # Barrier
        self.closed = threading.Event()            # Event
        self.lock = threading.Lock()               # Lock
        self.ledger = Ledger()                     # RLock inside
        self.shelf = []
        self.shelf_cond = threading.Condition()    # Condition
        self.oven_slots = [None] * n_ovens         # what each oven is baking
        self.cooked = 0
        self.ordered = 0
        self.threads = []

    def sleep(self, lo, hi):
        time.sleep(random.uniform(lo, hi) / self.speed)

    def log(self, msg):
        self.ui.put(("log", f"{threading.current_thread().name:<11} {msg}"))

    # ---- oven slot bookkeeping (guarded by the Lock) ----
    def take_oven(self, text):
        with self.lock:
            i = self.oven_slots.index(None)
            self.oven_slots[i] = text
            return i

    def free_oven(self, i):
        with self.lock:
            self.oven_slots[i] = None

    def start(self):
        cooks = [Cook(f"Cook-{i}", self) for i in range(1, self.n_cooks + 1)]
        custs = [Customer(f"Customer-{i}", self) for i in range(1, self.n_customers + 1)]
        waiter = Waiter("Waiter", self)
        self.threads = cooks + custs + [waiter]
        for t in self.threads:
            t.start()
        threading.Thread(target=self._finish, args=(custs, cooks, waiter),
                         name="Manager", daemon=True).start()

    def _finish(self, custs, cooks, waiter):
        for c in custs:
            c.join()
        self.closed.set()
        self.orders.join()
        with self.shelf_cond:
            self.shelf_cond.notify_all()
        for t in cooks + [waiter]:
            t.join()
        self.ui.put(("done", None))


class Customer(threading.Thread):
    def __init__(self, name, sim):
        super().__init__(name=name, daemon=True)
        self.sim = sim

    def run(self):
        s = self.sim
        for n in range(1, s.n_orders + 1):
            s.sleep(0.3, 1.2)
            pizza = random.choice(list(PRICES))
            s.orders.put((self.name, pizza))
            with s.lock:
                s.ordered += 1
            s.log(f"ordered {EMOJI[pizza]} {pizza} (#{n})")


class Cook(threading.Thread):
    def __init__(self, name, sim):
        super().__init__(name=name, daemon=True)
        self.sim = sim

    def run(self):
        s = self.sim
        s.log("waiting for the other cooks...")
        s.start_barrier.wait()
        s.log("shift started!")
        while not (s.closed.is_set() and s.orders.empty()):
            try:
                customer, pizza = s.orders.get(timeout=0.2)
            except queue.Empty:
                continue
            s.log(f"waiting for a free oven ({pizza})")
            with s.ovens:
                slot = s.take_oven(f"{EMOJI[pizza]} {pizza}  ({self.name})")
                s.log(f"baking {pizza} for {customer} in oven {slot + 1}")
                s.sleep(1.0, 2.5)
                s.free_oven(slot)
            with s.lock:
                s.cooked += 1
            with s.shelf_cond:
                s.shelf.append((customer, pizza))
                s.shelf_cond.notify()
            s.orders.task_done()
        s.log("going home")


class Waiter(threading.Thread):
    def __init__(self, name, sim):
        super().__init__(name=name, daemon=True)
        self.sim = sim

    def run(self):
        s = self.sim
        while True:
            with s.shelf_cond:
                while not s.shelf:
                    if s.closed.is_set() and s.orders.unfinished_tasks == 0:
                        return
                    s.shelf_cond.wait(timeout=0.2)
                customer, pizza = s.shelf.pop(0)
            s.sleep(0.2, 0.5)
            s.ledger.record_sale(pizza)
            s.log(f"served {pizza} to {customer}")


# ============================ GUI ============================
class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Threaded Pizza Kitchen - Chapter 2")
        self.geometry("820x640")
        self.minsize(760, 600)
        self.ui_events = queue.Queue()
        self.sim = None
        self.t0 = 0.0
        self._build()
        self.after(50, self._poll)

    # ---------- layout ----------
    def _build(self):
        pad = {"padx": 8, "pady": 4}

        ctl = ttk.LabelFrame(self, text="Settings")
        ctl.pack(fill="x", **pad)
        self.vars = {}
        fields = [("Cooks", "cooks", 3, 1, 8), ("Customers", "custs", 4, 1, 10),
                  ("Orders each", "orders", 3, 1, 10), ("Ovens", "ovens", 2, 1, 6)]
        for i, (label, key, default, lo, hi) in enumerate(fields):
            ttk.Label(ctl, text=label).grid(row=0, column=i * 2, padx=(10, 2), pady=6)
            v = tk.IntVar(value=default)
            self.vars[key] = v
            ttk.Spinbox(ctl, from_=lo, to=hi, width=4, textvariable=v).grid(
                row=0, column=i * 2 + 1, padx=(0, 8))
        ttk.Label(ctl, text="Speed").grid(row=1, column=0, padx=(10, 2), pady=6)
        self.speed = tk.DoubleVar(value=1.0)
        ttk.Scale(ctl, from_=0.5, to=5, variable=self.speed, length=160).grid(
            row=1, column=1, columnspan=3, sticky="w")
        self.btn = ttk.Button(ctl, text="▶ Open kitchen", command=self.start)
        self.btn.grid(row=1, column=5, columnspan=3, padx=12, sticky="e")

        mid = ttk.Frame(self)
        mid.pack(fill="x", **pad)
        self.q_label = self._panel(mid, "Order queue", 0)
        self.q_list = self._listbox(mid, 0)
        self.oven_label = self._panel(mid, "Ovens (Semaphore)", 1)
        self.oven_list = self._listbox(mid, 1)
        self.shelf_label = self._panel(mid, "Pickup shelf (Condition)", 2)
        self.shelf_list = self._listbox(mid, 2)
        for c in range(3):
            mid.columnconfigure(c, weight=1, uniform="p")

        st = ttk.LabelFrame(self, text="Statistics")
        st.pack(fill="x", **pad)
        self.stat = {}
        for i, key in enumerate(["Ordered", "Cooked", "Served", "Revenue", "Time"]):
            ttk.Label(st, text=key + ":").grid(row=0, column=i * 2, padx=(12, 2), pady=6)
            lbl = ttk.Label(st, text="-", width=8, font=("TkDefaultFont", 10, "bold"))
            lbl.grid(row=0, column=i * 2 + 1)
            self.stat[key] = lbl

        self.progress = ttk.Progressbar(self, mode="determinate")
        self.progress.pack(fill="x", **pad)

        lf = ttk.LabelFrame(self, text="Thread log (current_thread().name)")
        lf.pack(fill="both", expand=True, **pad)
        self.log = tk.Text(lf, height=10, state="disabled", font=("Courier", 9),
                           wrap="none")
        sb = ttk.Scrollbar(lf, command=self.log.yview)
        self.log.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        self.log.pack(fill="both", expand=True)

    def _panel(self, parent, title, col):
        lbl = ttk.Label(parent, text=title, font=("TkDefaultFont", 10, "bold"))
        lbl.grid(row=0, column=col, sticky="w", padx=4)
        return lbl

    def _listbox(self, parent, col):
        lb = tk.Listbox(parent, height=7, activestyle="none")
        lb.grid(row=1, column=col, sticky="ew", padx=4, pady=2)
        return lb

    # ---------- actions ----------
    def start(self):
        try:
            cooks, custs, orders, ovens = (self.vars[k].get()
                                           for k in ("cooks", "custs", "orders", "ovens"))
        except tk.TclError:
            return
        self.btn.state(["disabled"])
        self.log.configure(state="normal")
        self.log.delete("1.0", "end")
        self.log.configure(state="disabled")
        self.total_orders = custs * orders
        self.progress.configure(maximum=self.total_orders, value=0)
        self.sim = Simulation(cooks, custs, orders, ovens,
                              round(self.speed.get(), 2), self.ui_events)
        self.t0 = time.perf_counter()
        self.running = True
        self.sim.start()

    def _append_log(self, msg):
        self.log.configure(state="normal")
        self.log.insert("end", f"[{time.strftime('%H:%M:%S')}] {msg}\n")
        self.log.see("end")
        self.log.configure(state="disabled")

    def _refresh(self):
        s = self.sim
        if not s:
            return
        # snapshot lists under their own locks, then update widgets
        with s.orders.mutex:
            pending = [f"{EMOJI[p]} {p}  ({c})" for c, p in list(s.orders.queue)]
        with s.lock:
            ovens = list(s.oven_slots)
        with s.shelf_cond:
            shelf = [f"{EMOJI[p]} {p} -> {c}" for c, p in s.shelf]
        self._fill(self.q_list, pending)
        self._fill(self.oven_list,
                   [f"Oven {i + 1}: {t if t else '(free)'}" for i, t in enumerate(ovens)])
        self._fill(self.shelf_list, shelf)
        self.q_label.config(text=f"Order queue ({len(pending)})")
        busy = sum(t is not None for t in ovens)
        self.oven_label.config(text=f"Ovens (Semaphore) {busy}/{len(ovens)} busy")
        self.shelf_label.config(text=f"Pickup shelf (Condition) ({len(shelf)})")

        self.stat["Ordered"].config(text=str(s.ordered))
        self.stat["Cooked"].config(text=str(s.cooked))
        self.stat["Served"].config(text=str(s.ledger.sales))
        self.stat["Revenue"].config(text=f"${s.ledger.total:.0f}")
        if self.running:
            self.stat["Time"].config(text=f"{time.perf_counter() - self.t0:.1f}s")
        self.progress.configure(value=s.ledger.sales)

    @staticmethod
    def _fill(lb, items):
        lb.delete(0, "end")
        for it in items:
            lb.insert("end", it)

    def _poll(self):
        try:
            while True:
                kind, data = self.ui_events.get_nowait()
                if kind == "log":
                    self._append_log(data)
                elif kind == "done":
                    self.running = False
                    ok = self.sim.cooked == self.sim.ledger.sales == self.total_orders
                    self._append_log("=== Kitchen closed - all orders " +
                                     ("served, none lost ✔ ===" if ok else "NOT matched! ✘ ==="))
                    self.btn.state(["!disabled"])
        except queue.Empty:
            pass
        self._refresh()
        self.after(50, self._poll)


if __name__ == "__main__":
    App().mainloop()
