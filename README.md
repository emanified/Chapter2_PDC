# Threaded Pizza Kitchen

A thread-based parallelism project built from the recipes in Chapter 2 of
*Python Parallel Programming Cookbook* (Thread-Based Parallelism).

A restaurant simulation where customers place orders, cooks bake them in a
limited number of ovens, and a waiter serves the finished pizzas.

## Chapter 2 concepts used

| Recipe | Where it appears |
|---|---|
| Defining a thread / current thread | `threading.current_thread().name` in every log line |
| Thread subclass | `Customer`, `Cook`, `Waiter` extend `Thread` |
| Lock | log output and shared counters |
| RLock | `Ledger.record_sale()` calls `add_to_total()` (nested locking) |
| Semaphore | only N ovens are available |
| Condition | `Waiter` sleeps until a cook puts a pizza on the shelf |
| Event | "kitchen closed" signal |
| Barrier | all cooks start the shift together |
| Queue | orders flow from customers to cooks |

## Run

Requires Python 3.8+ (no extra packages).

```bash
python kitchen.py       # console version
python kitchen_gui.py   # Tkinter interface
```

On some Linux systems the GUI needs `sudo apt install python3-tk`.

## Files

- `kitchen.py` – console simulation
- `kitchen_gui.py` – GUI version (worker threads send messages through a
  `Queue`; only the main thread touches Tkinter widgets)

## How it is verified

Each run checks that `cooked == served == orders placed`, so a lost order
(race condition) would fail the run.
