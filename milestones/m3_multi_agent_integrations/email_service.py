import os
from pathlib import Path
import smtplib
import ssl
from email.utils import parseaddr
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import config


class EmailService:
    def _get_config(self):
        """Dynamically reload and return latest SMTP settings from .env and config."""
        try:
            from dotenv import load_dotenv
            load_dotenv(config.ENV_FILE, override=True)
        except Exception:
            pass

        smtp_server = (os.environ.get("SMTP_SERVER") or getattr(config, "SMTP_SERVER", "smtp.gmail.com") or "smtp.gmail.com").strip()
        try:
            smtp_port = int(os.environ.get("SMTP_PORT") or getattr(config, "SMTP_PORT", 587) or 587)
        except (ValueError, TypeError):
            smtp_port = 587
        smtp_email = (os.environ.get("SMTP_EMAIL") or getattr(config, "SMTP_EMAIL", "") or "").strip()
        smtp_password = "".join((os.environ.get("SMTP_PASSWORD") or getattr(config, "SMTP_PASSWORD", "") or "").split())
        return smtp_server, smtp_port, smtp_email, smtp_password

    def is_configured(self) -> bool:
        _, _, smtp_email, smtp_password = self._get_config()
        if not smtp_email or not smtp_password:
            return False
        if "example.com" in smtp_email or "your_email" in smtp_email or "your-email" in smtp_email:
            return False
        return True

    def test_connection(self):
        smtp_server, smtp_port, smtp_email, smtp_password = self._get_config()

        if not smtp_email or not smtp_password:
            return {
                "success": False,
                "message": "Email is missing SMTP_EMAIL or SMTP_PASSWORD in settings or .env."
            }
        try:
            if smtp_port == 465:
                context = ssl.create_default_context()
                with smtplib.SMTP_SSL(
                    smtp_server, smtp_port, context=context, timeout=12
                ) as server:
                    server.login(smtp_email, smtp_password)
            else:
                context = ssl.create_default_context()
                with smtplib.SMTP(smtp_server, smtp_port, timeout=12) as server:
                    server.ehlo()
                    server.starttls(context=context)
                    server.ehlo()
                    server.login(smtp_email, smtp_password)
            return {
                "success": True,
                "message": f"SMTP Authentication successful for {smtp_email}!"
            }
        except smtplib.SMTPAuthenticationError:
            return {
                "success": False,
                "message": "SMTP Authentication Failed: Check email and 16-character Gmail App Password."
            }
        except Exception as exc:
            return {"success": False, "message": f"SMTP Connection error: {exc}"}

    def send_email(self, recipient, subject, body):
        smtp_server, smtp_port, smtp_email, smtp_password = self._get_config()

        if not smtp_email or not smtp_password:
            return {
                "success": False,
                "message": "Email is not configured. Set SMTP_EMAIL and SMTP_PASSWORD in settings or .env."
            }
        if not recipient or parseaddr(recipient)[1] != recipient.strip():
            return {"success": False, "message": "A valid customer email address is required."}

        message = MIMEMultipart()
        message["From"] = smtp_email
        message["To"] = recipient.strip()
        message["Subject"] = subject
        message.attach(MIMEText(body, "plain"))

        try:
            if smtp_port == 465:
                context = ssl.create_default_context()
                with smtplib.SMTP_SSL(
                    smtp_server, smtp_port, context=context, timeout=20
                ) as server:
                    server.login(smtp_email, smtp_password)
                    server.send_message(message)
            else:
                context = ssl.create_default_context()
                with smtplib.SMTP(smtp_server, smtp_port, timeout=20) as server:
                    server.ehlo()
                    server.starttls(context=context)
                    server.ehlo()
                    server.login(smtp_email, smtp_password)
                    server.send_message(message)
            return {"success": True, "message": f"Email notification successfully sent to {recipient.strip()}!"}
        except (OSError, smtplib.SMTPException, Exception) as exc:
            return {"success": False, "message": f"Email delivery failed: {exc}"}


