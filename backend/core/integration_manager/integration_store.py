from typing import Optional, Dict, Any, List
from datetime import datetime
from backend.database_supabase import get_supabase_client
from backend.core.integration_manager.crypto_vault import vault
import logging

logger = logging.getLogger(__name__)

class IntegrationStore:
    """
    Manages secure storage and retrieval of OAuth integration tokens
    from the Supabase database.

    PERSISTENCE FIX: All connected integrations are stored in Supabase so they
    survive server restarts. In-memory store is used as a write-through cache
    and as a fallback when Supabase is unavailable.
    """
    def __init__(self):
        self.supabase = get_supabase_client()
        self.table_name = "user_integrations"
        # Write-through cache: mirrors Supabase for fast reads
        self._memory_store: Dict[str, Dict[str, Dict[str, Any]]] = {}

    # =========================================================================
    # Available Integrations Catalog
    # =========================================================================

    AVAILABLE_INTEGRATIONS = {
        "gmail": {
            "name": "Gmail",
            "icon": "📧",
            "description": "Send and read emails via Secure SMTP or OAuth",
            "provider": "google",
            "scopes": ["gmail.send", "gmail.readonly"],
            "category": "communication",
        },
        "jitsi": {
            "name": "Jitsi Meet",
            "icon": "📹",
            "description": "Free, instant video meetings (No account needed)",
            "provider": "jitsi",
            "scopes": [],
            "category": "communication",
            "is_working": True,
        },
        "zoom": {
            "name": "Zoom",
            "icon": "📹",
            "description": "Professional video conferencing",
            "provider": "zoom",
            "scopes": ["meeting:write", "meeting:read"],
            "category": "communication",
        },
        "google_calendar": {
            "name": "Google Calendar",
            "icon": "📅",
            "description": "Schedule meetings, manage events",
            "provider": "google",
            "scopes": ["calendar.events", "calendar.readonly"],
            "category": "productivity",
        },
        "google_drive": {
            "name": "Google Drive",
            "icon": "📂",
            "description": "Access and share files",
            "provider": "google",
            "scopes": ["drive.readonly", "drive.file"],
            "category": "storage",
        },
    }

    # =========================================================================
    # Private Helpers
    # =========================================================================

    def _store_memory_integration(
        self,
        user_id: str,
        provider: str,
        encrypted_tokens: Optional[str],
        scopes: List[str],
        metadata: Optional[Dict[str, Any]] = None,
        status: str = "connected",
    ) -> None:
        """Cache an integration record in memory (write-through cache)."""
        now = datetime.utcnow().isoformat()
        if user_id not in self._memory_store:
            self._memory_store[user_id] = {}
        self._memory_store[user_id][provider] = {
            "id": self._memory_store[user_id].get(provider, {}).get("id") or f"mem-{user_id}-{provider}",
            "user_id": user_id,
            "provider": provider,
            "encrypted_tokens": encrypted_tokens,
            "scopes": scopes,
            "metadata": metadata or {},
            "status": status,
            "updated_at": now,
        }

    def _encrypt_token_data(self, token_data: Dict[str, Any]) -> str:
        """Encrypts the OAuth payload (JSON) using AES-256-GCM."""
        import json
        json_str = json.dumps(token_data)
        return vault.encrypt(json_str)

    def _decrypt_token_data(self, encrypted_str: str) -> Dict[str, Any]:
        """Decrypts the OAuth payload back to JSON."""
        import json
        json_str = vault.decrypt(encrypted_str)
        return json.loads(json_str)

    def _build_display_record(self, record: Dict[str, Any]) -> Dict[str, Any]:
        """Convert a DB/memory record into a UI-friendly integration dict."""
        provider = record.get("provider", "unknown")
        catalog = self.AVAILABLE_INTEGRATIONS.get(provider, {})
        return {
            "id": record.get("id"),
            "service": provider,
            "name": catalog.get("name", provider),
            "icon": catalog.get("icon", "🔗"),
            "status": record.get("status"),
            "connected_at": record.get("updated_at"),
            "last_used_at": record.get("updated_at"),
            "provider": catalog.get("provider", provider),
            "scopes": record.get("scopes", []),
            "method": record.get("method"),
            "note": record.get("note"),
        }

    # =========================================================================
    # Core CRUD Operations
    # =========================================================================

    def store_integration(
        self,
        user_id: str,
        provider: str,
        token_data: Dict[str, Any],
        scopes: list,
        metadata: Optional[Dict] = None,
    ) -> bool:
        """
        Securely stores an integration token.
        Writes to Supabase first, then updates the memory cache.
        Falls back to memory-only if Supabase is unavailable.
        """
        encrypted_tokens = self._encrypt_token_data(token_data)

        # Always update memory cache
        self._store_memory_integration(user_id, provider, encrypted_tokens, scopes, metadata, status="connected")

        if not self.supabase:
            logger.info(f"[IntegrationStore] Stored {provider} for {user_id} (memory-only)")
            return True

        data = {
            "user_id": user_id,
            "provider": provider,
            "encrypted_tokens": encrypted_tokens,
            "scopes": scopes,
            "metadata": metadata or {},
            "status": "connected",
            "updated_at": datetime.utcnow().isoformat(),
        }

        try:
            self.supabase.table(self.table_name).upsert(data).execute()
            logger.info(f"[IntegrationStore] Stored {provider} for {user_id} in Supabase")
            return True
        except Exception as e:
            logger.error(f"Error storing integration {provider} for user {user_id}: {e}")
            # Memory cache was already updated above
            return True

    def get_integration(self, user_id: str, provider: str) -> Optional[Dict[str, Any]]:
        """
        Retrieve a single integration.
        Checks built-in services first, then Supabase, then memory cache.
        """
        # --- Built-in: Gmail via SMTP ---
        if provider == "gmail":
            import os
            smtp_email = os.getenv("SMTP_EMAIL") or os.getenv("GMAIL_USER")
            smtp_pass = os.getenv("SMTP_PASSWORD") or os.getenv("GMAIL_APP_PASSWORD")
            if smtp_email and smtp_pass:
                return {
                    "id": "smtp-gmail",
                    "user_id": user_id,
                    "provider": "gmail",
                    "status": "connected",
                    "method": "smtp",
                    "tokens": {"access_token": smtp_pass},
                    "scopes": ["gmail.send"],
                }

        # --- Built-in: Jitsi (always connected, zero-auth) ---
        if provider == "jitsi":
            return {
                "id": "builtin-jitsi",
                "user_id": user_id,
                "provider": "jitsi",
                "status": "connected",
                "method": "builtin",
                "tokens": {},
                "scopes": [],
            }

        # --- Check Supabase persistent store ---
        if self.supabase:
            try:
                response = self.supabase.table(self.table_name).select("*").match({
                    "user_id": user_id,
                    "provider": provider,
                }).execute()

                if response.data and len(response.data) > 0:
                    record = response.data[0]
                    if record.get("status") != "connected":
                        return None
                    # Decrypt tokens
                    encrypted_str = record.get("encrypted_tokens")
                    if encrypted_str:
                        record["tokens"] = self._decrypt_token_data(encrypted_str)
                        del record["encrypted_tokens"]
                    # Update memory cache
                    self._store_memory_integration(
                        user_id, provider,
                        record.get("encrypted_tokens") or self._encrypt_token_data(record.get("tokens", {})),
                        record.get("scopes", []),
                        record.get("metadata"),
                        status="connected",
                    )
                    return record
            except Exception as e:
                logger.error(f"Error fetching integration {provider} for user {user_id}: {e}")

        # --- Fallback: memory cache ---
        record = self._memory_store.get(user_id, {}).get(provider)
        if record and record.get("status") == "connected":
            result = dict(record)
            encrypted_str = result.get("encrypted_tokens")
            if encrypted_str:
                result["tokens"] = self._decrypt_token_data(encrypted_str)
                result.pop("encrypted_tokens", None)
            return result

        return None

    def revoke_integration(self, user_id: str, provider: str) -> bool:
        """Revoke an integration — marks it as revoked in Supabase and memory."""
        now = datetime.utcnow().isoformat()

        # Update memory
        existing = self._memory_store.get(user_id, {}).get(provider, {})
        self._memory_store.setdefault(user_id, {})[provider] = {
            **existing,
            "id": existing.get("id") or f"mem-{user_id}-{provider}",
            "user_id": user_id,
            "provider": provider,
            "encrypted_tokens": None,
            "status": "revoked",
            "updated_at": now,
        }

        if not self.supabase:
            return True

        data = {
            "user_id": user_id,
            "provider": provider,
            "encrypted_tokens": None,
            "status": "revoked",
            "updated_at": now,
        }

        try:
            self.supabase.table(self.table_name).upsert(data).execute()
            return True
        except Exception as e:
            logger.error(f"Error revoking integration {provider} for user {user_id}: {e}")
            return True

    # =========================================================================
    # Listing & Status
    # =========================================================================

    def get_user_integrations(self, user_id: str) -> List[Dict]:
        """
        List all connected integrations for a user.
        Checks: built-in services → Supabase → memory cache.
        """
        try:
            import os
            connected = []
            seen_services = set()

            # --- Built-in: Gmail SMTP ---
            smtp_email = os.getenv("SMTP_EMAIL") or os.getenv("GMAIL_USER")
            smtp_pass = os.getenv("SMTP_PASSWORD") or os.getenv("GMAIL_APP_PASSWORD")
            if smtp_email and smtp_pass:
                connected.append({
                    "id": "smtp-gmail",
                    "service": "gmail",
                    "name": "Gmail",
                    "icon": "📧",
                    "status": "connected",
                    "method": "smtp",
                    "connected_at": datetime.utcnow().isoformat(),
                    "last_used_at": datetime.utcnow().isoformat(),
                    "provider": "google",
                    "scopes": ["gmail.send"],
                    "note": "Connected via Secure SMTP (App Password)",
                })
                seen_services.add("gmail")

            # --- Built-in: Jitsi ---
            connected.append({
                "id": "builtin-jitsi",
                "service": "jitsi",
                "name": "Jitsi Meet",
                "icon": "📹",
                "status": "connected",
                "method": "builtin",
                "connected_at": datetime.utcnow().isoformat(),
                "last_used_at": datetime.utcnow().isoformat(),
                "provider": "jitsi",
                "scopes": [],
                "note": "Ready to use (Zero-Auth)",
            })
            seen_services.add("jitsi")

            # --- Supabase persistent store ---
            if self.supabase:
                try:
                    response = self.supabase.table(self.table_name).select("*").eq("user_id", user_id).execute()
                    if response.data:
                        for record in response.data:
                            if record.get("status") != "connected":
                                continue
                            service_name = record.get("provider")
                            if service_name in seen_services:
                                continue
                            display = self._build_display_record(record)
                            connected.append(display)
                            seen_services.add(service_name)

                            # Warm the memory cache
                            self._store_memory_integration(
                                user_id, service_name,
                                record.get("encrypted_tokens"),
                                record.get("scopes", []),
                                record.get("metadata"),
                                status="connected",
                            )
                except Exception as e:
                    logger.error(f"Error fetching integrations from Supabase for {user_id}: {e}")

            # --- Memory cache (catches OAuth tokens stored in current session) ---
            user_records = self._memory_store.get(user_id, {})
            for provider, record in user_records.items():
                if record.get("status") != "connected":
                    continue
                if provider in seen_services:
                    continue
                display = self._build_display_record(record)
                connected.append(display)
                seen_services.add(provider)

            return connected

        except Exception as e:
            logger.error(f"Error fetching integrations for user {user_id}: {e}")
            return []

    def get_available_integrations(self, user_id: str) -> List[Dict]:
        """List integrations NOT yet connected for a user."""
        connected_services = set(item["service"] for item in self.get_user_integrations(user_id))
        available = []
        for service_name, info in self.AVAILABLE_INTEGRATIONS.items():
            if service_name not in connected_services:
                available.append({
                    "service": service_name,
                    "name": info["name"],
                    "icon": info["icon"],
                    "description": info["description"],
                    "provider": info["provider"],
                    "category": info["category"],
                })
        return available

    def is_connected(self, user_id: str, service: str) -> bool:
        """
        Check if a service is connected.
        Includes checks for SMTP, built-in, Supabase, and memory.
        """
        if service == "gmail":
            import os
            smtp_email = os.getenv("SMTP_EMAIL") or os.getenv("GMAIL_USER")
            smtp_pass = os.getenv("SMTP_PASSWORD") or os.getenv("GMAIL_APP_PASSWORD")
            if smtp_email and smtp_pass:
                return True

        if service == "jitsi":
            return True

        record = self.get_integration(user_id, service)
        return record is not None and record.get("status") == "connected"

    def check_health(self, user_id: str, service: str) -> Dict[str, Any]:
        """Check health of a specific integration."""
        is_conn = self.is_connected(user_id, service)
        catalog = self.AVAILABLE_INTEGRATIONS.get(service, {})
        return {
            "service": service,
            "name": catalog.get("name", service),
            "connected": is_conn,
            "healthy": is_conn,
            "provider": catalog.get("provider", service),
        }

    # =========================================================================
    # Aliases for backwards compatibility
    # =========================================================================

    def connect_integration(
        self, user_id: str, service: str,
        access_token: str = None, refresh_token: str = None,
        scopes: list = None, expires_at: str = None
    ) -> Dict[str, Any]:
        """Alias used by OAuth callback routes."""
        token_data = {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "expires_at": expires_at
        }
        success = self.store_integration(
            user_id=user_id,
            provider=service,
            token_data=token_data,
            scopes=scopes or []
        )
        return {
            "service": service,
            "status": "connected" if success else "failed",
            "provider": self.AVAILABLE_INTEGRATIONS.get(service, {}).get("provider", service)
        }

    def revoke_by_service(self, user_id: str, service: str) -> bool:
        """Alias for revoke_integration to map to older API requirements."""
        return self.revoke_integration(user_id, service)


integration_store = IntegrationStore()
