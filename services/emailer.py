from __future__ import annotations

"""Lightweight SMTP email sender for login codes.

Uses aiosmtplib directly and follows the project's existing SMTP env pattern.
"""

import os
from email.message import EmailMessage
from email.utils import formataddr
from typing import Optional

from restailor.app_config import CONFIG
import logging
logger = logging.getLogger(__name__)
from perf.observability import outbound_timed  # PERF


def _truthy(v: Optional[str]) -> bool:
    return str(v or "").strip().lower() in {"1", "true", "yes", "y", "on"}


def _get_smtp_config() -> tuple:
    """Get SMTP configuration for email sending.
    
    Returns: (host, port, mail_from, mail_from_name, app_name, starttls, use_tls, username, password, use_credentials)
    """
    host = (
        os.getenv("MAIL_SERVER")
        or os.getenv("SMTP_SERVER")
        or os.getenv("SMTP_HOST")
    )
    port_s = os.getenv("MAIL_PORT") or os.getenv("SMTP_PORT") or ""
    try:
        port = int(port_s) if port_s else 0
    except Exception:
        port = 0
    mail_from = (
        os.getenv("MAIL_FROM")
        or os.getenv("SMTP_FROM")
        or os.getenv("FROM_EMAIL")
        or "no-reply@example.com"
    )
    mail_from_name = os.getenv("MAIL_FROM_NAME") or ""
    app_name = (CONFIG.get("app", {}) or {}).get("name", "Restailor")
    starttls = _truthy(os.getenv("MAIL_STARTTLS") or os.getenv("SMTP_STARTTLS"))
    use_tls = _truthy(os.getenv("MAIL_SSL_TLS") or os.getenv("SMTP_SSL"))
    username = os.getenv("MAIL_USERNAME")
    password = os.getenv("MAIL_PASSWORD")

    # Optional keyring fallback when env variables are not set
    if (not username or not password) and _truthy(os.getenv("MAIL_USE_CREDENTIALS")):
        try:
            import keyring  # type: ignore
            svc_env = os.getenv("MAIL_KEYRING_SERVICE")
            services = [svc_env] if svc_env else ["restailor", "restailor", "smtp-relay.brevo.com"]
            for svc in [s for s in services if s]:
                if not username:
                    try:
                        v = keyring.get_password(svc, "MAIL_USERNAME")
                        if v:
                            username = v
                    except Exception:
                        pass
                if not password:
                    try:
                        v = keyring.get_password(svc, "MAIL_PASSWORD")
                        if v:
                            password = v
                    except Exception:
                        pass
                if username and password:
                    break
        except Exception:
            # Keyring not available or failed; continue without
            pass
    # Only enable AUTH when both username and password are present
    use_credentials = bool(username and password)
    
    return (host, port, mail_from, mail_from_name, app_name, starttls, use_tls, username, password, use_credentials)


async def send_login_code_email(to: str, code: str, ttl_minutes: int) -> bool:
    """Send a login verification code via SMTP (text and HTML parts).

    Returns True on best-effort success, False on failure. Never raises.
    """
    # Hard-stop in automated tests: do not send real email
    try:
        from restailor.test_flags import is_automated_test_run as _is_auto
        if _is_auto():
            logger.info("email: skipped (automated test run)")
            return True
    except Exception:
        # If detection fails, fall back to env flags below
        pass
    # Global kill-switch (mirror main.py _mail_conf behavior)
    if _truthy(os.getenv("EMAIL_DISABLE_OUTBOUND")) or _truthy(os.getenv("DISABLE_OUTBOUND_EMAIL")):
        logger.info("email: outbound disabled via env")
        return True

    host, port, mail_from, mail_from_name, app_name, starttls, use_tls, username, password, use_credentials = _get_smtp_config()

    if not (host and port and mail_from):
        logger.warning("email: incomplete SMTP config (host=%r, port=%r, from=%r)", bool(host), port, mail_from)
        return False

    # Compose message
    subject = f"Your {app_name} login code"
    text_body = (
        f"Use this verification code to finish signing in to {app_name}: {code}\n\n"
        f"This code expires in {int(ttl_minutes)} minutes. If you didn't request it, you can ignore this email."
    )
    html_body = f"""
    <html>
      <body>
        <p>Use this verification code to finish signing in to <strong>{app_name}</strong>:</p>
        <p style=\"font-size:22px; font-weight:bold; letter-spacing:3px;\">{code}</p>
        <p>This code expires in <strong>{int(ttl_minutes)}</strong> minutes.<br/>
        If you didn't request it, you can ignore this email.</p>
      </body>
    </html>
    """

    msg = EmailMessage()
    try:
        msg["From"] = formataddr((mail_from_name.strip() or "", mail_from)) if mail_from_name else mail_from
    except Exception:
        msg["From"] = mail_from
    msg["To"] = to
    msg["Subject"] = subject
    msg.set_content(text_body)
    msg.add_alternative(html_body, subtype="html")

    try:
        import aiosmtplib  # type: ignore

        # aiosmtplib.send handles starttls/use_tls
        logger.info(
            "email: sending via SMTP host=%s port=%s starttls=%s ssl=%s auth=%s from=%s to=%s",
            host,
            port,
            bool(starttls and not use_tls),
            bool(use_tls),
            bool(use_credentials),
            mail_from,
            to,
        )
        if _truthy(os.getenv("MAIL_USE_CREDENTIALS")) and not use_credentials:
            logger.warning("email: MAIL_USE_CREDENTIALS true but no username/password resolved (check env/keyring)")
        async with outbound_timed("email", host or "smtp", port=port):  # PERF
            await aiosmtplib.send(
                msg,
                hostname=host,
                port=port,
                start_tls=bool(starttls and not use_tls),
                use_tls=bool(use_tls),
                username=username if use_credentials else None,
                password=password if use_credentials else None,
                timeout=20.0,
            )
        logger.info("email: send_ok to=%s", to)
        return True
    except Exception as ex:
        logger.warning("email: send_failed host=%s port=%s err=%s", host, port, ex)
        return False


async def send_gift_notification_email(to: str, amount_usd: str, is_trial: bool) -> bool:
    """Send a gift notification email when admin gifts credits to a user.
    
    Args:
        to: Recipient email address
        amount_usd: Formatted amount (e.g., "$5.00")
        is_trial: True if trial credits, False if regular credits
    
    Returns True on best-effort success, False on failure. Never raises.
    """
    # Hard-stop in automated tests: do not send real email
    try:
        from restailor.test_flags import is_automated_test_run as _is_auto
        if _is_auto():
            logger.info("email: gift notification skipped (automated test run)")
            return True
    except Exception:
        pass
    
    # Global kill-switch
    if _truthy(os.getenv("EMAIL_DISABLE_OUTBOUND")) or _truthy(os.getenv("DISABLE_OUTBOUND_EMAIL")):
        logger.info("email: outbound disabled via env")
        return True

    host, port, mail_from, mail_from_name, app_name, starttls, use_tls, username, password, use_credentials = _get_smtp_config()
    
    # Use same email format as verification emails
    gift_from = mail_from
    gift_from_name = mail_from_name or app_name
    
    if not (host and port):
        logger.warning("email: incomplete SMTP config (host=%r, port=%r)", bool(host), port)
        return False

    # Compose message
    credit_type = "trial" if is_trial else "gift"
    subject = f"You've received {amount_usd} in {credit_type} credits from {app_name}!"
    
    text_body = f"""Hello!

Good news - you've received {amount_usd} in {credit_type} credits from {app_name}!

{"These trial credits can be used to explore our services. " if is_trial else ""}You can start using your credits immediately by logging into your account.

Thank you for being part of our community!

Best regards,
The {app_name} Team
"""

    html_body = f"""
    <html>
      <body style="font-family: Arial, sans-serif; color: #333; max-width: 600px; margin: 0 auto;">
        <div style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); padding: 30px; text-align: center; border-radius: 8px 8px 0 0;">
          <h1 style="color: white; margin: 0; font-size: 28px;">🎉 You've Got Credits!</h1>
        </div>
        <div style="background: #ffffff; padding: 30px; border: 1px solid #e0e0e0; border-radius: 0 0 8px 8px;">
          <p style="font-size: 16px; line-height: 1.6;">Hello!</p>
          <p style="font-size: 16px; line-height: 1.6;">
            Good news - you've received <strong style="color: #667eea; font-size: 20px;">{amount_usd}</strong> 
            in <strong>{credit_type} credits</strong> from <strong>{app_name}</strong>!
          </p>
          {"<p style='font-size: 16px; line-height: 1.6; background: #f0f4ff; padding: 15px; border-left: 4px solid #667eea; border-radius: 4px;'>These trial credits can be used to explore our services and see what we have to offer.</p>" if is_trial else ""}
          <p style="font-size: 16px; line-height: 1.6;">
            You can start using your credits immediately by logging into your account.
          </p>
          <div style="text-align: center; margin: 30px 0;">
            <a href="https://restailor.com" 
               style="background: #667eea; color: white; padding: 12px 30px; text-decoration: none; border-radius: 6px; display: inline-block; font-weight: bold;">
              Log In to Your Account
            </a>
          </div>
          <p style="font-size: 16px; line-height: 1.6;">
            Thank you for being part of our community!
          </p>
          <p style="font-size: 16px; line-height: 1.6; margin-top: 30px;">
            Best regards,<br/>
            <strong>The {app_name} Team</strong>
          </p>
        </div>
        <div style="text-align: center; padding: 20px; color: #999; font-size: 12px;">
          <p>This is an automated message from {app_name}. Please do not reply to this email.</p>
        </div>
      </body>
    </html>
    """

    msg = EmailMessage()
    try:
        msg["From"] = formataddr((gift_from_name, gift_from))
    except Exception:
        msg["From"] = gift_from
    msg["To"] = to
    msg["Subject"] = subject
    msg.set_content(text_body)
    msg.add_alternative(html_body, subtype="html")

    try:
        import aiosmtplib  # type: ignore

        logger.info(
            "email: sending gift notification via SMTP host=%s port=%s from=%s to=%s amount=%s is_trial=%s",
            host,
            port,
            gift_from,
            to,
            amount_usd,
            is_trial,
        )
        if _truthy(os.getenv("MAIL_USE_CREDENTIALS")) and not use_credentials:
            logger.warning("email: MAIL_USE_CREDENTIALS true but no username/password resolved (check env/keyring)")
        
        async with outbound_timed("email", host or "smtp", port=port):  # PERF
            await aiosmtplib.send(
                msg,
                hostname=host,
                port=port,
                start_tls=bool(starttls and not use_tls),
                use_tls=bool(use_tls),
                username=username if use_credentials else None,
                password=password if use_credentials else None,
                timeout=20.0,
            )
        logger.info("email: gift notification send_ok to=%s", to)
        return True
    except Exception as ex:
        logger.warning("email: gift notification send_failed host=%s port=%s err=%s", host, port, ex)
        return False
