"""
Thread management utilities for proper cleanup on shutdown.

Based on MeshForge's utils/threads.py pattern.  Centralises thread
lifecycle so SIGTERM cleanly stops all background workers (TX drain,
health probes, etc.) instead of relying on daemon-flag-and-pray.

Usage:
    from src.utils.threads import get_thread_manager, shutdown_all_threads

    mgr = get_thread_manager()
    stop = threading.Event()
    mgr.start_thread("health-probe", probe_loop, args=(cfg,), stop_event=stop)

    # On shutdown
    shutdown_all_threads(timeout=5)
"""
import logging
import threading
from typing import Callable, Dict, List, Optional

log = logging.getLogger("threads")


class ThreadManager:
    """Manages long-running threads and ensures proper cleanup on shutdown."""

    def __init__(self):
        self._threads: List[threading.Thread] = []
        self._stop_events: Dict[str, threading.Event] = {}
        self._lock = threading.Lock()

    def start_thread(
        self,
        name: str,
        target: Callable,
        args: tuple = (),
        kwargs: Optional[dict] = None,
        stop_event: Optional[threading.Event] = None,
    ) -> threading.Thread:
        """Start a managed thread.

        Args:
            name:       Thread name for identification.
            target:     Function to run in thread.
            args:       Positional arguments for *target*.
            kwargs:     Keyword arguments for *target*.
            stop_event: Optional event to signal thread to stop.

        Returns:
            The started thread.
        """
        if kwargs is None:
            kwargs = {}

        thread = threading.Thread(
            target=target, args=args, kwargs=kwargs, name=name,
        )
        thread.daemon = False  # Non-daemon so we can clean up properly

        with self._lock:
            self._threads.append(thread)
            if stop_event is not None:
                self._stop_events[name] = stop_event

        thread.start()
        log.debug("Started managed thread: %s", name)
        return thread

    def stop_thread(self, name: str, timeout: float = 5.0) -> bool:
        """Stop a specific thread by name.

        Args:
            name:    Thread name to stop.
            timeout: Seconds to wait for thread to join.

        Returns:
            True if thread stopped, False if still running.
        """
        with self._lock:
            if name in self._stop_events:
                self._stop_events[name].set()
                log.debug("Signalled stop for thread: %s", name)

            for thread in self._threads:
                if thread.name == name:
                    thread.join(timeout=timeout)
                    if thread.is_alive():
                        log.warning("Thread %s did not stop within %.1fs", name, timeout)
                        return False
                    self._threads.remove(thread)
                    self._stop_events.pop(name, None)
                    log.debug("Thread %s stopped", name)
                    return True

        log.warning("Thread %s not found", name)
        return False

    def shutdown(self, timeout: float = 5.0) -> int:
        """Stop all managed threads.

        Args:
            timeout: Seconds to wait for each thread.

        Returns:
            Number of threads that didn't stop in time.
        """
        with self._lock:
            count = len(self._threads)
            log.info("Shutting down %d managed thread(s)...", count)

            # Signal all stop events first
            for name, event in self._stop_events.items():
                event.set()

            # Wait for threads to finish
            still_running = 0
            for thread in self._threads[:]:
                thread.join(timeout=timeout)
                if thread.is_alive():
                    log.warning("Thread %s still running after shutdown", thread.name)
                    still_running += 1
                else:
                    self._threads.remove(thread)

            self._stop_events.clear()

        if still_running:
            log.warning("%d thread(s) still running after shutdown", still_running)
        else:
            log.info("All managed threads stopped")
        return still_running

    @property
    def running_threads(self) -> List[str]:
        """Get names of currently running threads."""
        with self._lock:
            return [t.name for t in self._threads if t.is_alive()]


# ── Module-level singleton ───────────────────────────────────
_global_manager: Optional[ThreadManager] = None


def get_thread_manager() -> ThreadManager:
    """Get the global thread manager instance."""
    global _global_manager
    if _global_manager is None:
        _global_manager = ThreadManager()
    return _global_manager


def shutdown_all_threads(timeout: float = 5.0) -> int:
    """Convenience function to shutdown all globally managed threads."""
    global _global_manager
    if _global_manager is not None:
        return _global_manager.shutdown(timeout)
    return 0
