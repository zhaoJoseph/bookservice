import boto3
import boto3.session
from botocore.exceptions import ClientError
from .config import aws_settings
from ..config import settings as app_settings
from .exceptions import SESServiceError, SESIdentityNotFoundError, SESQuotaExceededError
from .constants import SES_DEFAULT_TIMEOUT, SES_MAX_RETRIES
from .schemas import EmailRequest
from .utils import format_email_body, render_verification_email

class SESClient:
    def __init__(self):
        self.client = boto3.client(
            "ses",
            region_name=aws_settings.AWS_REGION,
            aws_access_key_id=aws_settings.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=aws_settings.AWS_SECRET_ACCESS_KEY,
            config=boto3.session.Config(retries={"max_attempts": SES_MAX_RETRIES})
        )
        # send_verification_email uses the SESv2 API (FromEmailAddress/Content),
        # which classic "ses" clients don't support.
        self.v2_client = boto3.client(
            "sesv2",
            region_name=aws_settings.AWS_REGION,
            aws_access_key_id=aws_settings.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=aws_settings.AWS_SECRET_ACCESS_KEY,
            config=boto3.session.Config(retries={"max_attempts": SES_MAX_RETRIES})
        )
        self.source_email = aws_settings.SES_SOURCE_EMAIL

    def send_email(self, request: EmailRequest) -> str:
        try:
            destination = {"ToAddresses": [request.to_email]}
            if request.cc_emails:
                destination["CcAddresses"] = request.cc_emails

            response = self.client.send_email(
                Source=self.source_email,
                Destination=destination,
                Message={
                    "Subject": {"Data": request.subject},
                    "Body": format_email_body(request.body),
                },
            )
            return response["MessageId"]

        except ClientError as e:
            error_code = e.response["Error"]["Code"]
            if error_code == "MessageRejected":
                raise SESIdentityNotFoundError("Recipient or Sender invalid") from e
            elif error_code == "Throttling":
                raise SESQuotaExceededError("SES sending limit exceeded") from e
            raise SESServiceError(f"Failed to send email: {str(e)}") from e

    def send_verification_email(self, email: str, token: str):
        verification_link = f"{app_settings.app_base_url}/verify-email?token={token}"
        rendered = render_verification_email(verification_link)

        try:
            response = self.v2_client.send_email(
                FromEmailAddress=self.source_email,
                Destination={"ToAddresses": [email]},
                Content={
                    "Simple": {
                        "Subject": {"Data": rendered["subject"]},
                        "Body": {
                            "Html": {"Data": rendered["html"]},
                            "Text": {"Data": rendered["text"]},
                        },
                    }
                }
            )
            return response["MessageId"]
        except ClientError as e:
            error_code = e.response["Error"]["Code"]
            if error_code == "MessageRejected":
                raise SESIdentityNotFoundError("Recipient or Sender invalid") from e
            elif error_code == "Throttling":
                raise SESQuotaExceededError("SES sending limit exceeded") from e
            raise SESServiceError(f"Failed to send email: {str(e)}") from e

class S3Client:
    def __init__(self):
        self.client = boto3.client(
            "s3",
            region_name=aws_settings.AWS_REGION,
            aws_access_key_id=aws_settings.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=aws_settings.AWS_SECRET_ACCESS_KEY,
            config=boto3.session.Config(retries={"max_attempts": SES_MAX_RETRIES})
        )

    def get_file(self, file_name: str) -> bytes:
        response = self.client.get_object(Bucket=aws_settings.S3_BUCKET, Key=file_name)
        return response["Body"].read()

# Singleton instances
ses_client = SESClient()   

s3_client = S3Client()

