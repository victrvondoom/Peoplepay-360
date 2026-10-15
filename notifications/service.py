"""Notification service implementation."""

from __future__ import annotations

import hashlib
import json
import threading
from datetime import datetime, timezone
from queue import Queue
from typing import Any, Callable

from notifications.models import (
    Notification,
    NotificationChannel,
    NotificationPreference,
    NotificationStatus,
    NotificationTemplate,
    NotificationType,
    DeliveryAttempt,
)
from notifications.errors import (
    NotificationError,
    NotificationNotFoundError,
    NotificationDeliveryError,
    NotificationTemplateNotFoundError,
    UserPreferencesNotFoundError,
    DuplicateNotificationError,
    RateLimitExceededError,
)


class NotificationService:
    """Central notification service.
    
    Manages creation, delivery, and tracking of notifications across
    multiple channels.
    """
    
    def __init__(self) -> None:
        self._notifications: dict[str, Notification] = {}
        self._preferences: dict[str, NotificationPreference] = {}
        self._templates: dict[str, NotificationTemplate] = {}
        self._delivery_queue = Queue()
        self._delivery_workers: list[threading.Thread] = []
        self._running = False
        self._lock = threading.RLock()
        self._fingerprint_cache: set[str] = set()
        self._rate_limits: dict[str, dict[str, int]] = {}  # user_id -> {hour_key: count}
    
    def start(self, num_workers: int = 2) -> None:
        """Start the notification delivery workers."""
        with self._lock:
            if self._running:
                return
            self._running = True
            
            for i in range(num_workers):
                worker = threading.Thread(
                    target=self._delivery_worker,
                    name=f"notification-worker-{i}",
                    daemon=True,
                )
                worker.start()
                self._delivery_workers.append(worker)
    
    def stop(self) -> None:
        """Stop the notification delivery workers."""
        with self._lock:
            self._running = False
        
        for worker in self._delivery_workers:
            worker.join(timeout=5)
        
        self._delivery_workers = []
    
    def _delivery_worker(self) -> None:
        """Worker thread that processes delivery queue."""
        while True:
            with self._lock:
                if not self._running:
                    break
            
            try:
                # Get notification with timeout
                notification = self._delivery_queue.get(timeout=1)
                self._deliver_notification(notification)
                self._delivery_queue.task_done()
            except Exception:
                # Queue empty or timeout
                pass
    
    def create_notification(
        self,
        user_id: str,
        notification_type: NotificationType,
        title: str,
        message: str,
        data: dict[str, Any] | None = None,
        channels: list[NotificationChannel] | None = None,
        organization_id: str | None = None,
        priority: int = 0,
        related_resource_id: str | None = None,
        related_resource_type: str | None = None,
        action_url: str | None = None,
        deduplication_id: str | None = None,
        tags: list[str] | None = None,
    ) -> Notification:
        """Create a new notification."""
        with self._lock:
            # Check rate limit
            self._check_rate_limit(user_id)
            
            # Create notification
            notification = Notification(
                user_id=user_id,
                organization_id=organization_id,
                notification_type=notification_type,
                title=title,
                message=message,
                data=data or {},
                channels=channels or [NotificationChannel.IN_APP],
                priority=priority,
                related_resource_id=related_resource_id,
                related_resource_type=related_resource_type,
                action_url=action_url,
                deduplication_id=deduplication_id,
                tags=tags or [],
            )
            
            # Generate fingerprint for deduplication
            fingerprint = self._generate_fingerprint(notification)
            notification.fingerprint = fingerprint
            
            # Check for duplicates
            if fingerprint in self._fingerprint_cache:
                raise DuplicateNotificationError(
                    notification_id=notification.notification_id,
                    duplicate_of=self._fingerprint_cache[fingerprint],
                    user_id=user_id,
                )
            
            self._fingerprint_cache.add(fingerprint)
            self._notifications[notification.notification_id] = notification
            
            # Queue for delivery
            self._delivery_queue.put(notification)
            
            return notification
    
    def _generate_fingerprint(self, notification: Notification) -> str:
        """Generate a fingerprint for deduplication."""
        # Include user, type, and key data
        fingerprint_data = {
            "user_id": notification.user_id,
            "type": notification.notification_type.value,
            "title": notification.title,
            "related_resource_id": notification.related_resource_id,
            "related_resource_type": notification.related_resource_type,
        }
        fingerprint_str = json.dumps(fingerprint_data, sort_keys=True)
        return hashlib.sha256(fingerprint_str.encode()).hexdigest()
    
    def _check_rate_limit(self, user_id: str) -> None:
        """Check if user has exceeded notification rate limit."""
        now = datetime.utcnow()
        hour_key = now.strftime("%Y-%m-%d-%H")
        
        with self._lock:
            if user_id not in self._rate_limits:
                self._rate_limits[user_id] = {}
            
            user_limits = self._rate_limits[user_id]
            
            # Clean up old hours
            user_limits = {
                k: v for k, v in user_limits.items()
                if k >= now.strftime("%Y-%m-%d-%H")
            }
            
            count = user_limits.get(hour_key, 0)
            
            # Get user's limit (default 50)
            limit = 50
            try:
                prefs = self.get_preferences(user_id)
                limit = prefs.max_notifications_per_hour
            except UserPreferencesNotFoundError:
                pass
            
            if count >= limit:
                raise RateLimitExceededError(user_id, count, limit)
            
            user_limits[hour_key] = count + 1
            self._rate_limits[user_id] = user_limits
    
    def _deliver_notification(self, notification: Notification) -> None:
        """Deliver a notification through all configured channels."""
        for channel in notification.channels:
            try:
                self._deliver_via_channel(notification, channel)
            except NotificationDeliveryError as e:
                notification.mark_failed(channel, e.reason)
            except Exception as e:
                notification.mark_failed(channel, str(e))
        
        # If at least one channel succeeded, mark as delivered
        if any(
            s["status"] == NotificationStatus.DELIVERED
            for s in notification.status_history
        ):
            notification.status = NotificationStatus.DELIVERED
        else:
            notification.status = NotificationStatus.FAILED
    
    def _deliver_via_channel(
        self,
        notification: Notification,
        channel: NotificationChannel,
    ) -> None:
        """Deliver notification via a specific channel."""
        # Check if channel is enabled for user
        if notification.user_id:
            try:
                prefs = self.get_preferences(notification.user_id)
                if channel == NotificationChannel.IN_APP:
                    if not prefs.in_app_enabled:
                        return
                elif channel == NotificationChannel.EMAIL:
                    if not prefs.email_enabled:
                        return
                elif channel == NotificationChannel.WEBHOOK:
                    if not prefs.webhook_enabled:
                        return
            except UserPreferencesNotFoundError:
                # No preferences, assume all channels enabled
                pass
        
        # Actually deliver (in production, this would call external services)
        # For now, just mark as delivered
        notification.mark_delivered(channel)
        
        # Record delivery attempt
        attempt = DeliveryAttempt(
            notification_id=notification.notification_id,
            channel=channel,
            status="delivered",
        )
        # In a real implementation, we'd store this
    
    def get_notification(self, notification_id: str, user_id: str | None = None) -> Notification:
        """Get a notification by ID."""
        with self._lock:
            if notification_id not in self._notifications:
                raise NotificationNotFoundError(notification_id, user_id)
            
            notification = self._notifications[notification_id]
            
            # Check user access
            if user_id and notification.user_id != user_id:
                raise NotificationNotFoundError(notification_id, user_id)
            
            return notification
    
    def list_notifications(
        self,
        user_id: str,
        status: NotificationStatus | None = None,
        notification_type: NotificationType | None = None,
        limit: int = 50,
        offset: int = 0,
        unread_only: bool = False,
    ) -> list[Notification]:
        """List notifications for a user."""
        with self._lock:
            notifications = [
                n for n in self._notifications.values()
                if n.user_id == user_id
            ]
            
            if status:
                notifications = [n for n in notifications if n.status == status]
            
            if notification_type:
                notifications = [n for n in notifications if n.notification_type == notification_type]
            
            if unread_only:
                notifications = [
                    n for n in notifications
                    if n.status == NotificationStatus.DELIVERED and n.read_at is None
                ]
            
            # Sort by created_at descending
            notifications.sort(key=lambda n: n.created_at, reverse=True)
            
            return notifications[offset:offset + limit]
    
    def mark_read(self, notification_id: str, user_id: str) -> Notification:
        """Mark a notification as read."""
        with self._lock:
            if notification_id not in self._notifications:
                raise NotificationNotFoundError(notification_id, user_id)
            
            notification = self._notifications[notification_id]
            
            if notification.user_id != user_id:
                raise NotificationNotFoundError(notification_id, user_id)
            
            notification.mark_read()
            return notification
    
    def mark_all_read(self, user_id: str) -> int:
        """Mark all notifications for a user as read."""
        with self._lock:
            count = 0
            for notification in self._notifications.values():
                if notification.user_id == user_id and notification.read_at is None:
                    notification.mark_read()
                    count += 1
            return count
    
    def get_unread_count(self, user_id: str) -> int:
        """Get the number of unread notifications for a user."""
        with self._lock:
            return sum(
                1 for n in self._notifications.values()
                if n.user_id == user_id
                and n.status == NotificationStatus.DELIVERED
                and n.read_at is None
            )
    
    def create_preferences(
        self,
        user_id: str,
        organization_id: str | None = None,
        in_app_enabled: bool = True,
        email_enabled: bool = False,
        webhook_enabled: bool = False,
        preferred_channels: list[NotificationChannel] | None = None,
        max_notifications_per_hour: int = 50,
        webhook_url: str | None = None,
        webhook_secret: str | None = None,
    ) -> NotificationPreference:
        """Create notification preferences for a user."""
        with self._lock:
            prefs = NotificationPreference(
                user_id=user_id,
                organization_id=organization_id,
                in_app_enabled=in_app_enabled,
                email_enabled=email_enabled,
                webhook_enabled=webhook_enabled,
                preferred_channels=preferred_channels or [NotificationChannel.IN_APP],
                max_notifications_per_hour=max_notifications_per_hour,
                webhook_url=webhook_url,
                webhook_secret=webhook_secret,
            )
            self._preferences[user_id] = prefs
            return prefs
    
    def get_preferences(self, user_id: str) -> NotificationPreference:
        """Get notification preferences for a user."""
        with self._lock:
            if user_id not in self._preferences:
                # Return defaults
                return NotificationPreference(user_id=user_id)
            return self._preferences[user_id]
    
    def update_preferences(
        self,
        user_id: str,
        updates: dict[str, Any],
    ) -> NotificationPreference:
        """Update notification preferences for a user."""
        with self._lock:
            if user_id not in self._preferences:
                raise UserPreferencesNotFoundError(user_id)
            
            prefs = self._preferences[user_id]
            for key, value in updates.items():
                if hasattr(prefs, key):
                    setattr(prefs, key, value)
            
            prefs.updated_at = datetime.utcnow()
            return prefs
    
    def create_template(
        self,
        name: str,
        notification_type: NotificationType | None = None,
        title_template: str = "",
        message_template: str = "",
        default_channels: list[NotificationChannel] | None = None,
        default_priority: int = 0,
        description: str | None = None,
    ) -> NotificationTemplate:
        """Create a notification template."""
        with self._lock:
            template = NotificationTemplate(
                name=name,
                notification_type=notification_type,
                title_template=title_template,
                message_template=message_template,
                default_channels=default_channels or [NotificationChannel.IN_APP],
                default_priority=default_priority,
                description=description,
            )
            self._templates[template.template_id] = template
            return template
    
    def get_template(self, template_id: str) -> NotificationTemplate:
        """Get a notification template by ID."""
        with self._lock:
            if template_id not in self._templates:
                raise NotificationTemplateNotFoundError(template_id)
            return self._templates[template_id]
    
    def delete_notification(self, notification_id: str, user_id: str) -> None:
        """Delete a notification."""
        with self._lock:
            if notification_id not in self._notifications:
                raise NotificationNotFoundError(notification_id, user_id)
            
            notification = self._notifications[notification_id]
            
            if notification.user_id != user_id:
                raise NotificationNotFoundError(notification_id, user_id)
            
            del self._notifications[notification_id]
    
    def create_from_template(
        self,
        template_id: str,
        user_id: str,
        template_data: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> Notification:
        """Create a notification from a template."""
        try:
            template = self.get_template(template_id)
        except NotificationTemplateNotFoundError:
            raise
        
        # Format title and message with template data
        title = template.title_template
        message = template.message_template
        
        if template_data:
            try:
                title = title.format(**template_data)
            except Exception:
                pass
            
            try:
                message = message.format(**template_data)
            except Exception:
                pass
        
        return self.create_notification(
            user_id=user_id,
            notification_type=template.notification_type or kwargs.get("notification_type"),
            title=title,
            message=message,
            channels=kwargs.get("channels") or template.default_channels,
            priority=kwargs.get("priority") or template.default_priority,
            data=kwargs.get("data"),
            organization_id=kwargs.get("organization_id"),
            related_resource_id=kwargs.get("related_resource_id"),
            related_resource_type=kwargs.get("related_resource_type"),
            action_url=kwargs.get("action_url"),
            tags=kwargs.get("tags"),
        )


# Global notification service instance
_notification_service: NotificationService | None = None
_service_lock = threading.Lock()


def get_notification_service() -> NotificationService:
    """Get the global notification service instance."""
    global _notification_service
    with _service_lock:
        if _notification_service is None:
            _notification_service = NotificationService()
        return _notification_service


def reset_notification_service() -> None:
    """Reset the global notification service (for testing)."""
    global _notification_service
    with _service_lock:
        if _notification_service is not None:
            _notification_service.stop()
        _notification_service = None
