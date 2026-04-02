"""Minimal observer/event bus for shell modules."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Callable

EventListener = Callable[["ShellEvent"], None]


def emit_event(event_bus: Any | None, event_name: str, **payload: Any) -> None:
    """Emit an event when a bus with an ``emit`` method is available."""
    if event_bus is None:
        return
    emit = getattr(event_bus, "emit", None)
    if emit is None:
        return
    emit(event_name, **payload)


@dataclass(frozen=True)
class ShellEvent:
    """Immutable event payload emitted by the shell runtime."""

    name: str
    payload: dict[str, Any] = field(default_factory=dict)


class EventBus:
    """Simple publish/subscribe event bus with optional wildcard listeners."""

    def __init__(self) -> None:
        self._listeners: dict[str, list[EventListener]] = defaultdict(list)

    def subscribe(
        self, event_name: str, listener: EventListener
    ) -> Callable[[], None]:
        self._listeners[event_name].append(listener)

        def _unsubscribe() -> None:
            listeners = self._listeners.get(event_name)
            if listeners is None:
                return
            try:
                listeners.remove(listener)
            except ValueError:
                return
            if not listeners:
                self._listeners.pop(event_name, None)

        return _unsubscribe

    def emit(self, event_name: str, **payload: Any) -> None:
        event = ShellEvent(name=event_name, payload=dict(payload))
        listeners = list(self._listeners.get(event_name, []))
        listeners.extend(self._listeners.get("*", []))
        for listener in listeners:
            listener(event)
