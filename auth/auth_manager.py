"""Authentication manager for PeoplePay 360.

This module provides centralized authentication management including:
- Token issuance and verification
- Session management
- User authentication
- Organization switching
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import os
import secrets
import time
from contextvars import ContextVar
from datetime import datetime, timedelta, timezone
from typing import Any, Callable
from uuid import uuid4
from functools import wraps

from jose import JWTError, jwt
from passlib.context import CryptContext
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from auth.models import (
        User,
        Organization,
        Session,
        OrganizationMembership,
    )
    from auth.errors import (
        AuthenticationError,
        SessionError,
        UserNotFoundError,
        InvalidCredentialsError,
    )

# Configure logging
logger = logging.getLogger(__name__)


# =============================================================================
# TYPE ALIASES
# =============================================================================
TokenGenerator = Callable[[str, datetime, dict[str, Any]], str]
TokenVerifier = Callable[[str], dict[str, Any]]


# =============================================================================
# CONFIGURATION
# =============================================================================

class AuthConfig:
    """Authentication configuration."""
    
    def __init__(
        self,
        # JWT settings
        jwt_secret: str | None = None,
        jwt_algorithm: str = "HS256",
        jwt_expiry_hours: int = 24,
        jwt_refresh_hours: int = 168,  # 7 days
        
        # Session settings
        session_timeout_hours: int = 24,
        session_rolling: bool = True,
        session_cookie_name: str = "peoplepay_session",
        
        # Token settings
        token_version: str = "v1",
        access_token_expiry_hours: int = 24,
        refresh_token_expiry_hours: int = 168,
        
        # Password settings
        password_min_length: int = 8,
        password_require_uppercase: bool = True,
        password_require_lowercase: bool = True,
        password_require_digit: bool = True,
        password_require_special: bool = True,
        
        # MFA settings
        mfa_issuer: str = "PeoplePay",
        mfa_required: bool = False,
        
        # Security
        max_failed_attempts: int = 5,
        lockout_duration_minutes: int = 15,
        
        # Environment
        environment: str = "development",
    ):
        self.jwt_secret = jwt_secret or os.getenv("PEOPLEPAY_JWT_SECRET")
        self.jwt_algorithm = jwt_algorithm
        self.jwt_expiry_hours = jwt_expiry_hours
        self.jwt_refresh_hours = jwt_refresh_hours
        
        self.session_timeout_hours = session_timeout_hours
        self.session_rolling = session_rolling
        self.session_cookie_name = session_cookie_name
        
        self.token_version = token_version
        self.access_token_expiry_hours = access_token_expiry_hours
        self.refresh_token_expiry_hours = refresh_token_expiry_hours
        
        self.password_min_length = password_min_length
        self.password_require_uppercase = password_require_uppercase
        self.password_require_lowercase = password_require_lowercase
        self.password_require_digit = password_require_digit
        self.password_require_special = password_require_special
        
        self.mfa_issuer = mfa_issuer
        self.mfa_required = mfa_required
        
        self.max_failed_attempts = max_failed_attempts
        self.lockout_duration_minutes = lockout_duration_minutes
        
        self.environment = environment or os.getenv("PEOPLEPAY_ENVIRONMENT", "development")
    
    @property
    def is_production(self) -> bool:
        return self.environment.lower() == "production"
    
    @property
    def is_development(self) -> bool:
        return self.environment.lower() == "development"


# =============================================================================
# TOKEN MANAGEMENT
# =============================================================================

class TokenManager:
    """JWT token management."""
    
    def __init__(self, config: AuthConfig):
        self.config = config
        self._pwd_context = CryptContext(schemes=["bcrypt"], deprecated=["auto"])
    
    def _get_jwt_secret(self) -> str:
        """Get JWT secret, raising error if not configured in production."""
        secret = self.config.jwt_secret
        if secret is None and self.config.is_production:
            raise RuntimeError("JWT secret is required in production")
        return secret or "development-secret"
    
    def create_access_token(
        self,
        user_id: str,
        organization_id: str | None = None,
        permissions: list[str] | None = None,
        roles: list[str] | None = None,
        extra_claims: dict[str, Any] | None = None,
    ) -> str:
        """Create an access JWT token."""
        now = datetime.now(timezone.utc)
        expires = now + timedelta(hours=self.config.access_token_expiry_hours)
        
        payload = {
            "sub": user_id,
            "iat": int(now.timestamp()),
            "exp": int(expires.timestamp()),
            "jti": str(uuid4()),
            "token_type": "access",
            "version": self.config.token_version,
        }
        
        if organization_id:
            payload["org_id"] = organization_id
        if permissions:
            payload["permissions"] = permissions
        if roles:
            payload["roles"] = roles
        if extra_claims:
            payload.update(extra_claims)
        
        secret = self._get_jwt_secret()
        token = jwt.encode(payload, secret, algorithm=self.config.jwt_algorithm)
        
        return token
    
    def create_refresh_token(
        self,
        user_id: str,
        extra_claims: dict[str, Any] | None = None,
    ) -> str:
        """Create a refresh JWT token."""
        now = datetime.now(timezone.utc)
        expires = now + timedelta(hours=self.config.refresh_token_expiry_hours)
        
        payload = {
            "sub": user_id,
            "iat": int(now.timestamp()),
            "exp": int(expires.timestamp()),
            "jti": str(uuid4()),
            "token_type": "refresh",
            "version": self.config.token_version,
        }
        
        if extra_claims:
            payload.update(extra_claims)
        
        secret = self._get_jwt_secret()
        token = jwt.encode(payload, secret, algorithm=self.config.jwt_algorithm)
        
        return token
    
    def create_invitation_token(
        self,
        organization_id: str,
        email: str,
        role_ids: list[str],
        expires_in_hours: int = 168,  # 7 days
    ) -> str:
        """Create an organization invitation token."""
        now = datetime.now(timezone.utc)
        expires = now + timedelta(hours=expires_in_hours)
        
        payload = {
            "org_id": organization_id,
            "email": email,
            "roles": role_ids,
            "iat": int(now.timestamp()),
            "exp": int(expires.timestamp()),
            "jti": str(uuid4()),
            "token_type": "invitation",
            "version": self.config.token_version,
        }
        
        secret = self._get_jwt_secret()
        token = jwt.encode(payload, secret, algorithm=self.config.jwt_algorithm)
        
        return token
    
    def create_password_reset_token(
        self,
        user_id: str,
        email: str,
        expires_in_hours: int = 24,
    ) -> str:
        """Create a password reset token."""
        now = datetime.now(timezone.utc)
        expires = now + timedelta(hours=expires_in_hours)
        
        payload = {
            "sub": user_id,
            "email": email,
            "iat": int(now.timestamp()),
            "exp": int(expires.timestamp()),
            "jti": str(uuid4()),
            "token_type": "password_reset",
            "version": self.config.token_version,
        }
        
        secret = self._get_jwt_secret()
        token = jwt.encode(payload, secret, algorithm=self.config.jwt_algorithm)
        
        return token
    
    def decode_token(self, token: str) -> dict[str, Any]:
        """Decode and verify a JWT token."""
        try:
            secret = self._get_jwt_secret()
            payload = jwt.decode(
                token,
                secret,
                algorithms=[self.config.jwt_algorithm],
            )
            return payload
        except JWTError as e:
            logger.warning(f"Token decode failed: {e}")
            raise AuthenticationError(f"Invalid token: {str(e)}")
    
    def verify_token(self, token: str, token_type: str | None = None) -> dict[str, Any]:
        """Verify a token and return its payload."""
        payload = self.decode_token(token)
        
        if token_type and payload.get("token_type") != token_type:
            raise AuthenticationError(f"Expected {token_type} token, got {payload.get('token_type')}")
        
        # Check expiration
        exp = payload.get("exp")
        if exp is not None and datetime.now(timezone.utc).timestamp() > exp:
            raise AuthenticationError("Token has expired")
        
        return payload
    
    def verify_access_token(self, token: str) -> dict[str, Any]:
        """Verify an access token."""
        return self.verify_token(token, "access")
    
    def verify_refresh_token(self, token: str) -> dict[str, Any]:
        """Verify a refresh token."""
        return self.verify_token(token, "refresh")


# =============================================================================
# SESSION MANAGEMENT
# =============================================================================

class SessionManager:
    """Session management."""
    
    def __init__(self, config: AuthConfig):
        self.config = config
        self.token_manager = TokenManager(config)
        self._sessions: dict[str, "Session"] = {}  # In-memory session store
    
    def create_session(
        self,
        user: "User",
        organization_id: str | None = None,
        session_type: str = "web",
        ip_address: str | None = None,
        user_agent: str | None = None,
        device_id: str | None = None,
    ) -> "Session":
        """Create a new authentication session."""
        from auth.models import Session, SessionType
        
        now = datetime.now(timezone.utc)
        access_expires = now + timedelta(hours=self.config.access_token_expiry_hours)
        refresh_expires = now + timedelta(hours=self.config.refresh_token_expiry_hours)
        
        # Get user permissions
        permissions = list(user.permissions) if hasattr(user, 'permissions') else []
        
        # Create access token
        access_token = self.token_manager.create_access_token(
            user_id=user.user_id,
            organization_id=organization_id,
            permissions=permissions,
        )
        
        # Create refresh token
        refresh_token = self.token_manager.create_refresh_token(
            user_id=user.user_id,
        )
        
        session = Session(
            session_id=str(uuid4()),
            user_id=user.user_id,
            organization_id=organization_id,
            access_token=access_token,
            refresh_token=refresh_token,
            access_token_expires_at=access_expires,
            refresh_token_expires_at=refresh_expires,
            session_type=SessionType(session_type),
            ip_address=ip_address,
            user_agent=user_agent,
            device_id=device_id,
            current_organization_id=organization_id,
            is_verified=True,
            mfa_verified=False,  # Will be set to True if MFA is verified
        )
        
        self._sessions[session.session_id] = session
        
        return session
    
    def get_session(self, session_id: str) -> "Session | None":
        """Get a session by ID."""
        return self._sessions.get(session_id)
    
    def get_session_by_token(self, token: str) -> "Session | None":
        """Get session by access token."""
        for session in self._sessions.values():
            if session.access_token == token:
                return session
        return None
    
    def refresh_session(self, refresh_token: str) -> "Session | None":
        """Refresh a session using a refresh token."""
        # Find session with this refresh token
        session = None
        for s in self._sessions.values():
            if s.refresh_token == refresh_token:
                session = s
                break
        
        if session is None:
            raise SessionError("Invalid refresh token")
        
        if session.is_refresh_expired:
            raise SessionError("Refresh token has expired")
        
        # Verify refresh token
        try:
            payload = self.token_manager.verify_refresh_token(refresh_token)
            if payload.get("sub") != session.user_id:
                raise SessionError("Refresh token user mismatch")
        except AuthenticationError:
            raise SessionError("Invalid refresh token")
        
        # Create new access token
        now = datetime.now(timezone.utc)
        access_expires = now + timedelta(hours=self.config.access_token_expiry_hours)
        
        access_token = self.token_manager.create_access_token(
            user_id=session.user_id,
            organization_id=session.current_organization_id,
        )
        
        # Update session
        session.access_token = access_token
        session.access_token_expires_at = access_expires
        session.last_used_at = now
        
        return session
    
    def invalidate_session(self, session_id: str | None = None, token: str | None = None) -> bool:
        """Invalidate a session."""
        session = None
        
        if session_id:
            session = self._sessions.pop(session_id, None)
        elif token:
            for sid, s in list(self._sessions.items()):
                if s.access_token == token or s.refresh_token == token:
                    session = self._sessions.pop(sid, None)
                    break
        
        if session:
            session.access_token = None
            session.refresh_token = None
            return True
        
        return False
    
    def invalidate_user_sessions(self, user_id: str) -> int:
        """Invalidate all sessions for a user."""
        count = 0
        for sid, session in list(self._sessions.items()):
            if session.user_id == user_id:
                self._sessions.pop(sid, None)
                count += 1
        return count
    
    def invalidate_organization_sessions(self, organization_id: str) -> int:
        """Invalidate all sessions for an organization."""
        count = 0
        for sid, session in list(self._sessions.items()):
            if session.organization_id == organization_id or session.current_organization_id == organization_id:
                self._sessions.pop(sid, None)
                count += 1
        return count
    
    def list_user_sessions(self, user_id: str) -> list["Session"]:
        """List all sessions for a user."""
        return [s for s in self._sessions.values() if s.user_id == user_id]
    
    def cleanup_expired_sessions(self) -> int:
        """Remove expired sessions."""
        now = datetime.now(timezone.utc)
        expired = [
            sid for sid, session in self._sessions.items()
            if session.is_expired
        ]
        for sid in expired:
            self._sessions.pop(sid, None)
        return len(expired)


# =============================================================================
# AUTH MANAGER
# =============================================================================

class AuthManager:
    """Main authentication manager.
    
    This class orchestrates all authentication and authorization operations.
    """
    
    # Singleton instance
    _instance: "AuthManager | None" = None
    
    def __new__(cls, config: AuthConfig | None = None) -> "AuthManager":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self, config: AuthConfig | None = None):
        if AuthManager._instance is not None:
            return
        
        self.config = config or AuthConfig()
        self.token_manager = TokenManager(self.config)
        self.session_manager = SessionManager(self.config)
        
        # In-memory user store (for development/testing)
        self._users: dict[str, "User"] = {}
        self._organizations: dict[str, "Organization"] = {}
        self._memberships: dict[str, "OrganizationMembership"] = {}
        
        # Initialize with gateway compatibility
        self._gateway_secret = os.getenv("BEACON_GATEWAY_SECRET")
    
    @classmethod
    def get_instance(cls) -> "AuthManager":
        """Get the singleton instance."""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance
    
    @classmethod
    def reset(cls) -> None:
        """Reset the singleton (for testing)."""
        cls._instance = None
    
    # =========================================================================
    # TOKEN COMPATIBILITY WITH GATEWAY
    # =========================================================================
    
    def issue_gateway_token(self, user_id: str, ttl_seconds: int = 3600) -> str:
        """Issue a gateway-compatible token (for backward compatibility)."""
        if self._gateway_secret is None:
            raise RuntimeError("Cannot issue gateway token without BEACON_GATEWAY_SECRET")
        
        import base64 as b64
        import time as time_module
        import hmac as hmac_module
        from hashlib import sha256 as sha256_func
        
        expires_at = int(time_module.time()) + ttl_seconds
        
        user_b64 = b64.urlsafe_b64encode(user_id.encode('utf-8')).decode('ascii').rstrip('=')
        
        payload = f"v1.{user_b64}.{expires_at}"
        secret = self._gateway_secret.encode("utf-8")
        digest = hmac_module.new(secret, payload.encode("ascii"), sha256_func).digest()
        signature = b64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")
        
        return f"v1.{user_b64}.{expires_at}.{signature}"
    
    def verify_gateway_token(self, token: str) -> str | None:
        """Verify a gateway token and return user_id (for backward compatibility)."""
        if self._gateway_secret is None:
            # In OPEN mode, accept X-Beacon-User header
            return None
        
        import base64 as b64
        import time as time_module
        import hmac as hmac_module
        from hashlib import sha256 as sha256_func
        
        parts = (token or "").split(".")
        if len(parts) != 4 or parts[0] != "v1":
            return None
        
        _, user_b64, expiry_text, signature = parts
        
        try:
            user_id = b64.urlsafe_b64decode(user_b64 + "==").decode("utf-8")
            expires_at = int(expiry_text)
        except (ValueError, UnicodeDecodeError):
            return None
        
        # Verify signature
        payload = f"v1.{user_b64}.{expires_at}"
        secret = self._gateway_secret.encode("utf-8")
        expected = b64.urlsafe_b64encode(
            hmac_module.new(secret, payload.encode("ascii"), sha256_func).digest()
        ).decode("ascii").rstrip("=")
        
        if not hmac_module.compare_digest(expected, signature):
            return None
        
        # Check expiry
        if time_module.time() >= expires_at:
            return None
        
        if not user_id.strip():
            return None
        
        return user_id
    
    # =========================================================================
    # USER MANAGEMENT
    # =========================================================================
    
    def create_user(
        self,
        email: str,
        display_name: str,
        password: str | None = None,
        user_id: str | None = None,
        user_type: str = "human",
    ) -> "User":
        """Create a new user."""
        from auth.models import User, UserType, UserStatus
        from auth.password import PasswordHasher
        from auth.errors import UserAlreadyExistsError
        
        # Check if user exists
        if email and any(u.email == email for u in self._users.values()):
            raise UserAlreadyExistsError(f"User with email {email} already exists")
        
        user_id = user_id or str(uuid4())
        
        # Hash password if provided
        password_hash = None
        password_set = False
        if password:
            hasher = PasswordHasher()
            password_hash = hasher.hash(password)
            password_set = True
        
        user = User(
            user_id=user_id,
            email=email,
            display_name=display_name,
            user_type=UserType(user_type),
            status=UserStatus.ACTIVE,
            password_hash=password_hash,
            password_set=password_set,
        )
        
        self._users[user.user_id] = user
        
        logger.info(f"Created user: {user.user_id}")
        
        return user
    
    def get_user(self, user_id: str) -> "User | None":
        """Get a user by ID."""
        return self._users.get(user_id)
    
    def get_user_by_email(self, email: str) -> "User | None":
        """Get a user by email."""
        email = email.lower().strip()
        for user in self._users.values():
            if user.email and user.email.lower() == email:
                return user
        return None
    
    def update_user(self, user_id: str, **kwargs: Any) -> "User | None":
        """Update user attributes."""
        user = self._users.get(user_id)
        if user is None:
            return None
        
        for key, value in kwargs.items():
            if hasattr(user, key) and key != "user_id":
                setattr(user, key, value)
        
        user.updated_at = datetime.now(timezone.utc)
        
        return user
    
    def delete_user(self, user_id: str) -> bool:
        """Delete a user."""
        user = self._users.pop(user_id, None)
        if user:
            # Invalidate all sessions
            self.session_manager.invalidate_user_sessions(user_id)
            logger.info(f"Deleted user: {user_id}")
            return True
        return False
    
    def list_users(self) -> list["User"]:
        """List all users."""
        return list(self._users.values())
    
    # =========================================================================
    # ORGANIZATION MANAGEMENT
    # =========================================================================
    
    def create_organization(
        self,
        name: str,
        organization_id: str | None = None,
        description: str | None = None,
    ) -> "Organization":
        """Create a new organization."""
        from auth.models import Organization, OrganizationStatus
        
        organization_id = organization_id or str(uuid4())
        
        org = Organization(
            organization_id=organization_id,
            name=name,
            display_name=name,
            description=description,
            status=OrganizationStatus.ACTIVE,
        )
        
        self._organizations[org.organization_id] = org
        
        logger.info(f"Created organization: {org.organization_id}")
        
        return org
    
    def get_organization(self, organization_id: str) -> "Organization | None":
        """Get an organization by ID."""
        return self._organizations.get(organization_id)
    
    def list_organizations(self) -> list["Organization"]:
        """List all organizations."""
        return list(self._organizations.values())
    
    def delete_organization(self, organization_id: str) -> bool:
        """Delete an organization."""
        org = self._organizations.pop(organization_id, None)
        if org:
            # Invalidate all organization sessions
            self.session_manager.invalidate_organization_sessions(organization_id)
            logger.info(f"Deleted organization: {organization_id}")
            return True
        return False
    
    # =========================================================================
    # MEMBERSHIP MANAGEMENT
    # =========================================================================
    
    def create_membership(
        self,
        user_id: str,
        organization_id: str,
        role_ids: list[str] | None = None,
        membership_id: str | None = None,
        invited_by: str | None = None,
    ) -> "OrganizationMembership":
        """Create a new organization membership."""
        from auth.models import OrganizationMembership, MembershipStatus, MembershipRole
        
        membership_id = membership_id or str(uuid4())
        
        # Get user and organization
        user = self.get_user(user_id)
        org = self.get_organization(organization_id)
        
        if user is None or org is None:
            raise ValueError("User or organization not found")
        
        # Default to user role
        if role_ids is None:
            role_ids = ["user"]
        
        # Create membership roles
        roles = []
        for role_id in role_ids:
            # For now, just use the role_id as name
            roles.append(MembershipRole(
                role_id=role_id,
                role_name=role_id,
                permissions=[],  # Will be populated from role definitions
            ))
        
        membership = OrganizationMembership(
            membership_id=membership_id,
            user_id=user_id,
            organization_id=organization_id,
            roles=roles,
            status=MembershipStatus.ACTIVE,
            invited_by=invited_by,
            invited_at=datetime.now(timezone.utc),
            joined_at=datetime.now(timezone.utc),
        )
        
        self._memberships[membership.membership_id] = membership
        
        logger.info(f"Created membership: {membership.membership_id}")
        
        return membership
    
    def get_membership(self, membership_id: str) -> "OrganizationMembership | None":
        """Get a membership by ID."""
        return self._memberships.get(membership_id)
    
    def get_user_memberships(self, user_id: str) -> list["OrganizationMembership"]:
        """Get all memberships for a user."""
        return [m for m in self._memberships.values() if m.user_id == user_id]
    
    def get_organization_memberships(self, organization_id: str) -> list["OrganizationMembership"]:
        """Get all memberships for an organization."""
        return [m for m in self._memberships.values() if m.organization_id == organization_id]
    
    def delete_membership(self, membership_id: str) -> bool:
        """Delete a membership."""
        membership = self._memberships.pop(membership_id, None)
        if membership:
            # Invalidate sessions for this user in this organization
            self.session_manager.invalidate_organization_sessions(membership.organization_id)
            logger.info(f"Deleted membership: {membership_id}")
            return True
        return False
    
    # =========================================================================
    # AUTHENTICATION
    # =========================================================================
    
    def authenticate(
        self,
        email: str | None = None,
        user_id: str | None = None,
        password: str | None = None,
        token: str | None = None,
        session_id: str | None = None,
    ) -> "User | None":
        """Authenticate a user.
        
        Args:
            email: User email
            user_id: User ID
            password: Password for authentication
            token: Bearer token for authentication
            session_id: Session ID for existing session
        
        Returns:
            Authenticated user or None
        """
        from auth.errors import InvalidCredentialsError, AuthenticationError
        
        user = None
        
        # Try token authentication
        if token:
            try:
                payload = self.token_manager.verify_access_token(token)
                user_id = payload.get("sub")
                if user_id:
                    user = self.get_user(user_id)
            except AuthenticationError:
                pass
        
        # Try session authentication
        if session_id and user is None:
            session = self.session_manager.get_session(session_id)
            if session and not session.is_expired:
                user = self.get_user(session.user_id)
        
        # Try email/password authentication
        if email and password and user is None:
            user = self.get_user_by_email(email)
            if user is None:
                raise InvalidCredentialsError("Invalid email or password")
            
            if not user.password_set:
                raise InvalidCredentialsError("Password not set for user")
            
            hasher = PasswordHasher()
            if not hasher.verify(password, user.password_hash or ""):
                # Increment failed attempts
                user.failed_login_attempts += 1
                if user.failed_login_attempts >= self.config.max_failed_attempts:
                    user.status = "locked"
                raise InvalidCredentialsError("Invalid email or password")
            
            # Reset failed attempts on successful login
            user.failed_login_attempts = 0
            user.last_login_at = datetime.now(timezone.utc)
        
        # Try user_id lookup (for backward compatibility)
        if user_id and user is None:
            user = self.get_user(user_id)
        
        return user
    
    def login(
        self,
        email: str | None = None,
        user_id: str | None = None,
        password: str | None = None,
        organization_id: str | None = None,
        ip_address: str | None = None,
        user_agent: str | None = None,
        device_id: str | None = None,
    ) -> "Session":
        """Authenticate and create a session.
        
        Raises:
            AuthenticationError: If authentication fails
        """
        from auth.errors import InvalidCredentialsError
        
        # Authenticate
        user = self.authenticate(email=email, user_id=user_id, password=password)
        if user is None:
            raise InvalidCredentialsError("Invalid credentials")
        
        if not user.can_authenticate:
            if user.is_locked:
                raise InvalidCredentialsError("Account is locked due to too many failed attempts")
            elif user.is_suspended:
                raise InvalidCredentialsError("Account is suspended")
            elif not user.is_active:
                raise InvalidCredentialsError("Account is not active")
            else:
                raise InvalidCredentialsError("Cannot authenticate")
        
        # Create session
        session = self.session_manager.create_session(
            user=user,
            organization_id=organization_id,
            session_type="web",
            ip_address=ip_address,
            user_agent=user_agent,
            device_id=device_id,
        )
        
        logger.info(f"User logged in: {user.user_id}")
        
        return session
    
    def logout(self, session_id: str | None = None, token: str | None = None) -> bool:
        """Logout a user by invalidating their session."""
        result = self.session_manager.invalidate_session(session_id=session_id, token=token)
        if result:
            logger.info("User logged out")
        return result
    
    def refresh(self, refresh_token: str) -> "Session | None":
        """Refresh an access token."""
        session = self.session_manager.refresh_session(refresh_token)
        if session:
            logger.info(f"Session refreshed: {session.session_id}")
        return session
    
    # =========================================================================
    # PERMISSION CHECKING
    # =========================================================================
    
    def has_permission(
        self,
        user_id: str,
        permission_code: str,
        organization_id: str | None = None,
    ) -> bool:
        """Check if a user has a specific permission."""
        user = self.get_user(user_id)
        if user is None:
            return False
        
        # Check user permissions
        if permission_code in (user.permissions or []):
            return True
        
        # Check organization membership permissions
        if organization_id:
            memberships = [
                m for m in self._memberships.values()
                if m.user_id == user_id and m.organization_id == organization_id
            ]
            for membership in memberships:
                if membership.has_permission(permission_code):
                    return True
        
        # Check if user has wildcard permission
        if "*" in (user.permissions or []):
            return True
        
        return False
    
    def check_permission(
        self,
        user_id: str,
        permission_code: str,
        organization_id: str | None = None,
    ) -> None:
        """Check permission and raise error if not authorized.
        
        Raises:
            AuthorizationError: If user doesn't have permission
        """
        from auth.errors import PermissionDeniedError
        
        if not self.has_permission(user_id, permission_code, organization_id):
            raise PermissionDeniedError(
                permission=permission_code,
                user_id=user_id,
                resource_id=organization_id,
            )
    
    def require_permission(
        self,
        permission_code: str,
        organization_id: str | None = None,
    ):
        """Decorator to require a permission."""
        def decorator(func):
            @wraps(func)
            def wrapper(*args, **kwargs):
                # Extract user_id from args/kwargs or context
                user_id = None
                
                # Try to get user_id from various sources
                # This is a simplified version - in practice you'd want to
                # get it from the request context
                if args:
                    # Assume first arg might be user_id or have user_id
                    if isinstance(args[0], str):
                        user_id = args[0]
                
                if user_id is None and 'user_id' in kwargs:
                    user_id = kwargs['user_id']
                
                if user_id is None:
                    # Try to get from context
                    from auth.auth_manager import _current_user_var
                    user_id = _current_user_var.get()
                
                if user_id:
                    self.check_permission(user_id, permission_code, organization_id)
                
                return func(*args, **kwargs)
            return wrapper
        return decorator
    
    # =========================================================================
    # CONTEXT MANAGEMENT
    # =========================================================================
    
    def set_current_user(self, user: "User | None", organization_id: str | None = None) -> None:
        """Set the current user context."""
        _current_user_var.set(user)
        _current_org_var.set(organization_id)
    
    def get_current_user(self) -> "User | None":
        """Get the current user from context."""
        return _current_user_var.get()
    
    def get_current_organization(self) -> str | None:
        """Get the current organization from context."""
        return _current_org_var.get()
    
    def get_current_session(self) -> "Session | None":
        """Get the current session from context."""
        return _current_session_var.get()


# Context variables for thread-local storage
_current_user_var: ContextVar["User | None"] = ContextVar('current_user', default=None)
_current_org_var: ContextVar[str | None] = ContextVar('current_organization', default=None)
_current_session_var: ContextVar["Session | None"] = ContextVar('current_session', default=None)


# =============================================================================
# MODULE-LEVEL ACCESS
# =============================================================================

def get_auth_manager() -> AuthManager:
    """Get the authentication manager singleton."""
    return AuthManager.get_instance()


# Create a default auth manager instance
auth_manager = AuthManager.get_instance()
