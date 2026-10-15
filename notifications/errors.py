"""Notification service errors."""

from typing import Any, Optional


class NotificationError(Exception):
    """Base class for notification errors."""
    code: str = "NOTIFY_000"
    error_type: str = "notification_error"
    
    def __init__(
        self,
        message: str,
        code: Optional[str] = None,
        notification_id: Optional[str] = None,
        user_id: Optional[str] = None,
        details: Optional[dict] = None,
        cause: Optional[Exception] = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        if code:
            self.code = code
        self.notification_id = notification_id
        self.user_id = user_id
        self.details = details
        self.cause = cause


class NotificationNotFoundError(NotificationError):
    """Notification not found."""
    code = "NOTIFY_001"
    
    def __init__(self, notification_id: str, user_id: Optional[str] = None) -> None:
        super().__init__(
            message=f"Notification not found: {notification_id}",
            code=self.code,
            notification_id=notification_id,
            user_id=user_id,
        )


class NotificationDeliveryError(NotificationError):
    """Failed to deliver notification."""
    code = "NOTIFY_002"
    
    def __init__(
        self,
        notification_id: str,
        channel: str,
        reason: str,
        user_id: Optional[str] = None,
        attempt: int = 1,
        max_attempts: int = 3,
    ) -> None:
        super().__init__(
            message=f"Failed to deliver notification {notification_id} via {channel}: {reason}",
            code=self.code,
            notification_id=notification_id,
            user_id=user_id,
            details={
                "channel": channel,
                "reason": reason,
                "attempt": attempt,
                "max_attempts": max_attempts,
            },
        )
        self.channel = channel
        self.reason = reason
        self.attempt = attempt
        self.max_attempts = max_attempts


class NotificationTemplateNotFoundError(NotificationError):
    """Notification template not found."""
    code = "NOTIFY_003"
    
    def __init__(self, template_id: str) -> None:
        super().__init__(
            message=f"Notification template not found: {template_id}",
            code=self.code,
            details={"template_id": template_id},
        )
        self.template_id = template_id


class UserPreferencesNotFoundError(NotificationError):
    """User notification preferences not found."""
    code = "NOTIFY_004"
    
    def __init__(self, user_id: str) -> None:
        super().__init__(
            message=f"User notification preferences not found: {user_id}",
            code=self.code,
            user_id=user_id,
        )


class DuplicateNotificationError(NotificationError):
    """Duplicate notification detected."""
    code = "NOTIFY_005"
    
    def __init__(self, notification_id: str, duplicate_of: str, user_id: Optional[str] = None) -> None:
        super().__init__(
            message=f"Duplicate notification {notification_id} of {duplicate_of}",
            code=self.code,
            notification_id=notification_id,
            user_id=user_id,
            details={"duplicate_of": duplicate_of},
        )
        self.duplicate_of = duplicate_of


class RateLimitExceededError(NotificationError):
    """Notification rate limit exceeded."""
    code = "NOTIFY_006"
    
    def __init__(self, user_id: str, current: int, limit: int) -> None:
        super().__init__(
            message=f"Notification rate limit exceeded for user {user_id}: {current}/{limit}",
            code=self.code,
            user_id=user_id,
            details={"current": current, "limit": limit},
        )
