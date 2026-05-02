"""
Evidence vault for append-only mission artifacts.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Union
import base64
import hashlib
import json
import os
import uuid

try:
    from ..database_supabase import get_supabase_client
except ImportError:  # pragma: no cover
    from backend.database_supabase import get_supabase_client


@dataclass
class EvidenceArtifact:
    artifact_id: str
    mission_id: str
    tenant_id: str
    user_id: str
    step_id: Optional[str]
    name: str
    content_type: str
    file_path: str
    content_hash: str
    previous_hash: Optional[str] = None
    classification: str = "internal"
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class EvidenceVault:
    def __init__(self, root_dir: Optional[str] = None):
        self.root_dir = Path(root_dir or os.getenv("EVIDENCE_VAULT_DIR", "data/evidence"))
        self.root_dir.mkdir(parents=True, exist_ok=True)
        self._client = get_supabase_client()
        self._artifacts: Dict[str, EvidenceArtifact] = {}
        self._mission_artifacts: Dict[str, List[str]] = {}
        self.retention_days = max(1, int(os.getenv("EVIDENCE_RETENTION_DAYS", "365")))

    def _artifact_dir(self, tenant_id: str, mission_id: str) -> Path:
        path = self.root_dir / tenant_id / mission_id
        path.mkdir(parents=True, exist_ok=True)
        return path

    def store_artifact(
        self,
        *,
        mission_id: str,
        tenant_id: str,
        user_id: str,
        step_id: Optional[str],
        name: str,
        content: Union[str, bytes],
        content_type: str = "text/plain",
        classification: str = "internal",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> EvidenceArtifact:
        raw_bytes = content.encode("utf-8") if isinstance(content, str) else content
        content_hash = hashlib.sha256(raw_bytes).hexdigest()
        artifact_id = str(uuid.uuid4())
        artifact_dir = self._artifact_dir(tenant_id, mission_id)
        file_extension = Path(name).suffix or ".bin"
        file_path = artifact_dir / f"{artifact_id}{file_extension}"
        file_path.write_bytes(raw_bytes)

        previous_hash = None
        prior_ids = self._mission_artifacts.get(mission_id, [])
        if prior_ids:
            previous_hash = self._artifacts[prior_ids[-1]].content_hash

        artifact = EvidenceArtifact(
            artifact_id=artifact_id,
            mission_id=mission_id,
            tenant_id=tenant_id,
            user_id=user_id,
            step_id=step_id,
            name=name,
            content_type=content_type,
            file_path=str(file_path),
            content_hash=content_hash,
            previous_hash=previous_hash,
            classification=classification,
            metadata=metadata or {},
        )
        artifact.metadata.setdefault("retention_days", self.retention_days)
        artifact.metadata.setdefault(
            "expires_at",
            (datetime.fromisoformat(artifact.created_at) + timedelta(days=self.retention_days)).isoformat(),
        )
        artifact.metadata.setdefault("chain_index", len(prior_ids) + 1)
        self._artifacts[artifact_id] = artifact
        self._mission_artifacts.setdefault(mission_id, []).append(artifact_id)

        if self._client:
            try:
                self._client.table("evidence_artifacts").insert(
                    {
                        "artifact_id": artifact_id,
                        "mission_id": mission_id,
                        "step_id": step_id,
                        "tenant_id": tenant_id,
                        "user_id": user_id,
                        "name": name,
                        "content_type": content_type,
                        "file_path": str(file_path),
                        "content_hash": content_hash,
                        "previous_hash": previous_hash,
                        "classification": classification,
                        "metadata": metadata or {},
                    }
                ).execute()
            except Exception:
                pass

        manifest_path = artifact_dir / "manifest.json"
        manifest_path.write_text(json.dumps(self.export_bundle(mission_id), indent=2), encoding="utf-8")
        return artifact

    def _is_expired(self, artifact: EvidenceArtifact) -> bool:
        expires_at = artifact.metadata.get("expires_at")
        if not expires_at:
            return False
        try:
            return datetime.utcnow() > datetime.fromisoformat(str(expires_at))
        except Exception:
            return False

    def list_artifacts(self, mission_id: str, include_expired: bool = True) -> List[Dict[str, Any]]:
        items = [self._artifacts[artifact_id] for artifact_id in self._mission_artifacts.get(mission_id, [])]
        if not include_expired:
            items = [artifact for artifact in items if not self._is_expired(artifact)]
        return [artifact.to_dict() for artifact in items]

    def get_artifact(self, artifact_id: str) -> Optional[EvidenceArtifact]:
        return self._artifacts.get(artifact_id)

    def export_bundle(self, mission_id: str, include_expired: bool = True) -> Dict[str, Any]:
        artifact_ids = self._mission_artifacts.get(mission_id, [])
        artifacts = [self._artifacts[artifact_id] for artifact_id in artifact_ids]
        if not include_expired:
            artifacts = [artifact for artifact in artifacts if not self._is_expired(artifact)]
        artifact_dicts = [artifact.to_dict() for artifact in artifacts]
        chain_of_custody = [
            {
                "artifact_id": artifact.artifact_id,
                "content_hash": artifact.content_hash,
                "previous_hash": artifact.previous_hash,
                "chain_index": artifact.metadata.get("chain_index"),
                "created_at": artifact.created_at,
            }
            for artifact in artifacts
        ]
        return {
            "mission_id": mission_id,
            "artifact_count": len(artifact_dicts),
            "artifacts": artifact_dicts,
            "chain_of_custody": chain_of_custody,
            "retention_policy": {
                "retention_days": self.retention_days,
                "include_expired": include_expired,
            },
            "expired_artifact_count": len([artifact for artifact in artifacts if self._is_expired(artifact)]),
            "generated_at": datetime.utcnow().isoformat(),
            "bundle_hash": hashlib.sha256("".join(item["content_hash"] for item in artifact_dicts).encode("utf-8")).hexdigest() if artifact_dicts else None,
        }

    def export_download_payload(self, mission_id: str, include_expired: bool = True) -> Dict[str, Any]:
        manifest = self.export_bundle(mission_id, include_expired=include_expired)
        encoded = base64.b64encode(json.dumps(manifest).encode("utf-8")).decode("utf-8")
        return {"manifest": manifest, "encoded_manifest": encoded}

    def verify_artifact(self, artifact_id: str) -> Dict[str, Any]:
        """Item 20: Tamper detection by re-hashing file content."""
        artifact = self._artifacts.get(artifact_id)
        if not artifact:
            return {"valid": False, "reason": "not_found", "artifact_id": artifact_id}
        file_path = Path(artifact.file_path)
        if not file_path.exists():
            return {"valid": False, "reason": "file_missing", "artifact_id": artifact_id}
        try:
            actual_hash = hashlib.sha256(file_path.read_bytes()).hexdigest()
        except Exception as exc:
            return {"valid": False, "reason": f"read_error: {exc}", "artifact_id": artifact_id}
        if actual_hash != artifact.content_hash:
            return {
                "valid": False,
                "reason": "hash_mismatch",
                "artifact_id": artifact_id,
                "expected_hash": artifact.content_hash,
                "actual_hash": actual_hash,
            }
        return {"valid": True, "artifact_id": artifact_id, "content_hash": artifact.content_hash}

    def verify_chain(self, mission_id: str) -> Dict[str, Any]:
        """Item 20: Verify cryptographic chain of custody for all artifacts in a mission."""
        ids = self._mission_artifacts.get(mission_id, [])
        results = []
        for i, aid in enumerate(ids):
            art = self._artifacts.get(aid)
            if not art:
                results.append({"valid": False, "artifact_id": aid, "reason": "not_found", "chain_valid": False})
                continue
            check = self.verify_artifact(aid)
            if i > 0:
                prev = self._artifacts.get(ids[i - 1])
                expected_prev = prev.content_hash if prev else None
                check["chain_valid"] = art.previous_hash == expected_prev
            else:
                check["chain_valid"] = art.previous_hash is None
            results.append(check)
        return {
            "mission_id": mission_id,
            "chain_length": len(ids),
            "all_valid": all(r.get("valid") and r.get("chain_valid", True) for r in results),
            "artifacts": results,
        }

    def export_zip(self, mission_id: str) -> bytes:
        """Item 13: Export evidence bundle as ZIP bytes."""
        import io, zipfile
        bundle = self.export_bundle(mission_id)
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("manifest.json", json.dumps(bundle, indent=2))
            zf.writestr("chain_of_custody.json", json.dumps(bundle.get("chain_of_custody", []), indent=2))
            for artifact_dict in bundle.get("artifacts", []):
                path = Path(artifact_dict.get("file_path", ""))
                if path.exists():
                    zf.write(path, f"artifacts/{path.name}")
        buf.seek(0)
        return buf.getvalue()


_evidence_vault: Optional[EvidenceVault] = None


def get_evidence_vault() -> EvidenceVault:
    global _evidence_vault
    if _evidence_vault is None:
        _evidence_vault = EvidenceVault()
    return _evidence_vault