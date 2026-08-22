import time
import uuid
import logging
from typing import Any, Optional
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class SpanContext:
    span_id: str
    trace_id: str
    parent_id: Optional[str]
    name: str
    start_time: float = field(default_factory=time.time)
    end_time: Optional[float] = None
    attributes: dict = field(default_factory=dict)
    events: list = field(default_factory=list)


@dataclass
class TraceContext:
    trace_id: str
    name: str
    start_time: float = field(default_factory=time.time)
    end_time: Optional[float] = None
    metadata: dict = field(default_factory=dict)
    spans: list[SpanContext] = field(default_factory=list)


class TracingProvider:
    def __init__(self, provider: str = "none"):
        self._provider = provider
        self._traces: dict[str, TraceContext] = {}
        self._spans: dict[str, SpanContext] = {}
        self._enabled = provider != "none"
        
        if self._enabled:
            logger.info(f"Initialized tracing provider: {provider}")

    def start_trace(self, name: str, metadata: dict[str, Any] = None) -> str:
        """Start a new trace and return the trace ID."""
        if not self._enabled:
            return ""
        
        trace_id = str(uuid.uuid4())
        context = TraceContext(
            trace_id=trace_id,
            name=name,
            metadata=metadata or {}
        )
        self._traces[trace_id] = context
        logger.debug(f"Started trace {trace_id}: {name}")
        return trace_id

    def end_trace(self, trace_id: str, result: dict[str, Any] = None) -> None:
        """End a trace and record the result."""
        if not self._enabled or trace_id not in self._traces:
            return
        
        context = self._traces[trace_id]
        context.end_time = time.time()
        if result:
            context.metadata.update(result)
        
        duration_ms = (context.end_time - context.start_time) * 1000
        logger.debug(
            f"Ended trace {trace_id}: {context.name} "
            f"({duration_ms:.2f}ms)"
        )

    def start_span(
        self, 
        name: str, 
        parent: Optional[str] = None,
        attributes: dict[str, Any] = None
    ) -> str:
        """Start a new span and return the span ID."""
        if not self._enabled:
            return ""
        
        span_id = str(uuid.uuid4())
        trace_id = ""
        
        if parent and parent in self._traces:
            trace_id = parent
        elif parent and parent in self._spans:
            trace_id = self._spans[parent].trace_id
        elif self._traces:
            trace_id = next(iter(self._traces.keys()))
        
        context = SpanContext(
            span_id=span_id,
            trace_id=trace_id,
            parent_id=parent,
            name=name,
            attributes=attributes or {}
        )
        
        self._spans[span_id] = context
        
        if trace_id and trace_id in self._traces:
            self._traces[trace_id].spans.append(context)
        
        logger.debug(f"Started span {span_id}: {name}")
        return span_id

    def end_span(self, span_id: str, result: dict[str, Any] = None) -> None:
        """End a span and record the result."""
        if not self._enabled or span_id not in self._spans:
            return
        
        context = self._spans[span_id]
        context.end_time = time.time()
        if result:
            context.attributes.update(result)
        
        duration_ms = (context.end_time - context.start_time) * 1000
        logger.debug(
            f"Ended span {span_id}: {context.name} "
            f"({duration_ms:.2f}ms)"
        )

    def record_event(
        self, 
        span_id: str, 
        event_name: str, 
        data: dict[str, Any] = None
    ) -> None:
        """Record an event on a span."""
        if not self._enabled or span_id not in self._spans:
            return
        
        event = {
            "name": event_name,
            "timestamp": time.time(),
            "data": data or {}
        }
        self._spans[span_id].events.append(event)
        logger.debug(f"Recorded event on span {span_id}: {event_name}")

    def get_trace(self, trace_id: str) -> Optional[TraceContext]:
        """Get trace context by ID."""
        return self._traces.get(trace_id)

    def get_span(self, span_id: str) -> Optional[SpanContext]:
        """Get span context by ID."""
        return self._spans.get(span_id)

    def cleanup(self, max_age_seconds: int = 3600) -> int:
        """Cleanup old traces and spans. Returns number of items removed."""
        if not self._enabled:
            return 0
        
        current_time = time.time()
        removed = 0
        
        expired_traces = [
            tid for tid, trace in self._traces.items()
            if current_time - trace.start_time > max_age_seconds
        ]
        for tid in expired_traces:
            del self._traces[tid]
            removed += 1
        
        expired_spans = [
            sid for sid, span in self._spans.items()
            if current_time - span.start_time > max_age_seconds
        ]
        for sid in expired_spans:
            del self._spans[sid]
            removed += 1
        
        if removed > 0:
            logger.debug(f"Cleaned up {removed} old traces/spans")
        
        return removed

    def get_stats(self) -> dict[str, Any]:
        """Get tracing statistics."""
        return {
            "provider": self._provider,
            "enabled": self._enabled,
            "active_traces": len(self._traces),
            "active_spans": len(self._spans)
        }
