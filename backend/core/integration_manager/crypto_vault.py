import os
import base64
import hashlib
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.exceptions import InvalidTag
from typing import Optional

from ...config import get_settings

class CryptoVault:
    """
    AES-256-GCM encryption utility for secure storage of integration tokens.
    Implements Layer 6 Security Requirements from README.
    """
    
    def __init__(self, master_key: Optional[bytes] = None):
        # Key source order:
        # 1) ENCRYPTION_MASTER_KEY (base64-encoded 32 bytes)
        # 2) explicit master_key argument (32 bytes)
        # 3) development-only derived key for local/test environments
        env_key = os.environ.get("ENCRYPTION_MASTER_KEY")
        app_env = (os.environ.get("APP_ENV") or os.environ.get("ENV") or "development").strip().lower()
        is_dev_like = app_env in {"development", "dev", "testing", "test", "local"}

        if env_key:
            decoded = base64.b64decode(env_key)
            if len(decoded) != 32:
                raise ValueError("ENCRYPTION_MASTER_KEY must decode to exactly 32 bytes")
            self.key = decoded
        elif master_key:
            if len(master_key) != 32:
                raise ValueError("master_key must be exactly 32 bytes")
            self.key = master_key
        else:
            if not is_dev_like:
                raise RuntimeError("ENCRYPTION_MASTER_KEY is required outside development/testing environments")
            # Item 22: no random fallback \u2014 even dev needs explicit secret to prevent data loss on restart
            seed_source = (
                os.environ.get("ENCRYPTION_SECRET")
                or os.environ.get("SECRET_KEY")
                or get_settings().secret_key
            )
            if not seed_source:
                raise RuntimeError(
                    "ENCRYPTION_SECRET or SECRET_KEY is required even in development "
                    "(prevents token data loss on server restart)"
                )
            self.key = hashlib.sha256(seed_source.encode("utf-8")).digest()
            
    def encrypt(self, plaintext: str) -> str:
        """Encrypt string using AES-256-GCM."""
        aesgcm = AESGCM(self.key)
        nonce = os.urandom(12) # 96-bit nonce is recommended for GCM
        ciphertext = aesgcm.encrypt(nonce, plaintext.encode('utf-8'), None)
        # Store as base64 combined nonce + ciphertext
        return base64.b64encode(nonce + ciphertext).decode('utf-8')

    def decrypt(self, encrypted_b64: str) -> str:
        """Decrypt string using AES-256-GCM."""
        try:
            encrypted_data = base64.b64decode(encrypted_b64)
            nonce = encrypted_data[:12]
            ciphertext = encrypted_data[12:]
            aesgcm = AESGCM(self.key)
            plaintext = aesgcm.decrypt(nonce, ciphertext, None)
            return plaintext.decode('utf-8')
        except (ValueError, InvalidTag, TypeError) as e:
            raise ValueError(f"Decryption failed: {str(e)}")

# Singleton instance for the application
vault = CryptoVault()
