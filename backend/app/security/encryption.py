"""
Attora — Field-Level Encryption

Fernet symmetric encryption for sensitive organization fields
(ManyChat API keys, Meta CAPI tokens, etc.).

Usage:
    from app.security.encryption import encrypt_value, decrypt_value

    encrypted = encrypt_value("sk-secret-key-123")
    decrypted = decrypt_value(encrypted)  # "sk-secret-key-123"
"""

from cryptography.fernet import Fernet, InvalidToken

from app.config import settings

# Lazy-initialized Fernet instance
_fernet: Fernet | None = None


def _get_fernet() -> Fernet:
    """Get or create the Fernet cipher instance."""
    global _fernet
    if _fernet is None:
        key = settings.encryption_key
        # If the key doesn't look like a valid Fernet key, derive one
        try:
            _fernet = Fernet(key.encode() if isinstance(key, str) else key)
        except (ValueError, Exception):
            # If the provided key is not a valid Fernet key,
            # this is a configuration error — raise immediately
            raise ValueError(
                "ENCRYPTION_KEY is not a valid Fernet key. "
                "Generate one with: python -c \"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\""
            )
    return _fernet


def encrypt_value(plaintext: str) -> str:
    """
    Encrypt a plaintext string using Fernet symmetric encryption.

    Args:
        plaintext: The sensitive value to encrypt.

    Returns:
        Base64-encoded encrypted string safe for database storage.
    """
    if not plaintext:
        return plaintext
    fernet = _get_fernet()
    return fernet.encrypt(plaintext.encode("utf-8")).decode("utf-8")


def decrypt_value(ciphertext: str) -> str:
    """
    Decrypt a Fernet-encrypted string back to plaintext.

    Args:
        ciphertext: The encrypted value from the database.

    Returns:
        The original plaintext string.

    Raises:
        InvalidToken: If the ciphertext is corrupted or the key doesn't match.
    """
    if not ciphertext:
        return ciphertext
    fernet = _get_fernet()
    try:
        return fernet.decrypt(ciphertext.encode("utf-8")).decode("utf-8")
    except InvalidToken:
        raise ValueError("Failed to decrypt value — encryption key may have changed.")


def mask_value(value: str | None, visible_chars: int = 4) -> str | None:
    """
    Mask a sensitive value for display purposes.

    Args:
        value: The plaintext value to mask.
        visible_chars: Number of characters to show at the end.

    Returns:
        Masked string like "****abcd" or None if value is None.
    """
    if not value:
        return value
    if len(value) <= visible_chars:
        return "*" * len(value)
    return "*" * (len(value) - visible_chars) + value[-visible_chars:]
