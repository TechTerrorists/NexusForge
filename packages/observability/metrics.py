import time
import threading
from typing import Any
from collections import defaultdict


class Counter:
    def __init__(self, name: str, description: str = ""):
        self.name = name
        self.description = description
        self._value = 0.0
        self._labels: dict[tuple, float] = defaultdict(float)
        self._lock = threading.Lock()

    def inc(self, value: float = 1.0, **labels: str) -> None:
        """Increment counter by value."""
        with self._lock:
            label_key = tuple(sorted(labels.items()))
            if label_key:
                self._labels[label_key] += value
            else:
                self._value += value

    def get(self, **labels: str) -> float:
        """Get counter value."""
        with self._lock:
            if labels:
                label_key = tuple(sorted(labels.items()))
                return self._labels.get(label_key, 0.0)
            return self._value

    def get_all(self) -> dict[str, float]:
        """Get all counter values."""
        with self._lock:
            result = {"_total": self._value}
            for labels, value in self._labels.items():
                label_str = ",".join(f'{k}="{v}"' for k, v in labels)
                result[label_str] = value
            return result


class Histogram:
    def __init__(self, name: str, description: str = ""):
        self.name = name
        self.description = description
        self._values: list[float] = []
        self._labeled_values: dict[tuple, list[float]] = defaultdict(list)
        self._lock = threading.Lock()

    def observe(self, value: float, **labels: str) -> None:
        """Record an observation."""
        with self._lock:
            label_key = tuple(sorted(labels.items()))
            if label_key:
                self._labeled_values[label_key].append(value)
            else:
                self._values.append(value)

    def get_stats(self, **labels: str) -> dict[str, float]:
        """Get histogram statistics."""
        with self._lock:
            if labels:
                label_key = tuple(sorted(labels.items()))
                values = self._labeled_values.get(label_key, [])
            else:
                values = self._values
            
            if not values:
                return {"count": 0, "sum": 0, "avg": 0, "min": 0, "max": 0}
            
            sorted_values = sorted(values)
            count = len(values)
            return {
                "count": count,
                "sum": sum(values),
                "avg": sum(values) / count,
                "min": sorted_values[0],
                "max": sorted_values[-1],
                "p50": sorted_values[int(count * 0.5)],
                "p90": sorted_values[int(count * 0.9)],
                "p99": sorted_values[min(int(count * 0.99), count - 1)]
            }


class Gauge:
    def __init__(self, name: str, description: str = ""):
        self.name = name
        self.description = description
        self._value = 0.0
        self._labels: dict[tuple, float] = {}
        self._lock = threading.Lock()

    def set(self, value: float, **labels: str) -> None:
        """Set gauge value."""
        with self._lock:
            label_key = tuple(sorted(labels.items()))
            if label_key:
                self._labels[label_key] = value
            else:
                self._value = value

    def inc(self, value: float = 1.0, **labels: str) -> None:
        """Increment gauge value."""
        with self._lock:
            label_key = tuple(sorted(labels.items()))
            if label_key:
                self._labels[label_key] = self._labels.get(label_key, 0.0) + value
            else:
                self._value += value

    def dec(self, value: float = 1.0, **labels: str) -> None:
        """Decrement gauge value."""
        with self._lock:
            label_key = tuple(sorted(labels.items()))
            if label_key:
                self._labels[label_key] = self._labels.get(label_key, 0.0) - value
            else:
                self._value -= value

    def get(self, **labels: str) -> float:
        """Get gauge value."""
        with self._lock:
            if labels:
                label_key = tuple(sorted(labels.items()))
                return self._labels.get(label_key, 0.0)
            return self._value

    def get_all(self) -> dict[str, float]:
        """Get all gauge values."""
        with self._lock:
            result = {"_value": self._value}
            for labels, value in self._labels.items():
                label_str = ",".join(f'{k}="{v}"' for k, v in labels)
                result[label_str] = value
            return result


class PrometheusMetrics:
    def __init__(self):
        self.workflow_runs_total = Counter("workflow_runs_total", "Total workflow runs")
        self.agent_runs_total = Counter("agent_runs_total", "Total agent runs")
        self.tool_calls_total = Counter("tool_calls_total", "Total tool calls")
        
        self.workflow_duration_seconds = Histogram(
            "workflow_duration_seconds", "Workflow duration in seconds"
        )
        self.agent_duration_seconds = Histogram(
            "agent_duration_seconds", "Agent duration in seconds"
        )
        self.llm_tokens_used = Histogram("llm_tokens_used", "LLM tokens used")
        
        self.active_workflows = Gauge("active_workflows", "Currently active workflows")
        self.active_agents = Gauge("active_agents", "Currently active agents")

    def record_workflow_run(
        self, 
        workflow_id: str, 
        status: str, 
        duration: float
    ) -> None:
        """Record a workflow run."""
        self.workflow_runs_total.inc(workflow=workflow_id, status=status)
        self.workflow_duration_seconds.observe(duration, workflow=workflow_id)

    def record_agent_run(
        self, 
        agent_id: str, 
        status: str, 
        duration: float
    ) -> None:
        """Record an agent run."""
        self.agent_runs_total.inc(agent=agent_id, status=status)
        self.agent_duration_seconds.observe(duration, agent=agent_id)

    def record_tool_call(self, tool_name: str, status: str) -> None:
        """Record a tool call."""
        self.tool_calls_total.inc(tool=tool_name, status=status)

    def record_llm_usage(
        self, 
        model: str, 
        input_tokens: int, 
        output_tokens: int, 
        cost_cents: float
    ) -> None:
        """Record LLM token usage."""
        self.llm_tokens_used.observe(input_tokens, model=model, type="input")
        self.llm_tokens_used.observe(output_tokens, model=model, type="output")

    def increment_active_workflows(self) -> None:
        """Increment active workflows gauge."""
        self.active_workflows.inc()

    def decrement_active_workflows(self) -> None:
        """Decrement active workflows gauge."""
        self.active_workflows.dec()

    def increment_active_agents(self) -> None:
        """Increment active agents gauge."""
        self.active_agents.inc()

    def decrement_active_agents(self) -> None:
        """Decrement active agents gauge."""
        self.active_agents.dec()

    def get_metrics(self) -> str:
        """Get metrics in Prometheus text format."""
        lines = []
        
        lines.extend(self._format_counter(self.workflow_runs_total))
        lines.extend(self._format_counter(self.agent_runs_total))
        lines.extend(self._format_counter(self.tool_calls_total))
        
        lines.extend(self._format_histogram(self.workflow_duration_seconds))
        lines.extend(self._format_histogram(self.agent_duration_seconds))
        lines.extend(self._format_histogram(self.llm_tokens_used))
        
        lines.extend(self._format_gauge(self.active_workflows))
        lines.extend(self._format_gauge(self.active_agents))
        
        return "\n".join(lines)

    def _format_counter(self, counter: Counter) -> list[str]:
        """Format counter as Prometheus text."""
        lines = []
        if counter.description:
            lines.append(f"# HELP {counter.name} {counter.description}")
        lines.append(f"# TYPE {counter.name} counter")
        
        all_values = counter.get_all()
        if "_total" in all_values:
            lines.append(f"{counter.name} {all_values['_total']}")
        
        for labels, value in all_values.items():
            if labels != "_total":
                lines.append(f'{counter.name}{{{labels}}} {value}')
        
        return lines

    def _format_histogram(self, histogram: Histogram) -> list[str]:
        """Format histogram as Prometheus text."""
        lines = []
        if histogram.description:
            lines.append(f"# HELP {histogram.name} {histogram.description}")
        lines.append(f"# TYPE {histogram.name} histogram")
        
        stats = histogram.get_stats()
        if stats["count"] > 0:
            lines.append(f'{histogram.name}_count {stats["count"]}')
            lines.append(f'{histogram.name}_sum {stats["sum"]}')
        
        return lines

    def _format_gauge(self, gauge: Gauge) -> list[str]:
        """Format gauge as Prometheus text."""
        lines = []
        if gauge.description:
            lines.append(f"# HELP {gauge.name} {gauge.description}")
        lines.append(f"# TYPE {gauge.name} gauge")
        
        all_values = gauge.get_all()
        if "_value" in all_values:
            lines.append(f"{gauge.name} {all_values['_value']}")
        
        for labels, value in all_values.items():
            if labels != "_value":
                lines.append(f'{gauge.name}{{{labels}}} {value}')
        
        return lines
