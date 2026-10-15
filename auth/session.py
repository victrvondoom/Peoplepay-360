"""Session management for authentication."""

from __future__ import annotations

import hashlib
import secrets
import time
from datetime import datetime, timedelta, timezone
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from auth.models import Session as SessionModel, User
    from auth.errors import SessionError, SessionExpiredError, SessionNotFoundError


class SessionManager:
    """Manages user authentication sessions.
    
    This class handles session creation, validation, and lifecycle management.
    In production, you would want to use a persistent store for sessions.
    """
    
    def __init__(
        self,
        session_timeout_hours: int = 24,
        session_rolling: bool = True,
        max_sessions_per_user: int | None = None,
    ):
        """Initialize the session manager.
        
        Args:
            session_timeout_hours: Session timeout in hours
            session_rolling: Whether to extend session on activity
            max_sessions_per_user: Maximum sessions per user (None for unlimited)
        """
        self.session_timeout_hours = session_timeout_hours
        self.session_rolling = session_rolling
        self.max_sessions_per_user = max_sessions_per_user
        
        # In-memory session store
        self._sessions: dict[str, SessionModel] = {}
        self._user_sessions: dict[str, set[str]] = {}  # user_id -> set of session_ids
    
    def create_session(
        self,
        user: "User",
        organization_id: str | None = None,
        session_type: str = "web",
        ip_address: str | None = None,
        user_agent: str | None = None,
        device_id: str | None = None,
        context: dict[str, Any] | None = None,
    ) -> "SessionModel":
        """Create a new session.
        
        Args:
            user: The authenticated user
            organization_id: The current organization
            session_type: Type of session (web, api, cli, service)
            ip_address: Client IP address
            user_agent: Client user agent
            device_id: Device identifier
            context: Additional session context
            
        Returns:
            The created session
        """
        from auth.models import Session, SessionType
        from auth.errors import TooManySessionsError
        
        # Check session limit
        if self.max_sessions_per_user is not None:
            user_session_ids = self._user_sessions.get(user.user_id, set())
            if len(user_session_ids) >= self.max_sessions_per_user:
                raise TooManySessionsError(self.max_sessions_per_user)
        
        # Calculate expiry
        now = datetime.now(timezone.utc)
        expires_at = now + timedelta(hours=self.session_timeout_hours)
        refresh_expires_at = now + timedelta(days=7)  # 7 days for refresh token
        
        session = Session(
            session_id=self._generate_session_id(),
            user_id=user.user_id,
            organization_id=organization_id,
            access_token=self._generate_token(),
            refresh_token=self._generate_token(),
            access_token_expires_at=expires_at,
            refresh_token_expires_at=refresh_expires_at,
            session_type=SessionType(session_type),
            ip_address=ip_address,
            user_agent=user_agent,
            device_id=device_id,
            current_organization_id=organization_id,
            context=context or {},
            is_verified=True,
            last_used_at=now,
        )
        
        # Store session
        self._sessions[session.session_id] = session
        
        # Track user sessions
        if user.user_id not in self._user_sessions:
            self._user_sessions[user.user_id] = set()
        self._user_sessions[user.user_id].add(session.session_id)
        
        return session
    
    def get_session(self, session_id: str) -> "SessionModel | None":
        """Get a session by ID.
        
        Args:
            session_id: The session identifier
            
        Returns:
            The session or None if not found
        """
        session = self._sessions.get(session_id)
        
        # Update last used if rolling sessions
        if session and self.session_rolling:
            self._update_session_activity(session)
        
        return session
    
    def get_session_by_access_token(self, token: str) -> "SessionModel | None":
        """Get a session by access token.
        
        Args:
            token: The access token
            
        Returns:
            The session or None if not found
        """
        for session in self._sessions.values():
            if session.access_token == token:
                return self.get_session(session.session_id)
        return None
    
    def get_session_by_refresh_token(self, token: str) -> "SessionModel | None":
        """Get a session by refresh token.
        
        Args:
            token: The refresh token
            
        Returns:
            The session or None if not found
        """
        for session in self._sessions.values():
            if session.refresh_token == token:
                return session
        return None
    
    def get_user_sessions(self, user_id: str) -> list["SessionModel"]:
        """Get all active sessions for a user.
        
        Args:
            user_id: The user identifier
            
        Returns:
            List of active sessions
        """
        session_ids = self._user_sessions.get(user_id, set())
        return [self._sessions[sid] for sid in session_ids if sid in self._sessions]
    
    def refresh_session(self, refresh_token: str) -> "SessionModel | None":
        """Refresh a session using a refresh token.
        
        Args:
            refresh_token: The refresh token
            
        Returns:
            The refreshed session or None
            
        Raises:
            SessionError: If refresh token is invalid or expired
        """
        from auth.errors import SessionExpiredError, SessionNotFoundError
        
        session = self.get_session_by_refresh_token(refresh_token)
        
        if session is None:
            raise SessionNotFoundError("Refresh token not found")
        
        if session.is_refresh_expired:
            raise SessionExpiredError("Refresh token has expired")
        
        # Create new access token and update expiry
        now = datetime.now(timezone.utc)
        new_expires = now + timedelta(hours=self.session_timeout_hours)
        
        session.access_token = self._generate_token()
        session.access_token_expires_at = new_expires
        session.last_used_at = now
        
        return session
    
    def invalidate_session(self, session_id: str | None = None, token: str | None = None) -> bool:
        """Invalidate a session.
        
        Args:
            session_id: The session identifier
            token: The access or refresh token
            
        Returns:
            True if a session was invalidated, False otherwise
        """
        session = None
        
        if session_id:
            session = self._sessions.pop(session_id, None)
        elif token:
            session = self.get_session_by_access_token(token)
            if session is None:
                session = self.get_session_by_refresh_token(token)
            if session:
                self._sessions.pop(session.session_id, None)
        
        if session:
            # Remove from user sessions
            if session.user_id in self._user_sessions:
                self._user_sessions[session.user_id].discard(session.session_id)
            
            # Clear tokens
            session.access_token = None
            session.refresh_token = None
            
            return True
        
        return False
    
    def invalidate_user_sessions(self, user_id: str) -> int:
        """Invalidate all sessions for a user.
        
        Args:
            user_id: The user identifier
            
        Returns:
            Number of sessions invalidated
        """
        count = 0
        session_ids = list(self._user_sessions.get(user_id, set()))
        
        for session_id in session_ids:
            if session_id in self._sessions:
                del self._sessions[session_id]
                count += 1
        
        # Clear user session tracking
        if user_id in self._user_sessions:
            self._user_sessions[user_id].clear()
        
        return count
    
    def invalidate_all_sessions(self) -> int:
        """Invalidate all sessions.
        
        Returns:
            Number of sessions invalidated
        """
        count = len(self._sessions)
        self._sessions.clear()
        self._user_sessions.clear()
        return count
    
    def cleanup_expired_sessions(self) -> int:
        """Remove expired sessions.
        
        Returns:
            Number of sessions removed
        """
        now = datetime.now(timezone.utc)
        expired = [
            sid for sid, session in self._sessions.items()
            if session.is_expired
        ]
        
        for sid in expired:
            session = self._sessions[sid]
            # Remove from user tracking
            if session.user_id in self._user_sessions:
                self._user_sessions[session.user_id].discard(sid)
            del self._sessions[sid]
        
        return len(expired)
    
    def validate_session(self, session_id: str | None = None, token: str | None = None) -> "SessionModel | None":
        """Validate a session.
        
        Args:
            session_id: The session identifier
            token: The access token
            
        Returns:
            The valid session or None
        """
        session = None
        
        if session_id:
            session = self.get_session(session_id)
        elif token:
            session = self.get_session_by_access_token(token)
        
        if session is None:
            return None
        
        if session.is_expired:
            self.invalidate_session(session_id=session.session_id)
            return None
        
        # Update activity
        self._update_session_activity(session)
        
        return session
    
    def set_session_context(self, session_id: str, key: str, value: Any) -> bool:
        """Set context value for a session.
        
        Args:
            session_id: The session identifier
            key: The context key
            value: The context value
            
        Returns:
            True if successful, False if session not found
        """
        session = self._sessions.get(session_id)
        if session:
            session.context[key] = value
            session.updated_at = datetime.now(timezone.utc)
            return True
        return False
    
    def get_session_context(self, session_id: str, key: str, default: Any = None) -> Any:
        """Get context value from a session.
        
        Args:
            session_id: The session identifier
            key: The context key
            default: Default value if key not found
            
        Returns:
            The context value or default
        """
        session = self._sessions.get(session_id)
        if session:
            return session.context.get(key, default)
        return default
    
    def switch_organization(self, session_id: str, organization_id: str) -> bool:
        """Switch the current organization for a session.
        
        Args:
            session_id: The session identifier
            organization_id: The new organization identifier
            
        Returns:
            True if successful, False if session not found
        """
        session = self._sessions.get(session_id)
        if session:
            session.current_organization_id = organization_id
            session.updated_at = datetime.now(timezone.utc)
            return True
        return False
    
    def _update_session_activity(self, session: "SessionModel") -> None:
        """Update session activity timestamp."""
        session.last_used_at = datetime.now(timezone.utc)
        
        # Extend expiry if rolling sessions
        if self.session_rolling:
            session.access_token_expires_at = session.last_used_at + timedelta(
                hours=self.session_timeout_hours
            )
    
    def _generate_session_id(self) -> str:
        """Generate a unique session ID."""
        import uuid
        return f"sess_{uuid.uuid4().hex[:16]}"
    
    def _generate_token(self) -> str:
        """Generate a cryptographically secure random token."""
        return secrets.token_urlsafe(32)
    
    def _hash_token(self, token: str) -> str:
        """Hash a token for storage."""
        return hashlib.sha256(token.encode()).hexdigest()
