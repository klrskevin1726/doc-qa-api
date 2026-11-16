import os

from dotenv import load_dotenv

load_dotenv()


class ConfigurationError(RuntimeError):
    pass


def get_secret_key() -> str:
    secret_key = os.getenv("SECRET_KEY")
    if (
        not secret_key
        or not secret_key.strip()
        or len(secret_key.encode("utf-8")) < 32
    ):
        raise ConfigurationError(
            "SECRET_KEY must be configured with at least 32 bytes."
        )
    return secret_key


def get_openai_api_key() -> str:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise ConfigurationError("OPENAI_API_KEY is not configured.")
    return api_key


def get_int_setting(name: str, default: int, minimum: int, maximum: int) -> int:
    raw_value = os.getenv(name)
    if raw_value is None:
        return default
    try:
        value = int(raw_value)
    except ValueError as exc:
        raise ConfigurationError(f"{name} must be an integer.") from exc
    if not minimum <= value <= maximum:
        raise ConfigurationError(
            f"{name} must be between {minimum} and {maximum}."
        )
    return value
