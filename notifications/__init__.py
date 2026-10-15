"""PeoplePay 360 - Notification and Communication Service.

This module provides a centralized notification system for:
- In-app notifications
- Approval requests
- Order status changes
- Payment status changes
- Failed workflow notifications
- Risk alerts
- Supplier updates
- Task completion alerts
- System health alerts

Features:
- Notification preferences per user
- Delivery history
- Read/unread state
- Notification templates
- Retry policies
- Notification deduplication
"""

from notifications.models import (
    Notification,
    NotificationStatus,
    NotificationType,
    NotificationPreference,
    NotificationTemplate,
    DeliveryAttempt,
)
from notifications.service import NotificationService, get_notification_service
from notifications.errors import (
    NotificationError,
    NotificationNotFoundError,
    NotificationDeliveryError,
)

__all__ = [
    "Notification",
    "NotificationStatus",
    "NotificationType",
    "NotificationPreference",
    "NotificationTemplate",
    "DeliveryAttempt",
    "NotificationService",
    "get_notification_service",
    "NotificationError",
    "NotificationNotFoundError",
    "NotificationDeliveryError",
]
