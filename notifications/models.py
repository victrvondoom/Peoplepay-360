"""Notification data models."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any
from uuid import UUID, uuid4


class NotificationType(str, Enum):
    """Types of notifications."""
    INFORMATION = "information"
    WARNING = "warning"
    ERROR = "error"
    SUCCESS = "success"
    
    # Business notifications
    ORDER_STATUS = "order_status"
    PAYMENT_STATUS = "payment_status"
    APPROVAL_REQUEST = "approval_request"
    APPROVAL_GRANTED = "approval_granted"
    APPROVAL_DENIED = "approval_denied"
    WORKFLOW_COMPLETED = "workflow_completed"
    WORKFLOW_FAILED = "workflow_failed"
    TASK_COMPLETED = "task_completed"
    TASK_FAILED = "task_failed"
    RISK_ALERT = "risk_alert"
    SUPPLIER_UPDATE = "supplier_update"
    DISPUTE_CREATED = "dispute_created"
    DISPUTE_RESOLVED = "dispute_resolved"
    
    # System notifications
    SYSTEM_HEALTH = "system_health"
    SYSTEM_ALERT = "system_alert"
    MAINTENANCE = "maintenance"


class NotificationStatus(str, Enum):
    """Notification delivery status."""
    PENDING = "pending"
    DELIVERED = "delivered"
    FAILED = "failed"
    READ = "read"
    ARCHIVED = "archived"
    DISMISSED = "dismissed"


class NotificationChannel(str, Enum):
    """Notification delivery channels."""
    IN_APP = "in_app"
    EMAIL = "email"
    WEBHOOK = "webhook"
    # Future: PUSH = "push", SMS = "sms"


@dataclass
class Notification:
    """A notification to be delivered."""
    notification_id: str = field(default_factory=lambda: f"notify-{uuid4().hex}")
    user_id: str | None = None
    organization_id: str | None = None
    
    # Content
    notification_type: NotificationType = NotificationType.INFORMATION
    title: str = ""
    message: str = ""
    data: dict[str, Any] = field(default_factory=dict)
    
    # Routing
    channels: list[NotificationChannel] = field(default_factory=lambda: [NotificationChannel.IN_APP])
    priority: int = 0  # Higher is more urgent
    
    # State
    status: NotificationStatus = NotificationStatus.PENDING
    status_history: list[dict[str, Any]] = field(default_factory=list)
    
    # Timestamps
    created_at: datetime = field(default_factory=datetime.utcnow)
    scheduled_at: datetime | None = None
    delivered_at: datetime | None = None
    read_at: datetime | None = None
    archived_at: datetime | None = None
    
    # Deduplication
    fingerprint: str | None = None
    deduplication_id: str | None = None
    
    # Links
    related_resource_id: str | None = None
    related_resource_type: str | None = None
    action_url: str | None = None
    
    # Metadata
    metadata: dict[str, Any] = field(default_factory=dict)
    tags: list[str] = field(default_factory=list)
    
    def mark_delivered(self, channel: NotificationChannel) -> None:
        """Mark notification as delivered via a channel."""
        self.status = NotificationStatus.DELIVERED
        self.delivered_at = datetime.utcnow()
        self.status_history.append({
            "status": NotificationStatus.DELIVERED,
            "channel": channel,
            "timestamp": self.delivered_at.isoformat(),
        })
    
    def mark_failed(self, channel: NotificationChannel, reason: str) -> None:
        """Mark notification delivery as failed."""
        self.status_history.append({
            "status": NotificationStatus.FAILED,
            "channel": channel,
            "reason": reason,
            "timestamp": datetime.utcnow().isoformat(),
        })
        # Only mark as failed if all delivery attempts have failed
        if all(s["status"] == NotificationStatus.FAILED for s in self.status_history):
            self.status = NotificationStatus.FAILED
    
    def mark_read(self) -> None:
        """Mark notification as read."""
        self.status = NotificationStatus.READ
        self.read_at = datetime.utcnow()
        self.status_history.append({
            "status": NotificationStatus.READ,
            "timestamp": self.read_at.isoformat(),
        })
    
    def mark_archived(self) -> None:
        """Mark notification as archived."""
        self.status = NotificationStatus.ARCHIVED
        self.archived_at = datetime.utcnow()
        self.status_history.append({
            "status": NotificationStatus.ARCHIVED,
            "timestamp": self.archived_at.isoformat(),
        })
    
    def mark_dismissed(self) -> None:
        """Mark notification as dismissed."""
        self.status = NotificationStatus.DISMISSED
        self.status_history.append({
            "status": NotificationStatus.DISMISSED,
            "timestamp": datetime.utcnow().isoformat(),
        })
    
    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for API responses."""
        return {
            "notification_id": self.notification_id,
            "user_id": self.user_id,
            "organization_id": self.organization_id,
            "type": self.notification_type.value,
            "title": self.title,
            "message": self.message,
            "data": self.data,
            "channels": [c.value for c in self.channels],
            "priority": self.priority,
            "status": self.status.value,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "delivered_at": self.delivered_at.isoformat() if self.delivered_at else None,
            "read_at": self.read_at.isoformat() if self.read_at else None,
            "action_url": self.action_url,
            "tags": self.tags,
        }


@dataclass
class NotificationPreference:
    """User notification preferences."""
    user_id: str
    organization_id: str | None = None
    
    # Channel preferences
    in_app_enabled: bool = True
    email_enabled: bool = False
    webhook_enabled: bool = False
    
    # Type preferences
    notification_types: dict[NotificationType, bool] = field(default_factory=dict)
    
    # Delivery preferences
    preferred_channels: list[NotificationChannel] = field(
        default_factory=lambda: [NotificationChannel.IN_APP]
    )
    
    # Quiet hours
    quiet_hours_start: str | None = None  # "22:00"
    quiet_hours_end: str | None = None    # "08:00"
    quiet_hours_timezone: str | None = None  # "UTC"
    
    # Rate limiting
    max_notifications_per_hour: int = 50
    
    # DND
    do_not_disturb: bool = False
    
    # Webhook
    webhook_url: str | None = None
    webhook_secret: str | None = None
    
    # Metadata
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)


@dataclass
class NotificationTemplate:
    """Notification template for consistent formatting."""
    name: str
    template_id: str = field(default_factory=lambda: f"template-{uuid4().hex}")
    description: str | None = None
    notification_type: NotificationType | None = None
    
    # Template content
    title_template: str = ""
    message_template: str = ""
    
    # Default channels
    default_channels: list[NotificationChannel] = field(
        default_factory=lambda: [NotificationChannel.IN_APP]
    )
    
    # Default priority
    default_priority: int = 0
    
    # Metadata
    is_active: bool = True
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)


@dataclass
class DeliveryAttempt:
    """Record of a notification delivery attempt."""
    notification_id: str
    channel: NotificationChannel
    status: str  # "sent", "delivered", "failed", "bounced"
    attempt_id: str = field(default_factory=lambda: f"attempt-{uuid4().hex}")
    
    # For failed deliveries
    error: str | None = None
    
    # Timestamps
    created_at: datetime = field(default_factory=datetime.utcnow)
    completed_at: datetime | None = None
    
    # Response
    response: dict[str, Any] | None = None
    
    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "attempt_id": self.attempt_id,
            "notification_id": self.notification_id,
            "channel": self.channel.value,
            "status": self.status,
            "error": self.error,
            "created_at": self.created_at.isoformat(),
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
        }
