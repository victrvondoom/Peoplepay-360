"""
Observability Service - Metrics and Monitoring
"""

import logging
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, List, Dict, Any
from uuid import uuid4
from collections import defaultdict


@dataclass
class Metric:
    name: str
    value: float
    tags: Dict[str, str] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.utcnow)
    description: Optional[str] = None


@dataclass
class Trace:
    trace_id: str
    name: str
    start_time: datetime
    end_time: Optional[datetime] = None
    duration_ms: float = 0.0
    tags: Dict[str, str] = field(default_factory=dict)
    spans: List[Dict[str, Any]] = field(default_factory=list)
    status: str = "ok"


class ObservabilityService:
    def __init__(self):
        self._metrics: Dict[str, List[Metric]] = defaultdict(list)
        self._traces: Dict[str, Trace] = {}
        self._logger = logging.getLogger(__name__)

    def record_metric(
        self,
        name: str,
        value: float,
        tags: Optional[Dict[str, str]] = None,
        description: Optional[str] = None,
    ) -> Metric:
        metric = Metric(
            name=name,
            value=value,
            tags=tags or {},
            description=description,
        )
        self._metrics[name].append(metric)
        # Keep only last 1000 metrics per name
        if len(self._metrics[name]) > 1000:
            self._metrics[name] = self._metrics[name][-1000:]
        return metric

    def get_metrics(
        self,
        name: Optional[str] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
    ) -> List[Metric]:
        if name:
            metrics = self._metrics.get(name, [])
        else:
            metrics = [m for ms in self._metrics.values() for m in ms]
        
        if start_time:
            metrics = [m for m in metrics if m.timestamp >= start_time]
        if end_time:
            metrics = [m for m in metrics if m.timestamp <= end_time]
        
        return sorted(metrics, key=lambda m: m.timestamp, reverse=True)

    def start_trace(
        self,
        name: str,
        tags: Optional[Dict[str, str]] = None,
    ) -> str:
        trace_id = str(uuid4())
        trace = Trace(
            trace_id=trace_id,
            name=name,
            start_time=datetime.utcnow(),
            tags=tags or {},
        )
        self._traces[trace_id] = trace
        return trace_id

    def end_trace(
        self,
        trace_id: str,
        status: str = "ok",
        error: Optional[str] = None,
    ) -> Optional[Trace]:
        trace = self._traces.get(trace_id)
        if trace is None:
            return None
        
        trace.end_time = datetime.utcnow()
        trace.duration_ms = (trace.end_time - trace.start_time).total_seconds() * 1000
        trace.status = status
        
        if error:
            trace.tags["error"] = error
        
        return trace

    def add_span(
        self,
        trace_id: str,
        span_data: Dict[str, Any],
    ) -> bool:
        trace = self._traces.get(trace_id)
        if trace is None:
            return False
        trace.spans.append(span_data)
        return True

    def get_trace(self, trace_id: str) -> Optional[Trace]:
        return self._traces.get(trace_id)

    def list_traces(
        self,
        name: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 100,
    ) -> List[Trace]:
        traces = list(self._traces.values())
        
        if name:
            traces = [t for t in traces if t.name == name]
        if status:
            traces = [t for t in traces if t.status == status]
        
        return sorted(traces, key=lambda t: t.start_time, reverse=True)[:limit]

    def get_health_status(self) -> Dict[str, Any]:
        return {
            "status": "healthy",
            "timestamp": datetime.utcnow().isoformat(),
            "metrics_count": sum(len(ms) for ms in self._metrics.values()),
            "traces_count": len(self._traces),
        }


_observability_service: Optional[ObservabilityService] = None


def get_observability_service() -> ObservabilityService:
    global _observability_service
    if _observability_service is None:
        _observability_service = ObservabilityService()
    return _observability_service
