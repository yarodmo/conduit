"""
Conduit Backend — Email Tasks (Celery Async)
Prompt 3: "Emails siempre a Celery queue, nunca síncronos"

All email tasks run on the 'general' queue → worker-general container.

Bliss Systems LLC — APEX Standard
"""

import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

import structlog

from app.core.config import settings
from app.tasks.celery_app import celery_app

logger = structlog.get_logger()

TEMPLATE_DIR = Path(__file__).parent.parent / "templates" / "emails"


def _send_email(to: str, subject: str, html_body: str) -> None:
    """Send email via SMTP. Used by all email tasks."""
    if not settings.SMTP_HOST or settings.APP_ENV == "development":
        logger.info(
            "email_skipped_dev_mode",
            to=to,
            subject=subject,
        )
        return

    msg = MIMEMultipart("alternative")
    msg["From"] = f"{settings.SMTP_FROM_NAME} <{settings.SMTP_FROM_EMAIL}>"
    msg["To"] = to
    msg["Subject"] = subject
    msg.attach(MIMEText(html_body, "html"))

    try:
        with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT) as server:
            server.starttls()
            if settings.SMTP_USER:
                server.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
            server.send_message(msg)

        logger.info("email_sent", to=to, subject=subject)

    except Exception as e:
        logger.error("email_failed", to=to, subject=subject, error=str(e))
        raise


def _load_template(name: str) -> str:
    """Load HTML email template."""
    path = TEMPLATE_DIR / name
    if path.exists():
        return path.read_text()
    # Fallback template
    return "<html><body>{content}</body></html>"


@celery_app.task(
    name="app.tasks.email_tasks.send_welcome_email",
    bind=True,
    max_retries=3,
    default_retry_delay=60,
)
def send_welcome_email(self, email: str, full_name: str) -> dict:
    """
    Send welcome email after registration.
    Prompt 3: register → welcome email.
    """
    try:
        template = _load_template("welcome.html")
        html = template.replace("{{full_name}}", full_name)
        html = html.replace("{{login_url}}", f"{settings.FRONTEND_URL}/login")

        _send_email(email, "Welcome to Conduit — MEP Intelligence. Connected.", html)
        return {"status": "sent", "to": email}

    except Exception as exc:
        logger.error("welcome_email_failed", email=email, error=str(exc))
        self.retry(exc=exc)


@celery_app.task(
    name="app.tasks.email_tasks.send_invitation_email",
    bind=True,
    max_retries=3,
    default_retry_delay=60,
)
def send_invitation_email(
    self,
    email: str,
    org_name: str,
    token: str,
    inviter_name: str,
) -> dict:
    """
    Send organization invitation email.
    Prompt 3: "POST /organizations/invite → invitar por email (Celery)"
    """
    try:
        template = _load_template("invitation.html")
        accept_url = f"{settings.FRONTEND_URL}/accept-invite/{token}"

        html = template.replace("{{org_name}}", org_name)
        html = html.replace("{{inviter_name}}", inviter_name)
        html = html.replace("{{accept_url}}", accept_url)

        _send_email(
            email,
            f"You're invited to join {org_name} on Conduit",
            html,
        )
        return {"status": "sent", "to": email}

    except Exception as exc:
        logger.error("invitation_email_failed", email=email, error=str(exc))
        self.retry(exc=exc)


@celery_app.task(
    name="app.tasks.email_tasks.send_password_reset_email",
    bind=True,
    max_retries=3,
    default_retry_delay=60,
)
def send_password_reset_email(self, email: str, token: str) -> dict:
    """
    Send password reset email with OTP link.
    Prompt 3: "POST /auth/forgot-password → email con link OTP"
    """
    try:
        template = _load_template("password_reset.html")
        reset_url = f"{settings.FRONTEND_URL}/reset-password/{token}"

        html = template.replace("{{reset_url}}", reset_url)

        _send_email(email, "Reset Your Conduit Password", html)
        return {"status": "sent", "to": email}

    except Exception as exc:
        logger.error("reset_email_failed", email=email, error=str(exc))
        self.retry(exc=exc)


@celery_app.task(
    name="app.tasks.email_tasks.send_new_device_alert",
    bind=True,
    max_retries=3,
    default_retry_delay=60,
)
def send_new_device_alert(
    self,
    email: str,
    device_info: str,
    ip_address: str,
) -> dict:
    """
    Alert user of login from new device.
    Prompt 3: "Notificación push al usuario en login desde nuevo dispositivo"
    """
    try:
        template = _load_template("new_device_alert.html")
        html = template.replace("{{device_info}}", device_info or "Unknown device")
        html = html.replace("{{ip_address}}", ip_address or "Unknown IP")

        _send_email(email, "New Login to Your Conduit Account", html)
        return {"status": "sent", "to": email}

    except Exception as exc:
        logger.error("device_alert_failed", email=email, error=str(exc))
        self.retry(exc=exc)
