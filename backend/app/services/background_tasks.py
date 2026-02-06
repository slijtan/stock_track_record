import threading
from typing import Callable
from queue import Queue
import traceback


class BackgroundTaskRunner:
    """Simple background task runner for local development."""

    def __init__(self):
        self._queue: Queue = Queue()
        self._worker_thread: threading.Thread | None = None
        self._running = False

    def start(self):
        """Start the background worker thread."""
        if self._running:
            return
        self._running = True
        self._worker_thread = threading.Thread(target=self._worker, daemon=True)
        self._worker_thread.start()

    def stop(self):
        """Stop the background worker thread."""
        self._running = False
        self._queue.put(None)  # Signal to stop

    def submit(self, func: Callable, *args, **kwargs):
        """Submit a task to be executed in the background."""
        self._queue.put((func, args, kwargs))

    def _worker(self):
        """Worker thread that processes tasks from the queue."""
        while self._running:
            try:
                item = self._queue.get()
                if item is None:
                    break
                func, args, kwargs = item
                try:
                    func(*args, **kwargs)
                except Exception as e:
                    print(f"Background task error: {e}")
                    traceback.print_exc()
            except Exception as e:
                print(f"Worker error: {e}")


# Global task runner instance
task_runner = BackgroundTaskRunner()


def get_task_runner() -> BackgroundTaskRunner:
    """Get the global task runner instance."""
    return task_runner


def start_background_runner():
    """Start the background task runner."""
    task_runner.start()


def submit_task(func: Callable, *args, **kwargs):
    """Submit a task to the background runner."""
    task_runner.submit(func, *args, **kwargs)
