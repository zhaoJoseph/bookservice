def format_email_body(text: str) -> dict:
    """Formats body for SES API (Text + HTML placeholder)"""
    return {
        "Text": {"Data": text},
    }