import hashlib
import secrets
from .constants import VERIFICATION_TOKEN_LENGTH

genres_dict = {
    1: "Action",
    2: "Adventure",
    3: "Comedy",
    4: "Drama",
    5: "Fantasy",
    6: "Horror",
    7: "Romance",
    8: "Sci-Fi",
    9: "Thriller",
    10: "Western"
}

def generate_verification_token() -> str:
    """Generates a cryptographically secure URL-safe token."""
    return secrets.token_urlsafe(VERIFICATION_TOKEN_LENGTH)

def genres_to_string(genres: list[int]) -> str:
    """Converts a list of genres to a string."""
    return ",".join([genres_dict[genre] for genre in genres])

def fingerprint_verification_token(token: str) -> str:
    """
    Short, stable fingerprint of a verification JWT. Verification tokens are
    stateless JWTs valid until they expire, so nothing normally stops an
    older, still-unexpired token from working after a newer one has been
    issued. Storing this fingerprint on the user lets /verify reject anything
    but the most recently issued token.
    """
    return hashlib.sha256(token.encode()).hexdigest()[:VERIFICATION_TOKEN_LENGTH]