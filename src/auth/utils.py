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