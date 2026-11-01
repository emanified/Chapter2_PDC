"""
Chapter 2 Project: Threaded Pizza Kitchen
-----------------------------------------
Producer/consumer simulation that uses every recipe from Chapter 2:

  * Defining a thread / current thread  -> threading.current_thread().name in logs
  * Thread subclass     -> Customer, Cook, Waiter extend Thread
  * Lock                -> log output and the finished-pizza counter
  * RLock               -> Ledger: record_sale() calls add_to_total(), both lock
  * Semaphore           -> only N_OVENS ovens available
  * Condition           -> Waiter sleeps until cooks put a pizza on the shelf
  * Event               -> "kitchen closed" signal
  * Barrier             -> all cooks start the shift together
  * Queue               -> orders flow from customers to cooks

Run:  python kitchen.py
"""
import queue
import random
import threading
import time

N_COOKS = 3
N_CUSTOMERS = 4
ORDERS_PER_CUSTOMER = 3
N_OVENS = 2
PRICES = {"Margherita": 8.0, "Pepperoni": 10.0, "Veggie": 9.0}

orders = queue.Queue()                        # Queue
ovens = threading.Semaphore(N_OVENS)          # Semaphore
shift_start = threading.Barrier(N_COOKS)      # Barrier
kitchen_closed = threading.Event()            # Event
log_lock = threading.Lock()                   # Lock
counter_lock = threading.Lock()               # Lock
cooked_count = 0

shelf = []                                    # ready pizzas
shelf_cond = threading.Condition()            # Condition


def log(msg):
    with log_lock:
        print(f"[{time.strftime('%H:%M:%S')}] "
              f"{threading.current_thread().name:<11} {msg}")


class Ledger:
    """RLock demo: record_sale() holds the lock and calls add_to_total(),
    which locks again. A plain Lock would deadlock here; RLock does not."""

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


ledger = Ledger()


class Customer(threading.Thread):
    def __init__(self, name):
        super().__init__(name=name)

    def run(self):
        for n in range(1, ORDERS_PER_CUSTOMER + 1):
            time.sleep(random.uniform(0.1, 0.5))
            pizza = random.choice(list(PRICES))
            orders.put((self.name, pizza))
            log(f"ordered {pizza} (#{n})")


class Cook(threading.Thread):
    def __init__(self, name):
        super().__init__(name=name)

    def run(self):
        global cooked_count
        log("waiting for other cooks...")
        shift_start.wait()
        while not (kitchen_closed.is_set() and orders.empty()):
            try:
                customer, pizza = orders.get(timeout=0.3)
            except queue.Empty:
                continue
            with ovens:
                log(f"baking {pizza} for {customer}")
                time.sleep(random.uniform(0.3, 0.8))
            with counter_lock:
                cooked_count += 1
            with shelf_cond:                       # hand over to the waiter
                shelf.append((customer, pizza))
                shelf_cond.notify()
            orders.task_done()
        log("going home")


class Waiter(threading.Thread):
    """Waits on the Condition until a pizza is on the shelf, then serves it."""

    def __init__(self, name):
        super().__init__(name=name)

    def run(self):
        while True:
            with shelf_cond:
                while not shelf:
                    if kitchen_closed.is_set() and orders.unfinished_tasks == 0:
                        return
                    shelf_cond.wait(timeout=0.3)
                customer, pizza = shelf.pop(0)
            ledger.record_sale(pizza)
            log(f"served {pizza} to {customer}")


def main():
    cooks = [Cook(f"Cook-{i}") for i in range(1, N_COOKS + 1)]
    customers = [Customer(f"Customer-{i}") for i in range(1, N_CUSTOMERS + 1)]
    waiter = Waiter("Waiter")

    start = time.perf_counter()
    for t in cooks + customers + [waiter]:
        t.start()

    for c in customers:
        c.join()
    kitchen_closed.set()
    orders.join()
    for c in cooks:
        c.join()
    waiter.join()

    expected = N_CUSTOMERS * ORDERS_PER_CUSTOMER
    print("\n----- End of day report -----")
    print(f"Orders expected : {expected}")
    print(f"Pizzas cooked   : {cooked_count}")
    print(f"Pizzas served   : {ledger.sales}")
    print(f"Revenue         : ${ledger.total:.2f}")
    print(f"Wall-clock time : {time.perf_counter() - start:.2f}s")
    assert cooked_count == ledger.sales == expected, "lost an order!"


if __name__ == "__main__":
    main()
