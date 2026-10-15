"""Data models for authentication and authorization."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any
from pydantic import BaseModel, Field, field_validator
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from shared.schemas import UserRole as SharedUserRole, Permission as SharedPermission


# =============================================================================
# ROLES AND PERMISSIONS
# =============================================================================

class RoleType(str, Enum):
    """System role types."""
    SYSTEM = "system"
    ORGANIZATION = "organization"
    CUSTOM = "custom"


class Role(BaseModel):
    """Role definition with permissions."""
    role_id: str = Field(..., description="Unique role identifier")
    name: str = Field(..., description="Role name")
    description: str | None = Field(default=None, description="Role description")
    role_type: RoleType = Field(default=RoleType.CUSTOM, description="Role type")
    permissions: list[str] = Field(default_factory=list, description="List of permission codes")
    is_default: bool = Field(default=False, description="Whether this is a default role")
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    
    # System roles
    @classmethod
    def system_admin(cls) -> "Role":
        return cls(
            role_id="system_admin",
            name="System Administrator",
            description="Full access to all system functionality",
            role_type=RoleType.SYSTEM,
            permissions=["*"],  # All permissions
            is_default=False,
        )
    
    @classmethod
    def org_admin(cls) -> "Role":
        return cls(
            role_id="org_admin",
            name="Organization Administrator",
            description="Full access to organization resources",
            role_type=RoleType.ORGANIZATION,
            permissions=[
                "org:admin",
                "org:manage_members",
                "org:manage_budgets",
                "org:view",
                "transaction:create",
                "transaction:read",
                "transaction:update",
                "transaction:approve",
                "transaction:cancel",
                "commerce:cart",
                "commerce:checkout",
                "commerce:order",
                "commerce:payment",
                "evidence:read",
                "evidence:write",
                "agent:read",
                "agent:execute",
                "supplier:read",
                "supplier:write",
                "product:read",
                "product:write",
            ],
            is_default=False,
        )
    
    @classmethod
    def user(cls) -> "Role":
        return cls(
            role_id="user",
            name="User",
            description="Standard user with basic access",
            role_type=RoleType.ORGANIZATION,
            permissions=[
                "org:view",
                "transaction:create",
                "transaction:read",
                "commerce:cart",
                "evidence:read",
                "agent:read",
                "supplier:read",
                "product:read",
            ],
            is_default=True,
        )
    
    @classmethod
    def viewer(cls) -> "Role":
        return cls(
            role_id="viewer",
            name="Viewer",
            description="Read-only access to organization resources",
            role_type=RoleType.ORGANIZATION,
            permissions=[
                "org:view",
                "transaction:read",
                "evidence:read",
                "agent:read",
                "supplier:read",
                "product:read",
            ],
            is_default=False,
        )
    
    @classmethod
    def default_roles(cls) -> dict[str, "Role"]:
        """Get all default system roles."""
        return {
            "system_admin": cls.system_admin(),
            "org_admin": cls.org_admin(),
            "user": cls.user(),
            "viewer": cls.viewer(),
        }


# =============================================================================
# PERMISSIONS
# =============================================================================

class PermissionCategory(str, Enum):
    """Permission categories."""
    SYSTEM = "system"
    ORGANIZATION = "org"
    TRANSACTION = "transaction"
    COMMERCE = "commerce"
    EVIDENCE = "evidence"
    AGENT = "agent"
    WORKFLOW = "workflow"
    SUPPLIER = "supplier"
    PRODUCT = "product"
    SUSTAINABILITY = "sustainability"
    NOTIFICATION = "notification"
    AUDIT = "audit"
    SETTINGS = "settings"


class Permission(BaseModel):
    """Permission definition."""
    permission_id: str = Field(..., description="Unique permission identifier")
    code: str = Field(..., description="Permission code (e.g., 'transaction:create')")
    name: str = Field(..., description="Human-readable name")
    description: str | None = Field(default=None, description="Description")
    category: PermissionCategory = Field(default=PermissionCategory.SYSTEM)
    is_sensitive: bool = Field(default=False, description="Whether this is a sensitive action")
    requires_approval: bool = Field(default=False, description="Whether this requires additional approval")
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    
    @property
    def category_prefix(self) -> str:
        """Get the category prefix from the code."""
        if ':' in self.code:
            return self.code.split(':')[0]
        return self.category.value
    
    @classmethod
    def from_code(cls, code: str) -> "Permission":
        """Create a permission from a code string."""
        category = PermissionCategory.SYSTEM
        if ':' in code:
            prefix = code.split(':')[0]
            try:
                category = PermissionCategory(prefix)
            except ValueError:
                pass
        
        return cls(
            permission_id=f"perm_{code.replace(':', '_')}",
            code=code,
            name=code.replace(':', '_').replace('_', ' ').title(),
            category=category,
        )
    
    @classmethod
    def default_permissions(cls) -> dict[str, "Permission"]:
        """Get all default permissions."""
        perms = {}
        
        # System permissions
        system_perms = [
            "system:admin",
            "system:config",
            "system:audit",
        ]
        
        # Organization permissions
        org_perms = [
            "org:admin",
            "org:manage_members",
            "org:manage_budgets",
            "org:view",
        ]
        
        # Transaction permissions
        txn_perms = [
            "transaction:create",
            "transaction:read",
            "transaction:update",
            "transaction:approve",
            "transaction:cancel",
        ]
        
        # Commerce permissions
        commerce_perms = [
            "commerce:cart",
            "commerce:checkout",
            "commerce:order",
            "commerce:payment",
            "commerce:refund",
        ]
        
        # Evidence permissions
        evidence_perms = [
            "evidence:read",
            "evidence:write",
            "evidence:analyze",
        ]
        
        # Agent permissions
        agent_perms = [
            "agent:read",
            "agent:execute",
            "agent:approve",
        ]
        
        # Workflow permissions
        workflow_perms = [
            "workflow:create",
            "workflow:manage",
            "workflow:read",
        ]
        
        # Supplier permissions
        supplier_perms = [
            "supplier:read",
            "supplier:write",
        ]
        
        # Product permissions
        product_perms = [
            "product:read",
            "product:write",
        ]
        
        # Sustainability permissions
        sustainability_perms = [
            "sustainability:read",
            "sustainability:analyze",
        ]
        
        # Notification permissions
        notification_perms = [
            "notification:read",
            "notification:manage",
        ]
        
        # Audit permissions
        audit_perms = [
            "audit:read",
            "audit:export",
        ]
        
        # Settings permissions
        settings_perms = [
            "settings:read",
            "settings:manage",
        ]
        
        for perm_code in (*system_perms, *org_perms, *txn_perms, *commerce_perms,
                         *evidence_perms, *agent_perms, *workflow_perms,
                         *supplier_perms, *product_perms, *sustainability_perms,
                         *notification_perms, *audit_perms, *settings_perms):
            perms[perm_code] = cls.from_code(perm_code)
        
        # Mark sensitive permissions
        sensitive_perms = [
            "system:admin",
            "org:admin",
            "org:manage_members",
            "transaction:approve",
            "commerce:payment",
            "commerce:refund",
            "agent:approve",
        ]
        for code in sensitive_perms:
            if code in perms:
                perms[code].is_sensitive = True
        
        # Mark permissions requiring approval
        approval_perms = [
            "commerce:payment",
            "commerce:refund",
        ]
        for code in approval_perms:
            if code in perms:
                perms[code].requires_approval = True
        
        return perms


# =============================================================================
# USER MODELS
# =============================================================================

class UserStatus(str, Enum):
    """User account status."""
    ACTIVE = "active"
    INACTIVE = "inactive"
    SUSPENDED = "suspended"
    PENDING = "pending"
    LOCKED = "locked"


class UserType(str, Enum):
    """User type."""
    HUMAN = "human"
    SERVICE = "service"
    AGENT = "agent"
    BOT = "bot"


class User(BaseModel):
    """User account."""
    user_id: str = Field(..., description="Unique user identifier")
    email: str | None = Field(default=None, description="Email address")
    display_name: str = Field(..., description="Display name")
    user_type: UserType = Field(default=UserType.HUMAN, description="User type")
    status: UserStatus = Field(default=UserStatus.PENDING, description="Account status")
    
    # Authentication
    password_hash: str | None = Field(default=None, description="Password hash (bcrypt)")
    password_set: bool = Field(default=False, description="Whether password is set")
    mfa_enabled: bool = Field(default=False, description="Whether MFA is enabled")
    mfa_methods: list[str] = Field(default_factory=list, description="Configured MFA methods")
    
    # Profile
    first_name: str | None = Field(default=None, description="First name")
    last_name: str | None = Field(default=None, description="Last name")
    phone: str | None = Field(default=None, description="Phone number")
    timezone: str | None = Field(default=None, description="Timezone")
    locale: str | None = Field(default=None, description="Locale")
    avatar_url: str | None = Field(default=None, description="Avatar URL")
    
    # Security
    last_login_at: datetime | None = Field(default=None, description="Last login timestamp")
    failed_login_attempts: int = Field(default=0, ge=0, description="Failed login attempts")
    password_last_changed: datetime | None = Field(default=None, description="Password last changed")
    
    # Timestamps
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    
    # External IDs
    external_ids: dict[str, str] = Field(default_factory=dict, description="External identity provider IDs")
    
    @field_validator('email')
    @classmethod
    def validate_email(cls, v: str | None) -> str | None:
        if v is None:
            return None
        v = v.lower().strip()
        if not v:
            return None
        if '@' not in v or '.' not in v.split('@')[-1]:
            raise ValueError("Invalid email format")
        return v
    
    @property
    def full_name(self) -> str:
        """Get full name."""
        if self.first_name and self.last_name:
            return f"{self.first_name} {self.last_name}"
        return self.display_name
    
    @property
    def is_active(self) -> bool:
        """Whether the user account is active."""
        return self.status == UserStatus.ACTIVE
    
    @property
    def is_locked(self) -> bool:
        """Whether the user account is locked."""
        return self.status == UserStatus.LOCKED
    
    @property
    def is_suspended(self) -> bool:
        """Whether the user account is suspended."""
        return self.status == UserStatus.SUSPENDED
    
    @property
    def can_authenticate(self) -> bool:
        """Whether the user can authenticate."""
        return self.is_active and not self.is_locked and self.password_set
    
    def to_dict(self, include_secrets: bool = False) -> dict[str, Any]:
        """Convert to dictionary, optionally excluding secrets."""
        data = self.model_dump(exclude_none=True)
        if not include_secrets:
            data.pop('password_hash', None)
            data.pop('mfa_methods', None)
            data.pop('external_ids', None)
        return data


# =============================================================================
# ORGANIZATION MODELS
# =============================================================================

class OrganizationStatus(str, Enum):
    """Organization status."""
    ACTIVE = "active"
    INACTIVE = "inactive"
    SUSPENDED = "suspended"
    PENDING = "pending"


class OrganizationPlan(str, Enum):
    """Organization subscription plan."""
    FREE = "free"
    BASIC = "basic"
    PROFESSIONAL = "professional"
    ENTERPRISE = "enterprise"


class Organization(BaseModel):
    """Organization."""
    organization_id: str = Field(..., description="Unique organization identifier")
    name: str = Field(..., description="Organization name")
    display_name: str | None = Field(default=None, description="Display name")
    description: str | None = Field(default=None, description="Description")
    
    # Status and plan
    status: OrganizationStatus = Field(default=OrganizationStatus.PENDING)
    plan: OrganizationPlan = Field(default=OrganizationPlan.FREE)
    
    # Domain and branding
    domain: str | None = Field(default=None, description="Primary domain")
    domains: list[str] = Field(default_factory=list, description="All domains")
    logo_url: str | None = Field(default=None, description="Logo URL")
    color_scheme: dict[str, str] = Field(default_factory=dict, description="Color scheme")
    
    # Settings
    default_currency: str = Field(default="USD", description="Default currency")
    timezone: str = Field(default="UTC", description="Timezone")
    locale: str = Field(default="en", description="Locale")
    
    # Budget and limits
    default_budget_limit: int | None = Field(default=None, description="Default budget limit (minor units)")
    monthly_spend_limit: int | None = Field(default=None, description="Monthly spend limit (minor units)")
    require_approval_for_payments: bool = Field(default=True, description="Require approval for payments")
    payment_approval_threshold: int | None = Field(default=None, description="Payment amount requiring approval (minor units)")
    
    # Security
    require_mfa: bool = Field(default=False, description="Require MFA for members")
    session_timeout_hours: int = Field(default=24, ge=1, description="Session timeout in hours")
    
    # Timestamps
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    
    # External IDs
    external_id: str | None = Field(default=None, description="External system ID")
    
    @property
    def is_active(self) -> bool:
        """Whether the organization is active."""
        return self.status == OrganizationStatus.ACTIVE
    
    @property
    def is_enterprise(self) -> bool:
        """Whether the organization is on enterprise plan."""
        return self.plan == OrganizationPlan.ENTERPRISE
    
    @property
    def can_spend(self) -> bool:
        """Whether the organization can make payments."""
        return self.is_active and (self.monthly_spend_limit is None or self.monthly_spend_limit > 0)
    
    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return self.model_dump(exclude_none=True)


# =============================================================================
# MEMBERSHIP MODELS
# =============================================================================

class MembershipStatus(str, Enum):
    """Membership status."""
    ACTIVE = "active"
    PENDING = "pending"
    SUSPENDED = "suspended"
    REMOVED = "removed"


class MembershipRole(BaseModel):
    """Membership role assignment."""
    role_id: str = Field(..., description="Role identifier")
    role_name: str = Field(..., description="Role name")
    permissions: list[str] = Field(default_factory=list, description="Role permissions")


class OrganizationMembership(BaseModel):
    """User membership in an organization."""
    membership_id: str = Field(..., description="Unique membership identifier")
    user_id: str = Field(..., description="User identifier")
    organization_id: str = Field(..., description="Organization identifier")
    
    # Role and permissions
    roles: list[MembershipRole] = Field(default_factory=list, description="Assigned roles")
    permissions: list[str] = Field(default_factory=list, description="Explicit permissions")
    
    # Status
    status: MembershipStatus = Field(default=MembershipStatus.PENDING)
    
    # Invitation
    invited_by: str | None = Field(default=None, description="Who invited the user")
    invited_at: datetime | None = Field(default=None, description="Invitation timestamp")
    invitation_token: str | None = Field(default=None, description="Invitation token")
    invitation_expires_at: datetime | None = Field(default=None, description="Invitation expiry")
    
    # Timestamps
    joined_at: datetime | None = Field(default=None, description="When user joined")
    left_at: datetime | None = Field(default=None, description="When user left")
    
    @property
    def is_active(self) -> bool:
        """Whether the membership is active."""
        return self.status == MembershipStatus.ACTIVE and self.left_at is None
    
    @property
    def role_names(self) -> list[str]:
        """Get list of role names."""
        return [r.role_name for r in self.roles]
    
    @property
    def all_permissions(self) -> set[str]:
        """Get all permissions (from roles + explicit)."""
        perms = set(self.permissions)
        for role in self.roles:
            perms.update(role.permissions)
        return perms
    
    def has_permission(self, permission_code: str) -> bool:
        """Check if membership has a specific permission."""
        return permission_code in self.all_permissions or "*" in self.all_permissions
    
    def has_any_permission(self, permission_codes: list[str]) -> bool:
        """Check if membership has any of the specified permissions."""
        return any(self.has_permission(code) for code in permission_codes)
    
    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        data = self.model_dump(exclude_none=True)
        data["role_names"] = self.role_names
        data["is_active"] = self.is_active
        return data


# =============================================================================
# SESSION MODELS
# =============================================================================

class SessionType(str, Enum):
    """Session type."""
    WEB = "web"
    API = "api"
    CLI = "cli"
    SERVICE = "service"


class Session(BaseModel):
    """User authentication session."""
    session_id: str = Field(..., description="Unique session identifier")
    user_id: str = Field(..., description="User identifier")
    organization_id: str | None = Field(default=None, description="Current organization")
    
    # Authentication
    access_token: str | None = Field(default=None, description="Access token (JWT)")
    refresh_token: str | None = Field(default=None, description="Refresh token")
    access_token_expires_at: datetime | None = Field(default=None, description="Access token expiry")
    refresh_token_expires_at: datetime | None = Field(default=None, description="Refresh token expiry")
    
    # Session info
    session_type: SessionType = Field(default=SessionType.WEB, description="Session type")
    ip_address: str | None = Field(default=None, description="Client IP address")
    user_agent: str | None = Field(default=None, description="Client user agent")
    device_id: str | None = Field(default=None, description="Device identifier")
    
    # Context
    current_organization_id: str | None = Field(default=None, description="Current organization context")
    context: dict[str, Any] = Field(default_factory=dict, description="Session context")
    
    # Security
    is_verified: bool = Field(default=False, description="Whether session is verified")
    mfa_verified: bool = Field(default=False, description="Whether MFA was verified")
    mfa_method: str | None = Field(default=None, description="MFA method used")
    
    # Timestamps
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    last_used_at: datetime | None = Field(default=None, description="Last activity timestamp")
    
    @property
    def is_expired(self) -> bool:
        """Whether the session has expired."""
        if self.access_token_expires_at is None:
            return True
        return datetime.now(timezone.utc) >= self.access_token_expires_at
    
    @property
    def is_refresh_expired(self) -> bool:
        """Whether the refresh token has expired."""
        if self.refresh_token_expires_at is None:
            return True
        return datetime.now(timezone.utc) >= self.refresh_token_expires_at
    
    def to_dict(self, include_tokens: bool = False) -> dict[str, Any]:
        """Convert to dictionary."""
        data = self.model_dump(exclude_none=True)
        if not include_tokens:
            data.pop('access_token', None)
            data.pop('refresh_token', None)
        return data


# =============================================================================
# PASSWORD RESET MODELS
# =============================================================================

class PasswordResetRequest(BaseModel):
    """Password reset request."""
    request_id: str = Field(..., description="Unique request identifier")
    user_id: str = Field(..., description="User identifier")
    email: str = Field(..., description="User email")
    
    # Security
    token: str = Field(..., description="Reset token")
    token_hash: str | None = Field(default=None, description="Token hash")
    expires_at: datetime = Field(..., description="Token expiry")
    
    # Timestamps
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    used_at: datetime | None = Field(default=None, description="When token was used")
    
    @property
    def is_expired(self) -> bool:
        """Whether the reset request has expired."""
        return datetime.now(timezone.utc) >= self.expires_at
    
    @property
    def is_used(self) -> bool:
        """Whether the reset request has been used."""
        return self.used_at is not None


# =============================================================================
# AUDIT MODELS
# =============================================================================

class AuthAuditEvent(BaseModel):
    """Authentication audit event."""
    event_id: str = Field(..., description="Unique event identifier")
    user_id: str | None = Field(default=None, description="User identifier")
    organization_id: str | None = Field(default=None, description="Organization identifier")
    
    # Event info
    event_type: str = Field(..., description="Event type")
    action: str = Field(..., description="Action performed")
    resource: str = Field(..., description="Resource affected")
    resource_id: str | None = Field(default=None, description="Resource identifier")
    
    # Context
    ip_address: str | None = Field(default=None, description="Client IP address")
    user_agent: str | None = Field(default=None, description="Client user agent")
    session_id: str | None = Field(default=None, description="Session identifier")
    
    # Outcome
    success: bool = Field(default=True, description="Whether the action succeeded")
    error: str | None = Field(default=None, description="Error message")
    
    # Metadata
    metadata: dict[str, Any] = Field(default_factory=dict, description="Additional metadata")
    
    # Timestamps
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
