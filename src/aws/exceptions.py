class SESServiceError(Exception):
    """Base exception for SES failures"""
    pass

class SESIdentityNotFoundError(SESServiceError):
    """Raised when the source email is not verified"""
    pass

class SESQuotaExceededError(SESServiceError):
    """Raised when SES sending limits are hit"""

class S3ServiceError(Exception):
    """Base exception for S3 failures"""
    pass

class S3FileNotFoundError(S3ServiceError):
    """Raised when the file is not found in S3"""
    pass