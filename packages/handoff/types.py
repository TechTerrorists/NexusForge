from enum import Enum
from dataclasses import dataclass, field
from typing import Any
import time
import uuid

class LaneName(str, Enum):
    MAIN = "main"
    SUBAGENT = "subagent"
    CRON = "cron"
    NESTED = "nested"

class RunSource(str, Enum):
    CHAT = "chat"
    API = "api"
    EVENT = "event"
    CRON = "cron"

@dataclass
class HandoffMessage:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    type: str = ""
    version: int = 1
    tenant_id: str = ""
    session_key: str = ""
    business_key: str = ""
    attempt: int = 0
    max_attempts: int = 3
    enqueued_at: float = field(default_factory=time.time)
    trace_id: str = ""
    payload: dict = field(default_factory=dict)
    headers: dict = field(default_factory=dict)

@dataclass
class ProcessorPolicy:
    lane: LaneName = LaneName.MAIN
    timeout_ms: int = 30000
    idle_timeout_ms: int | None = None

@dataclass
class ProcessResult:
    status: str = "ok"  # ok | retry | dead
    outbound: list = field(default_factory=list)
    delay_ms: int = 0
    reason: str = ""

@dataclass
class LaneStats:
    lane: str
    active: int
    queued: int
    max_concurrent: int
    draining: bool = False

@dataclass
class RunMetadata:
    run_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    session_key: str = ""
    lane: LaneName = LaneName.MAIN
    source: RunSource = RunSource.API
    started_at: float = field(default_factory=time.time)
    expires_at: float | None = None
    tenant_id: str = ""
    user_id: str = ""

DEFAULT_LANE_CONFIG = {
    LaneName.MAIN: 8,
    LaneName.SUBAGENT: 16,
    LaneName.CRON: 4,
    LaneName.NESTED: 8,
}
