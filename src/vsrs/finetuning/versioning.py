"""Dataset versioning and deduplication for fine-tuning.

Manages dataset versions with content hashing, deduplication, and
metadata tracking. Supports comparing versions and computing diffs.
"""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from vsrs.core.logging import get_logger

logger = get_logger("finetuning.versioning")


def _hash_entry(entry: dict[str, Any]) -> str:
    """Compute a stable hash for a dataset entry."""
    return hashlib.sha256(
        json.dumps(entry, sort_keys=True, default=str).encode()
    ).hexdigest()


@dataclass
class DatasetVersion:
    """A versioned snapshot of a dataset.

    Attributes:
        version_id: Unique version identifier (semantic version or hash-based).
        dataset_path: Path to the JSONL file.
        entry_count: Number of entries in the dataset.
        unique_entries: Number of unique entries (after dedup).
        duplicate_count: Number of duplicates removed.
        content_hash: SHA-256 hash of the full dataset content.
        created_at: When this version was created.
        metadata: Additional metadata (source, filters, split info).
        size_bytes: File size in bytes.
    """

    version_id: str = ""
    dataset_path: str = ""
    entry_count: int = 0
    unique_entries: int = 0
    duplicate_count: int = 0
    content_hash: str = ""
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: dict[str, Any] = field(default_factory=dict)
    size_bytes: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "version_id": self.version_id,
            "dataset_path": self.dataset_path,
            "entry_count": self.entry_count,
            "unique_entries": self.unique_entries,
            "duplicate_count": self.duplicate_count,
            "content_hash": self.content_hash,
            "created_at": self.created_at.isoformat(),
            "metadata": self.metadata,
            "size_bytes": self.size_bytes,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> DatasetVersion:
        return cls(
            version_id=data["version_id"],
            dataset_path=data.get("dataset_path", ""),
            entry_count=data.get("entry_count", 0),
            unique_entries=data.get("unique_entries", 0),
            duplicate_count=data.get("duplicate_count", 0),
            content_hash=data.get("content_hash", ""),
            created_at=datetime.fromisoformat(data["created_at"]) if data.get("created_at") else datetime.now(timezone.utc),
            metadata=data.get("metadata", {}),
            size_bytes=data.get("size_bytes", 0),
        )


class DatasetVersionManager:
    """Manages dataset versions with deduplication.

    Provides:
    - Version creation with content hashing and deduplication
    - Version lookup and listing
    - Version comparison (diff between versions)
    - Deduplication of JSONL datasets

    Args:
        storage_dir: Directory to store versioned datasets and metadata.
    """

    def __init__(self, storage_dir: str | Path = ".vsrs_datasets") -> None:
        self.storage_dir = Path(storage_dir)
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self._versions: dict[str, DatasetVersion] = {}

    def create_version(
        self,
        dataset_path: str | Path,
        version_id: str = "",
        metadata: dict[str, Any] | None = None,
        deduplicate: bool = True,
    ) -> DatasetVersion:
        """Create a new dataset version with optional deduplication.

        Args:
            dataset_path: Path to the JSONL dataset file.
            version_id: Optional version ID (auto-generated if empty).
            metadata: Optional metadata to attach.
            deduplicate: Whether to remove duplicate entries.

        Returns:
            DatasetVersion describing the created version.
        """
        dataset_path = Path(dataset_path)
        if not dataset_path.exists():
            raise FileNotFoundError(f"Dataset not found: {dataset_path}")

        # Read entries
        entries: list[dict[str, Any]] = []
        with open(dataset_path) as f:
            for line in f:
                line = line.strip()
                if line:
                    entries.append(json.loads(line))

        original_count = len(entries)

        # Deduplicate
        seen_hashes: set[str] = set()
        unique_entries: list[dict[str, Any]] = []
        for entry in entries:
            h = _hash_entry(entry)
            if h not in seen_hashes:
                seen_hashes.add(h)
                unique_entries.append(entry)

        duplicate_count = original_count - len(unique_entries)

        # Compute content hash
        content = json.dumps(unique_entries, sort_keys=True, default=str)
        content_hash = hashlib.sha256(content.encode()).hexdigest()

        # Generate version ID if not provided
        if not version_id:
            version_id = f"v_{content_hash[:12]}"

        # Write deduplicated dataset to storage
        versioned_path = self.storage_dir / f"{version_id}.jsonl"
        with open(versioned_path, "w") as f:
            for entry in unique_entries:
                f.write(json.dumps(entry, default=str) + "\n")

        size_bytes = versioned_path.stat().st_size

        version = DatasetVersion(
            version_id=version_id,
            dataset_path=str(versioned_path),
            entry_count=original_count,
            unique_entries=len(unique_entries),
            duplicate_count=duplicate_count,
            content_hash=content_hash,
            metadata=metadata or {},
            size_bytes=size_bytes,
        )

        self._versions[version_id] = version
        logger.info(
            f"Created dataset version {version_id}: "
            f"{original_count} entries, {duplicate_count} duplicates removed, "
            f"{len(unique_entries)} unique"
        )
        return version

    def get_version(self, version_id: str) -> DatasetVersion | None:
        """Get a version by ID."""
        return self._versions.get(version_id)

    def list_versions(self) -> list[DatasetVersion]:
        """List all versions, sorted by creation time."""
        return sorted(
            self._versions.values(),
            key=lambda v: v.created_at,
        )

    def compare_versions(
        self,
        version_id_a: str,
        version_id_b: str,
    ) -> dict[str, Any]:
        """Compare two dataset versions.

        Returns:
            Dict with added, removed, common entry counts and hash comparison.
        """
        va = self._versions.get(version_id_a)
        vb = self._versions.get(version_id_b)
        if va is None or vb is None:
            raise ValueError("One or both versions not found")

        # Load entries from both versions
        entries_a = self._load_entries(va.dataset_path)
        entries_b = self._load_entries(vb.dataset_path)

        hashes_a = {_hash_entry(e) for e in entries_a}
        hashes_b = {_hash_entry(e) for e in entries_b}

        added = hashes_b - hashes_a
        removed = hashes_a - hashes_b
        common = hashes_a & hashes_b

        return {
            "version_a": version_id_a,
            "version_b": version_id_b,
            "entries_a": len(entries_a),
            "entries_b": len(entries_b),
            "added": len(added),
            "removed": len(removed),
            "common": len(common),
            "identical": va.content_hash == vb.content_hash,
        }

    def _load_entries(self, path: str) -> list[dict[str, Any]]:
        """Load entries from a JSONL file."""
        entries: list[dict[str, Any]] = []
        p = Path(path)
        if p.exists():
            with open(p) as f:
                for line in f:
                    line = line.strip()
                    if line:
                        entries.append(json.loads(line))
        return entries

    def deduplicate(
        self,
        input_path: str | Path,
        output_path: str | Path,
    ) -> tuple[int, int]:
        """Deduplicate a JSONL dataset and write to output.

        Args:
            input_path: Path to input JSONL.
            output_path: Path to write deduplicated JSONL.

        Returns:
            (original_count, unique_count) tuple.
        """
        input_path = Path(input_path)
        output_path = Path(output_path)

        entries = self._load_entries(str(input_path))
        original_count = len(entries)

        seen: set[str] = set()
        unique: list[dict[str, Any]] = []
        for entry in entries:
            h = _hash_entry(entry)
            if h not in seen:
                seen.add(h)
                unique.append(entry)

        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w") as f:
            for entry in unique:
                f.write(json.dumps(entry, default=str) + "\n")

        logger.info(
            f"Deduplicated {input_path}: {original_count} -> {len(unique)} "
            f"({original_count - len(unique)} duplicates removed)"
        )
        return original_count, len(unique)

    def count(self) -> int:
        """Get the number of registered versions."""
        return len(self._versions)

    def clear(self) -> None:
        """Remove all versions from memory (does not delete files)."""
        self._versions.clear()
