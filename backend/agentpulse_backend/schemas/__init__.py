"""Pydantic schemas for API request/response validation.

These schemas are the canonical contract between the API and its callers.
They mirror the JSON schemas in packages/contracts/schemas/ but add
FastAPI-specific features (validation, examples, OpenAPI integration).
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


# ─── Enums ─────────────────────────────────────────────────────────────────────

class CheckStatus(str, Enum):
    PASS = "pass"
    WARN = "warn"
    FAIL = "fail"
    SKIP = "skip"
    ERROR = "error"


class Severity(str, Enum):
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


class AgentStatus(str, Enum):
    ONLINE = "online"
    OFFLINE = "offline"
    DEGRADED = "degraded"


class IncidentStatus(str, Enum):
    OPEN = "open"
    ACKNOWLEDGED = "acknowledged"
    RESOLVED = "resolved"
    SUPPRESSED = "suppressed"


class RemediationAction(str, Enum):
    RESTART_SERVICE = "restart_service"
    RESTART_CONTAINER = "restart_container"
    ROTATE_LOGS = "rotate_logs"
    CLEAN_TEMP = "clean_temp"
    PRUNE_CACHE = "prune_cache"


class RemediationRisk(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class RemediationStatus(str, Enum):
    PENDING = "pending"
    SUCCESS = "success"
    FAILED = "failed"
    SKIPPED = "skipped"
    PENDING_APPROVAL = "pending_approval"


class AuditOutcome(str, Enum):
    SUCCESS = "success"
    FAILURE = "failure"
    PENDING = "pending"
    SUPPRESSED = "suppressed"
    INCIDENTS_OPENED = "incidents_opened"


class Component(str, Enum):
    AGENT = "agent"
    BACKEND = "backend"
    WORKER = "worker"
    DASHBOARD = "dashboard"
    CONTROL_PLANE = "control-plane"


# ─── Enrollment ─────────────────────────────────────────────────────────────────

class EnrollmentRequest(BaseModel):
    version: str = Field(default="1", pattern=r"^1$")
    hostname: str = Field(max_length=255)
    os: str = Field(max_length=32)
    architecture: str = Field(max_length=32)
    agent_version: str = Field(max_length=64)
    config_version: str = Field(default="", max_length=64)
    machine_id: str = Field(default="", max_length=255)
    kernel_version: str = Field(default="", max_length=128)
    checks_offered: List[str] = Field(default_factory=list)
    timestamp: str
    nonce: str = Field(min_length=16)
    enrollment_token: str = Field(min_length=16)
    signature: str

    @field_validator("timestamp")
    @classmethod
    def validate_timestamp(cls, v: str) -> str:
        try:
            dt = datetime.fromisoformat(v.replace("Z", "+00:00"))
            age = (datetime.now(timezone.utc) - dt).total_seconds()
            if abs(age) > 300:
                raise ValueError("Timestamp must be within 5 minutes of now")
        except ValueError:
            raise
        return v


class EnrollmentResponse(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    agent_id: str
    auth_token: str
    backend_url: str
    checkin_interval: int = 60
    policy: Dict[str, Any] = Field(default_factory=dict)


# ─── Check-in ─────────────────────────────────────────────────────────────────

class CheckResultSchema(BaseModel):
    check_id: str
    check_type: str
    status: CheckStatus
    severity: Severity = Severity.INFO
    executed_at: str
    duration_ms: int = Field(ge=0)
    value: Optional[float] = None
    unit: str = ""
    message: str = ""
    evidence: List[str] = Field(default_factory=list)
    consecutive_failures: int = Field(default=0, ge=0)
    is_baseline_anomaly: bool = False


class RemediationRequestSchema(BaseModel):
    id: str
    incident_id: str
    agent_id: str
    action: RemediationAction
    target: str = ""
    risk: RemediationRisk
    preconditions: List[str] = Field(default_factory=list)
    dry_run: bool = False
    created_at: str
    expires_at: Optional[str] = None
    idempotency_key: str


class RemediationResultSchema(BaseModel):
    request_id: str
    incident_id: str
    agent_id: str
    status: RemediationStatus
    executed_at: str
    duration_ms: int = Field(ge=0)
    action_taken: str = ""
    output: str = ""
    exit_code: Optional[int] = None
    verification_passed: Optional[bool] = None
    error: str = ""
    rollback_available: bool = False
    idempotency_key: str


class CheckinRequest(BaseModel):
    version: str = Field(default="1", pattern=r"^1$")
    agent_id: str
    timestamp: str
    sequence: int = Field(ge=1)
    agent_version: str = Field(max_length=64)
    config_version: str = Field(default="", max_length=64)
    hostname: str = Field(max_length=255)
    uptime_seconds: int = Field(default=0, ge=0)
    results: List[CheckResultSchema] = Field(default_factory=list)
    pending_actions: List[RemediationRequestSchema] = Field(default_factory=list)
    action_results: List[RemediationResultSchema] = Field(default_factory=list)
    offline_queue_depth: int = Field(default=0, ge=0)
    signature: str = ""


class CheckinResponse(BaseModel):
    acknowledged: bool = True
    actions: List[RemediationRequestSchema] = Field(default_factory=list)
    policy_version: str = ""
    server_time: str


# ─── Agents ────────────────────────────────────────────────────────────────────

class AgentResponse(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    id: str
    tenant_id: str
    hostname: str
    os: str
    architecture: str
    agent_version: str
    config_version: str
    machine_id: str
    status: AgentStatus
    enrolled_at: str
    last_seen_at: str
    policy_id: str = ""
    tags: List[str] = Field(default_factory=list)


class AgentListResponse(BaseModel):
    agents: List[AgentResponse]
    next_page: Optional[str] = None
    total: int


class AgentUpdateRequest(BaseModel):
    tags: Optional[List[str]] = None
    policy_id: Optional[str] = None


# ─── Incidents ─────────────────────────────────────────────────────────────────

class IncidentResponse(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    id: str
    tenant_id: str
    agent_id: str
    check_id: str
    check_type: str
    status: IncidentStatus
    severity: Severity
    title: str
    body: str = ""
    evidence: List[str] = Field(default_factory=list)
    opened_at: str
    acknowledged_at: Optional[str] = None
    acknowledged_by: str = ""
    resolved_at: Optional[str] = None
    resolved_by: str = ""
    remediation_id: Optional[str] = None
    policy_id: str = ""
    is_baseline_anomaly: bool = False
    tags: List[str] = Field(default_factory=list)


class IncidentListResponse(BaseModel):
    incidents: List[IncidentResponse]
    next_page: Optional[str] = None
    total: int


class AcknowledgeRequest(BaseModel):
    note: str = ""


class IncidentEventResponse(BaseModel):
    id: int
    incident_id: str
    event_type: str
    actor: str
    actor_id: str = ""
    body: Dict[str, Any] = Field(default_factory=dict)
    created_at: str


# ─── Audit ─────────────────────────────────────────────────────────────────────

class AuditEventResponse(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    id: int
    tenant_id: str
    timestamp: str
    component: Component
    event_type: str
    actor: str
    agent_id: Optional[str] = None
    incident_id: Optional[str] = None
    remediation_id: Optional[str] = None
    outcome: str  # flexible — supports 'success', 'failure', 'incidents_opened', etc.
    body: Dict[str, Any] = Field(default_factory=dict)


class AuditEventListResponse(BaseModel):
    events: List[AuditEventResponse]
    next_page: Optional[str] = None


# ─── Error ─────────────────────────────────────────────────────────────────────

class ErrorResponse(BaseModel):
    error_code: str
    message: str
    request_id: str = ""
    details: Dict[str, Any] = Field(default_factory=dict)
    retry_after: Optional[int] = None
