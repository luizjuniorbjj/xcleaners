"""
Circuit Breaker for external API calls.
States: CLOSED (normal) -> OPEN (failing) -> HALF_OPEN (testing recovery)
Thread-safe via threading.Lock (works with asyncio since all state ops are fast/non-blocking).
"""
import time
import threading
import logging
from enum import Enum
from typing import Optional

logger = logging.getLogger("xcleaners.circuit_breaker")


class CircuitState(Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitBreaker:
    """
    Thread-safe circuit breaker with exponential backoff.

    Usage:
        cb = CircuitBreaker(name="anthropic", failure_threshold=3, recovery_timeout=30)
        if cb.can_execute():
            try:
                result = call_api()
                cb.record_success()
            except Exception as e:
                cb.record_failure()
                raise
    """

    def __init__(
        self,
        name: str,
        failure_threshold: int = 3,
        recovery_timeout: float = 30.0,
        max_recovery_timeout: float = 300.0,
    ):
        self.name = name
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.max_recovery_timeout = max_recovery_timeout

        self._lock = threading.Lock()
        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._last_failure_time: Optional[float] = None
        self._current_recovery_timeout = recovery_timeout

    @property
    def state(self) -> CircuitState:
        with self._lock:
            if self._state == CircuitState.OPEN and self._last_failure_time is not None:
                elapsed = time.time() - self._last_failure_time
                if elapsed >= self._current_recovery_timeout:
                    self._state = CircuitState.HALF_OPEN
                    logger.info(f"[CB:{self.name}] OPEN -> HALF_OPEN (testing recovery after {elapsed:.0f}s)")
            return self._state

    def can_execute(self) -> bool:
        current = self.state  # property already acquires lock
        if current in (CircuitState.CLOSED, CircuitState.HALF_OPEN):
            return True
        # OPEN -- calculate remaining time for logging
        with self._lock:
            if self._last_failure_time is not None:
                remaining = self._current_recovery_timeout - (time.time() - self._last_failure_time)
                logger.debug(f"[CB:{self.name}] OPEN -- rejecting, retry in {max(0, remaining):.0f}s")
            else:
                logger.debug(f"[CB:{self.name}] OPEN -- rejecting (no failure time recorded)")
        return False

    def record_success(self):
        with self._lock:
            if self._state == CircuitState.HALF_OPEN:
                logger.info(f"[CB:{self.name}] HALF_OPEN -> CLOSED (recovered)")
            self._state = CircuitState.CLOSED
            self._failure_count = 0
            self._current_recovery_timeout = self.recovery_timeout

    def record_failure(self):
        with self._lock:
            self._failure_count += 1
            self._last_failure_time = time.time()

            if self._state == CircuitState.HALF_OPEN:
                self._state = CircuitState.OPEN
                self._current_recovery_timeout = min(
                    self._current_recovery_timeout * 2,
                    self.max_recovery_timeout
                )
                logger.warning(f"[CB:{self.name}] HALF_OPEN -> OPEN (recovery failed, next retry in {self._current_recovery_timeout:.0f}s)")
            elif self._failure_count >= self.failure_threshold:
                self._state = CircuitState.OPEN
                logger.warning(f"[CB:{self.name}] CLOSED -> OPEN (threshold {self.failure_threshold} reached)")

    def reset(self):
        """Manual reset"""
        with self._lock:
            self._state = CircuitState.CLOSED
            self._failure_count = 0
            self._last_failure_time = None
            self._current_recovery_timeout = self.recovery_timeout
            logger.info(f"[CB:{self.name}] Manual reset -> CLOSED")


# ============================================
# MODULE-LEVEL SINGLETONS
# Shared across all AIService instances
# ============================================
cb_primary = CircuitBreaker(name="primary", failure_threshold=3, recovery_timeout=30)
cb_fallback = CircuitBreaker(name="fallback", failure_threshold=5, recovery_timeout=60)
