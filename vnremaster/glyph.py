"""CJK glyph substitution codec and font-coverage audit.

Many older Japanese games ship a font whose ``cmap`` contains the Japanese
glyph repertoire but not every Simplified Chinese character. Rebuilding the
font is one option; a lighter option is to substitute a Simplified character
with a Japanese character whose glyph is visually equivalent (for example
``说 -> 説``) and keep an explicit, reversible mapping table.

This module does not invent mappings. It loads a curated table, applies it,
and reports which resulting codepoints are missing from a given font.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

from .fontcmap import load_cmap, missing_chars

__all__ = [
    "AmbiguousGlyphError",
    "AuditReport",
    "GlyphCodec",
    "GlyphEntry",
    "GlyphPlan",
    "UnmappedGlyphError",
    "load_map",
    "plan_map",
]

_SAFE_PASSTHROUGH = set("\r\n\t")


class UnmappedGlyphError(ValueError):
    """Strict encoding encountered a non-ASCII character with no mapping."""


class AmbiguousGlyphError(ValueError):
    """Strict decoding encountered a target produced by several source glyphs."""


@dataclass(frozen=True)
class GlyphEntry:
    source: str
    encoded: str
    mapped: bool
    in_font: bool


@dataclass
class AuditReport:
    entries: list[GlyphEntry] = field(default_factory=list)
    unmapped: list[str] = field(default_factory=list)
    font_missing: list[str] = field(default_factory=list)
    ambiguous_targets: dict[str, list[str]] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return not self.unmapped and not self.font_missing

    def summary(self) -> str:
        parts = [
            f"{len(self.entries)} unique characters",
            f"{len(self.unmapped)} unmapped",
            f"{len(self.font_missing)} missing from font",
        ]
        if self.ambiguous_targets:
            parts.append(f"{len(self.ambiguous_targets)} ambiguous targets")
        return ", ".join(parts)


@dataclass
class GlyphCodec:
    pairs: dict[str, str]
    name: str = ""
    description: str = ""

    def __post_init__(self) -> None:
        cleaned: dict[str, str] = {}
        for source, target in self.pairs.items():
            if not isinstance(source, str) or not isinstance(target, str):
                raise ValueError("glyph map keys and values must be strings")
            if len(source) != 1 or len(target) != 1:
                raise ValueError(
                    f"glyph map entries must be single characters: {source!r} -> {target!r}"
                )
            cleaned[source] = target
        self.pairs = cleaned

    @classmethod
    def from_json(cls, path: str | Path) -> "GlyphCodec":
        return load_map(path)

    @property
    def reverse(self) -> dict[str, list[str]]:
        reverse: dict[str, list[str]] = {}
        for source, target in self.pairs.items():
            if source == target:
                continue
            reverse.setdefault(target, []).append(source)
        for sources in reverse.values():
            sources.sort()
        return reverse

    @property
    def ambiguous_targets(self) -> dict[str, list[str]]:
        return {
            target: sources
            for target, sources in self.reverse.items()
            if len(sources) > 1
        }

    def encode(self, text: str, *, strict: bool = False) -> str:
        missing: list[str] = []
        out: list[str] = []
        for char in text:
            if char in self.pairs:
                out.append(self.pairs[char])
            else:
                if strict and ord(char) >= 128 and char not in _SAFE_PASSTHROUGH:
                    missing.append(char)
                out.append(char)
        if missing:
            unique = "".join(dict.fromkeys(missing))
            raise UnmappedGlyphError(
                f"no glyph mapping for: {unique!r}"
            )
        return "".join(out)

    def decode(self, text: str, *, strict: bool = False) -> str:
        reverse = self.reverse
        ambiguous = {
            target: sources
            for target, sources in reverse.items()
            if len(sources) > 1
        }
        out: list[str] = []
        for char in text:
            sources = reverse.get(char)
            if not sources:
                out.append(char)
                continue
            if len(sources) > 1 and strict:
                raise AmbiguousGlyphError(
                    f"target {char!r} maps back to {sources!r}"
                )
            out.append(sources[0])
        return "".join(out)

    def audit(
        self,
        text: str,
        cmap: frozenset[int] | set[int],
        *,
        strict: bool = False,
    ) -> AuditReport:
        report = AuditReport()
        report.ambiguous_targets = self.ambiguous_targets
        seen: set[str] = set()
        for char in text:
            if char in seen or char in _SAFE_PASSTHROUGH:
                continue
            seen.add(char)
            mapped = char in self.pairs
            encoded = self.pairs.get(char, char)
            in_font = ord(encoded) in cmap
            report.entries.append(GlyphEntry(char, encoded, mapped, in_font))
            if not mapped and ord(char) >= 128:
                report.unmapped.append(char)
            if not in_font:
                report.font_missing.append(encoded)
        if strict and (report.unmapped or report.font_missing):
            raise UnmappedGlyphError(
                "strict audit failed: "
                + ", ".join(
                    part
                    for part in (
                        f"unmapped={''.join(report.unmapped)!r}"
                        if report.unmapped
                        else "",
                        f"font_missing={''.join(report.font_missing)!r}"
                        if report.font_missing
                        else "",
                    )
                    if part
                )
            )
        return report


def _normalise_pairs(raw: dict) -> tuple[dict[str, str], str, str]:
    if "pairs" in raw:
        pairs = raw["pairs"]
    else:
        pairs = {
            key: value
            for key, value in raw.items()
            if not key.startswith("_")
            and key not in {"name", "description"}
        }
    if not isinstance(pairs, dict):
        raise ValueError("glyph map 'pairs' must be an object")
    name = str(raw.get("name", ""))
    description = str(raw.get("description", ""))
    return pairs, name, description


def load_map(path: str | Path) -> GlyphCodec:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("glyph map must be a JSON object")
    pairs, name, description = _normalise_pairs(data)
    return GlyphCodec(pairs=pairs, name=name, description=description)


@dataclass
class GlyphPlan:
    pairs: dict[str, str] = field(default_factory=dict)
    covered: list[str] = field(default_factory=list)
    suggested: dict[str, str] = field(default_factory=dict)
    unresolved: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "name": "generated-from-font",
            "description": (
                "Identity entries cover characters already present in the "
                "font; suggested entries use the supplied candidate table. "
                "Add mappings for the unresolved characters before shipping."
            ),
            "pairs": dict(self.pairs),
            "unresolved": list(self.unresolved),
        }

    def summary(self) -> str:
        return (
            f"{len(self.pairs)} mapped, {len(self.suggested)} suggested, "
            f"{len(self.unresolved)} unresolved"
        )


def plan_map(
    text: str,
    cmap: frozenset[int] | set[int],
    *,
    candidates: GlyphCodec | None = None,
) -> GlyphPlan:
    """Build a starter map: identity for covered chars, candidates for the rest."""
    plan = GlyphPlan()
    seen: set[str] = set()
    for char in text:
        if char in seen or char in _SAFE_PASSTHROUGH or ord(char) < 128:
            continue
        seen.add(char)
        if ord(char) in cmap:
            plan.pairs[char] = char
            plan.covered.append(char)
            continue
        target = candidates.pairs.get(char) if candidates else None
        if target and ord(target) in cmap:
            plan.pairs[char] = target
            plan.suggested[char] = target
        else:
            plan.unresolved.append(char)
    return plan


def audit_text(
    text: str,
    cmap: frozenset[int] | set[int],
    *,
    codec: GlyphCodec | None = None,
    strict: bool = False,
) -> AuditReport:
    codec = codec or GlyphCodec({})
    return codec.audit(text, cmap, strict=strict)


def font_missing(text: str, cmap: frozenset[int] | set[int]) -> list[str]:
    """Convenience wrapper that audits raw text without a glyph map."""
    return missing_chars(text, cmap)
