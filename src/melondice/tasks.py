"""Cancellable background network loop; callbacks run on the terminal UI thread."""
from __future__ import annotations

import asyncio
import queue
import threading


class Tasks:
    def __init__(self):
        self.events = queue.Queue()
        self.loop = asyncio.new_event_loop()
        self.futures = set()
        self.closed = False
        self.thread = threading.Thread(target=self._run, name="melondice-network", daemon=True)
        self.thread.start()

    def _run(self):
        asyncio.set_event_loop(self.loop)
        self.loop.run_forever()
        pending = asyncio.all_tasks(self.loop)
        for task in pending:
            task.cancel()
        if pending:
            self.loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
        self.loop.run_until_complete(self.loop.shutdown_asyncgens())
        self.loop.run_until_complete(self.loop.shutdown_default_executor())
        self.loop.close()

    def post(self, callback, *args):
        self.events.put((callback, args))

    def submit(self, coroutine, done=None):
        future = asyncio.run_coroutine_threadsafe(coroutine, self.loop)
        self.futures.add(future)

        def complete(f):
            self.events.put((self.futures.discard, (f,)))
            if done:
                self.events.put((done, (f,)))

        future.add_done_callback(complete)
        return future

    def drain(self, stop=None):
        for _ in range(250):
            if stop and stop():
                return
            try:
                callback, args = self.events.get_nowait()
            except queue.Empty:
                return
            callback(*args)

    def close(self):
        if self.closed:
            return
        self.closed = True
        for future in tuple(self.futures):
            future.cancel()
        if not self.loop.is_closed():
            self.loop.call_soon_threadsafe(self.loop.stop)
        self.thread.join(timeout=5)
