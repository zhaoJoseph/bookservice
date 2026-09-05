EMAIL_EXISTS_MESSAGE = "Email already exists"
INCORECT_LOGIN_MESSAGE = "Incorrect email or password"
USER_SUSPENDED_MESSAGE = "User is suspended"
USER_NOT_FOUND_MESSAGE = "User not found"
INVALID_TOKEN_MESSAGE = "Invalid token"
VERIFICATION_TOO_SOON_MESSAGE = "Please wait before requesting another verification email"

VERIFICATION_TOKEN_LENGTH = 32
VERIFICATION_TOKEN_EXPIRY_HOURS = 24

# Minimum time a user must wait between /request-verify-token calls.
VERIFY_RESEND_COOLDOWN_SECONDS = 60