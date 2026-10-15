"""Payment API routes for the PeoplePay 360 Gateway.

This module provides HTTP handlers for payment-related endpoints that integrate
with the payment service.
"""

from __future__ import annotations

import json
from typing import Any
from http.server import BaseHTTPRequestHandler

from payment import (
    get_payment_manager,
    reset_payment_manager,
    PaymentRequest,
    PaymentResponse,
    PaymentStatus,
    PaymentMethod,
    PaymentAction,
    Currency,
    CheckoutRequest,
    CheckoutSession,
    WebhookEvent,
    WebhookEventType,
    Approval,
    ApprovalStatus,
)
from payment.errors import (
    PaymentNotFoundError,
    PaymentFailedError,
    ApprovalRequiredError,
    ApprovalDeniedError,
    IdempotencyConflictError,
    WebhookVerificationError,
    InvalidWebhookPayloadError,
)


class PaymentRoutes:
    """Payment API route handlers."""
    
    def __init__(self, handler: BaseHTTPRequestHandler):
        self.handler = handler
        self.payment_manager = get_payment_manager()
    
    def handle_payment_request(self, method: str, path_parts: list[str], body: dict[str, Any], user: str) -> tuple[int, dict[str, Any] | list[dict[str, Any]]]:
        """Handle payment-related requests."""
        if method == "POST" and path_parts == ["payments"]:
            return self._create_payment(body, user)
        elif method == "GET" and len(path_parts) >= 1 and path_parts[0] == "payments":
            if len(path_parts) == 1:
                return self._list_payments([], user)
            elif len(path_parts) == 2:
                return self._get_payment(path_parts[1])
            else:
                return self._list_payments(path_parts[1:], user)
        elif method == "POST" and len(path_parts) >= 2 and path_parts[0] == "payments":
            payment_id = path_parts[1]
            if len(path_parts) > 2 and path_parts[2] == "capture":
                return self._capture_payment(payment_id, body)
            elif len(path_parts) > 2 and path_parts[2] == "refund":
                return self._refund_payment(payment_id, body)
            elif len(path_parts) > 2 and path_parts[2] == "cancel":
                return self._cancel_payment(payment_id, body)
        elif method == "POST" and path_parts[:2] == ["payments", "checkout"]:
            return self._create_checkout_session(body, user)
        elif method == "GET" and path_parts[:2] == ["checkout", "sessions"]:
            if len(path_parts) == 3:
                return self._get_checkout_session(path_parts[2])
            else:
                return self._list_checkout_sessions()
        elif method == "POST" and path_parts == ["webhooks", "verify"]:
            return self._verify_webhook(body)
        elif method == "POST" and path_parts == ["webhooks"]:
            return self._process_webhook(body)
        else:
            return 404, {"error": "not_found", "message": f"No route for payment API {path_parts}"}
    
    def _create_payment(self, body: dict[str, Any], user: str) -> tuple[int, dict[str, Any]]:
        """Create a new payment."""
        try:
            request = PaymentRequest(
                payment_id=body.get("payment_id"),
                order_id=body.get("order_id"),
                transaction_id=body.get("transaction_id"),
                amount=body["amount"],
                currency=Currency(body.get("currency", "USD")),
                method=PaymentMethod(body.get("method", "SANDBOX")),
                user_id=user,
                organization_id=body.get("organization_id"),
                requires_approval=body.get("requires_approval", True),
                approved_by=body.get("approved_by"),
                approval_token=body.get("approval_token"),
                idempotency_key=body.get("idempotency_key"),
                metadata=body.get("metadata", {}),
                callback_url=body.get("callback_url"),
            )
            response = self.payment_manager.create_payment(request)
            return 200, response.model_dump()
        except (ValueError, TypeError) as e:
            return 400, {"error": "validation_error", "message": str(e)}
        except PaymentFailedError as e:
            return 400, {"error": "payment_failed", "message": str(e)}
        except Exception as e:
            return 500, {"error": "internal_error", "message": str(e)}
    
    def _get_payment(self, payment_id: str) -> tuple[int, dict[str, Any]]:
        """Get payment details."""
        try:
            response = self.payment_manager.get_payment(payment_id)
            return 200, response.model_dump()
        except PaymentNotFoundError:
            return 404, {"error": "not_found", "message": f"Payment not found: {payment_id}"}
    
    def _list_payments(self, path_parts: list[str], user: str) -> tuple[int, list[dict[str, Any]]]:
        """List payments."""
        try:
            user_id = path_parts[0] if path_parts and path_parts[0] != "" else None
            organization_id = path_parts[1] if len(path_parts) > 1 else None
            status = PaymentStatus(path_parts[2]) if len(path_parts) > 2 else None
            
            payments = self.payment_manager.list_payments(
                user_id=user_id,
                organization_id=organization_id,
                status=status,
                limit=100,
                offset=0
            )
            return 200, [p.model_dump() for p in payments]
        except Exception as e:
            return 500, [{"error": "internal_error", "message": str(e)}]
    
    def _capture_payment(self, payment_id: str, body: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        """Capture a payment."""
        try:
            amount = body.get("amount")
            idempotency_key = body.get("idempotency_key")
            response = self.payment_manager.capture_payment(payment_id, amount, idempotency_key)
            return 200, response.model_dump()
        except PaymentNotFoundError:
            return 404, {"error": "not_found", "message": f"Payment not found: {payment_id}"}
        except PaymentFailedError as e:
            return 400, {"error": "payment_failed", "message": str(e)}
    
    def _refund_payment(self, payment_id: str, body: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        """Refund a payment."""
        try:
            amount = body.get("amount")
            reason = body.get("reason")
            idempotency_key = body.get("idempotency_key")
            response = self.payment_manager.refund_payment(payment_id, amount, reason, idempotency_key)
            return 200, response.model_dump()
        except PaymentNotFoundError:
            return 404, {"error": "not_found", "message": f"Payment not found: {payment_id}"}
        except PaymentFailedError as e:
            return 400, {"error": "payment_failed", "message": str(e)}
    
    def _cancel_payment(self, payment_id: str, body: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        """Cancel a payment."""
        try:
            reason = body.get("reason")
            response = self.payment_manager.cancel_payment(payment_id, reason)
            return 200, response.model_dump()
        except PaymentNotFoundError:
            return 404, {"error": "not_found", "message": f"Payment not found: {payment_id}"}
    
    def _create_checkout_session(self, body: dict[str, Any], user: str) -> tuple[int, dict[str, Any]]:
        """Create a checkout session."""
        try:
            request = CheckoutRequest(
                order_id=body["order_id"],
                user_id=user,
                organization_id=body.get("organization_id"),
                amount=body.get("amount"),
                currency=Currency(body.get("currency", "USD")),
                method=PaymentMethod(body.get("method", "SANDBOX")),
                require_approval=body.get("require_approval", True),
                auto_capture=body.get("auto_capture", False),
                callback_url=body.get("callback_url"),
                success_url=body.get("success_url"),
                cancel_url=body.get("cancel_url"),
                idempotency_key=body.get("idempotency_key"),
                metadata=body.get("metadata", {}),
            )
            session = self.payment_manager.create_checkout_session(request)
            return 200, session.model_dump()
        except (ValueError, TypeError) as e:
            return 400, {"error": "validation_error", "message": str(e)}
    
    def _get_checkout_session(self, session_id: str) -> tuple[int, dict[str, Any]]:
        """Get checkout session."""
        try:
            session = self.payment_manager.get_checkout_session(session_id)
            return 200, session.model_dump()
        except Exception:
            return 404, {"error": "not_found", "message": f"Checkout session not found: {session_id}"}
    
    def _list_checkout_sessions(self) -> tuple[int, list[dict[str, Any]]]:
        """List checkout sessions."""
        try:
            sessions = list(self.payment_manager._checkout_sessions.values())
            return 200, [s.model_dump() for s in sessions]
        except Exception as e:
            return 500, [{"error": "internal_error", "message": str(e)}]
    
    def _verify_webhook(self, body: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        """Verify a webhook signature."""
        try:
            payload = body.get("payload", {})
            signature = body.get("signature")
            secret = body.get("secret")
            
            event = WebhookEvent(
                event_id="test",
                event_type=WebhookEventType(body.get("event_type", "payment.authorized")),
                data=payload,
                signature=signature,
            )
            
            verified = self.payment_manager.webhook.verify_event_signature(event, secret)
            return 200, {"verified": verified}
        except WebhookVerificationError as e:
            return 400, {"error": "verification_failed", "message": str(e)}
    
    def _process_webhook(self, body: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        """Process an incoming webhook."""
        try:
            event = self.payment_manager.process_webhook(body, body.get("signature"))
            return 200, event.model_dump()
        except WebhookVerificationError as e:
            return 400, {"error": "verification_failed", "message": str(e)}
        except InvalidWebhookPayloadError as e:
            return 400, {"error": "invalid_payload", "message": str(e)}


def create_payment_routes_handler():
    """Factory to create payment routes handler."""
    return PaymentRoutes
