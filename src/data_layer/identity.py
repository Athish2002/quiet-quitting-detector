# src/data_layer/identity.py
# Identity resolution + pseudonymization.
#
# Real HR data does not arrive with clean, stable keys. The previous approach --
# key every record on `first_name_of(name)` -- fails in both directions at once,
# and both failures were reproduced before this module was written:
#
#   MERGE:  "Arjun Sharma" and "Arjun Patel" both collapse to "Arjun", so two
#           different people's metrics interleave into one timeline. Both get a
#           wrong score, and the baseline is meaningless.
#   SPLIT:  "Arjun" / "arjun" / " ARJUN " become three identities, fragmenting
#           one person's history so no trailing baseline can ever form.
#
# Resolution order, strongest key first:
#   1. An explicit employee/staff ID, if the source provides one. Real systems
#      have one; it is the only key that survives a name change.
#   2. A registered alias (handles marriage, legal name change, transliteration).
#   3. Normalised full name -- last resort, and collisions are reported rather
#      than silently merged.
#
# The surrogate ID is a salted hash, so downstream stores, filenames and logs
# never contain a real name. That is the Phase 0 pseudonymization requirement:
# the name <-> surrogate mapping lives in its own store with its own access
# control, and nothing else needs the real name at all.

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import threading
import unicodedata
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# Separate store, separate access control (Phase 0). Never commit this file.
IDENTITY_MAP_PATH = os.environ.get(
    "IDENTITY_MAP_PATH", os.path.join("data", "identity_map.json")
)

_DEV_SALT = "dev-only-insecure-salt"
_lock = threading.Lock()

ID_COLUMN_ALIASES = [
    "employee_id",
    "employee id",
    "emp_id",
    "empid",
    "staff_id",
    "staff id",
    "person_id",
    "worker_id",
    "user_id",
    "id",
]


def _salt() -> str:
    salt = os.environ.get("IDENTITY_SALT", "").strip()
    if not salt:
        # Loud, because an unsalted/predictable hash means the pseudonyms are
        # reversible by brute force over a name list -- i.e. not pseudonymous.
        logger.warning(
            "IDENTITY_SALT is not set; using an insecure development salt. "
            "Set IDENTITY_SALT before processing real personal data."
        )
        return _DEV_SALT
    return salt


def normalize_name(raw: str | None) -> str:
    """Fold a free-text name to a stable comparison key.

    Handles the variance that actually shows up in exports: casing, padding,
    accents ("José"/"Jose"), non-breaking spaces, honorifics, punctuation
    ("O'Brien"/"OBrien"), and "Last, First" ordering.
    """
    if not raw:
        return ""
    text = unicodedata.normalize("NFKD", str(raw))
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = text.replace(chr(0xA0), " ").strip()  # NBSP -> plain space

    # "Sharma, Arjun" -> "Arjun Sharma"
    if "," in text and text.count(",") == 1:
        last, first = (p.strip() for p in text.split(","))
        if first and last:
            text = f"{first} {last}"

    text = text.casefold()
    text = re.sub(r"\b(mr|mrs|ms|miss|dr|prof|sir)\.?\s+", "", text)
    text = re.sub(r"\s+(jr|sr|ii|iii|iv)\.?$", "", text)
    text = re.sub(r"[^a-z0-9\s]", "", text)
    return re.sub(r"\s+", " ", text).strip()


def _hash(value: str) -> str:
    digest = hashlib.sha256(f"{_salt()}::{value}".encode()).hexdigest()
    return f"emp_{digest[:16]}"


@dataclass(frozen=True)
class ResolvedIdentity:
    surrogate_id: str
    display_name: str  # first name only -- all the UI/briefings ever need
    key_source: str  # "employee_id" | "alias" | "name"
    normalized_key: str
    is_ambiguous: bool = False  # name-keyed and colliding with another person


class IdentityResolver:
    """Resolves incoming rows to stable surrogate IDs.

    Persists its mapping so surrogate IDs stay stable across runs -- without
    that, every restart would re-key the entire history and destroy baselines.
    """

    def __init__(self, map_path: str | None = None):
        self.map_path = map_path or IDENTITY_MAP_PATH
        self._map: dict = self._load()

    def _load(self) -> dict:
        try:
            with open(self.map_path, encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                data.setdefault("by_key", {})
                data.setdefault("aliases", {})
                data.setdefault("names", {})
                return data
        except (OSError, json.JSONDecodeError, ValueError):
            pass
        return {"by_key": {}, "aliases": {}, "names": {}}

    def _save(self) -> None:
        try:
            os.makedirs(os.path.dirname(os.path.abspath(self.map_path)), exist_ok=True)
            tmp = f"{self.map_path}.tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(self._map, f, indent=2)
            os.replace(tmp, self.map_path)
        except OSError:
            logger.error("Could not persist identity map.", exc_info=True)

    def register_alias(self, previous_name: str, employee_id: str) -> None:
        """Bind a former name to an employee ID so a rename keeps its history.

        The realistic case is a legal name change: without this the person
        becomes a new identity with no baseline, and looks like a brand-new
        joiner rather than someone with two years of context.
        """
        with _lock:
            self._map["aliases"][normalize_name(previous_name)] = str(
                employee_id
            ).strip()
            self._save()

    def resolve(self, row: dict) -> ResolvedIdentity:
        from src.data_layer.ingestion import COLUMN_ALIASES, resolve_header_value

        raw_name = resolve_header_value(row, COLUMN_ALIASES["name"], "")
        raw_id = resolve_header_value(row, ID_COLUMN_ALIASES, "")
        norm_name = normalize_name(raw_name)
        display = (raw_name or "Unknown").split()[0] if raw_name.strip() else "Unknown"

        # 1. Explicit ID -- survives name changes, never collides.
        if str(raw_id).strip():
            key = f"id:{str(raw_id).strip().casefold()}"
            return self._commit(key, "employee_id", display, norm_name, raw_id=raw_id)

        # 2. Known alias for a renamed person.
        alias_id = self._map["aliases"].get(norm_name)
        if alias_id:
            key = f"id:{alias_id.casefold()}"
            return self._commit(key, "alias", display, norm_name)

        # 3. Name key. Weakest: cannot survive a rename, and distinct people
        #    sharing a full name are genuinely indistinguishable here.
        if not norm_name:
            return ResolvedIdentity(_hash("key:unknown"), "Unknown", "name", "")
        return self._commit(f"name:{norm_name}", "name", display, norm_name)

    def _commit(
        self, key: str, key_source: str, display: str, norm_name: str, raw_id: str = ""
    ) -> ResolvedIdentity:
        with _lock:
            surrogate = self._map["by_key"].get(key)
            if surrogate is None:
                surrogate = _hash(key)
                self._map["by_key"][key] = surrogate

            # Track which distinct full names have mapped to this surrogate.
            seen = self._map["names"].setdefault(surrogate, [])
            if norm_name and norm_name not in seen:
                seen.append(norm_name)

            ambiguous = False
            # Ambiguity means we genuinely COULD NOT tell people apart -- i.e.
            # the source gave only a bare first name that several people share.
            # A full name that merely shares a first name with someone else
            # ("Arjun Sharma" vs "Arjun Patel") resolved correctly and must not
            # warn; crying wolf there just trains operators to ignore warnings.
            if key_source == "name" and norm_name and " " not in norm_name:
                owners = {
                    s
                    for s, names in self._map["names"].items()
                    if any(n.split()[0] == norm_name for n in names if n)
                }
                if len(owners) > 1:
                    ambiguous = True
                    logger.warning(
                        "Ambiguous identity: bare first name %r matches %d distinct "
                        "people. Provide an employee_id column to disambiguate -- "
                        "their metrics cannot be told apart.",
                        display,
                        len(owners),
                    )
            self._save()

        return ResolvedIdentity(surrogate, display, key_source, norm_name, ambiguous)

    def display_name_for(self, surrogate_id: str) -> str | None:
        names = self._map["names"].get(surrogate_id) or []
        return names[-1].title() if names else None


_default_resolver: IdentityResolver | None = None


def get_resolver() -> IdentityResolver:
    global _default_resolver
    if _default_resolver is None:
        _default_resolver = IdentityResolver()
    return _default_resolver


def reset_resolver() -> None:
    """Test hook -- drops the cached resolver so a patched path takes effect."""
    global _default_resolver
    _default_resolver = None
