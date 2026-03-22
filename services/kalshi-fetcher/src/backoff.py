import asyncio
import time
from enum import Enum
from typing import Callable, Any
import structlog

log = structlog.get_logger()


class CircuitState(Enum):
    CLOSED = "closed"       # Normal operation
    OPEN = "open"           # Failing — reject calls immediately
    HALF_OPEN = "half_open" # Testing recovery


class CircuitBreaker:
    def __init__(
        self,
        failure_threshold: int = 5,
        reset_timeout: float = 60.0,
        name: str = "circuit",
    ):
        self.failure_threshold = failure_threshold
        self.reset_timeout = reset_timeout
        self.name = name

        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._last_failure_time: float = 0.0

    @property
    def state(self) -> CircuitState:
        if self._state == CircuitState.OPEN:
            if time.monotonic() - self._last_failure_time >= self.reset_timeout:
                log.info("circuit_half_open", circuit=self.name)
                self._state = CircuitState.HALF_OPEN
        return self._state

    async def call(self, func: Callable, *args, **kwargs) -> Any:
        if self.state == CircuitState.OPEN:
            raise RuntimeError(f"Circuit '{self.name}' is OPEN — call rejected")

        try:
            result = await func(*args, **kwargs)
            self._on_success()
            return result
        except Exception as exc:
            self._on_failure(exc)
            raise

    def _on_success(self) -> None:
        if self._state == CircuitState.HALF_OPEN:
            log.info("circuit_closed", circuit=self.name)
        self._state = CircuitState.CLOSED
        self._failure_count = 0

    def _on_failure(self, exc: Exception) -> None:
        self._failure_count += 1
        self._last_failure_time = time.monotonic()
        log.warning(
            "circuit_failure",
            circuit=self.name,
            failures=self._failure_count,
            threshold=self.failure_threshold,
            error=str(exc),
        )
        if self._failure_count >= self.failure_threshold:
            if self._state != CircuitState.OPEN:
                log.error("circuit_opened", circuit=self.name)
            self._state = CircuitState.OPEN
