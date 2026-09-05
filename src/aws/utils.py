import json
from pathlib import Path

def format_email_body(text: str) -> dict:
    """Formats body for SES API (Text + HTML placeholder)"""
    return {
        "Text": {"Data": text},
    }

_VERIFICATION_TEMPLATE_PATH = Path(__file__).resolve().parents[2] / "templates" / "email" / "verification.json"

def render_verification_email(verification_link: str) -> dict:
    """Renders the local verification email template into SES-ready Simple content."""
    template = json.loads(_VERIFICATION_TEMPLATE_PATH.read_text())
    content = template["TemplateContent"]

    def _fill(text: str) -> str:
        return text.replace("{{verification_link}}", verification_link)

    return {
        "subject": _fill(content["Subject"]),
        "text": _fill(content["Text"]),
        "html": _fill(content["Html"]),
    }