#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import shutil
from pathlib import Path
from typing import Any, Dict, List, Tuple


# Nur diese Pack-Dateien sollen verarbeitet werden
TARGET_FILES = {
    "pf-companions.db",
    "pf-eidolon-forms.db",
    "pf-familiars.db",
    "pf-merchants.db",
    "pf-traps-and-haunts.db",
}

SPLIT_RE = re.compile(r"[;,]+")


def get(d: Dict[str, Any], path: str, default=None):
    cur: Any = d
    for part in path.split("."):
        if not isinstance(cur, dict) or part not in cur:
            return default
        cur = cur[part]
    return cur


def ensure_dict_path(d: Dict[str, Any], path: str) -> Dict[str, Any]:
    cur: Any = d
    for part in path.split("."):
        if part not in cur or not isinstance(cur[part], dict):
            cur[part] = {}
        cur = cur[part]
    return cur  # type: ignore[return-value]


def str_to_list(s: str) -> List[str]:
    """Convert 'A;B;' or 'A, B' -> ['A','B']."""
    tokens = [t.strip() for t in SPLIT_RE.split(s)]
    return [t for t in tokens if t]


def convert_plus_number_strings(obj: Any) -> bool:
    """
    Walk dict/list and convert strings like '+2' to int(2).
    Returns True if anything changed.
    """
    changed = False
    if isinstance(obj, dict):
        for k, v in list(obj.items()):
            if isinstance(v, str):
                s = v.strip()
                if s.startswith("+") and s[1:].isdigit():
                    obj[k] = int(s[1:])
                    changed = True
            else:
                if convert_plus_number_strings(v):
                    changed = True
    elif isinstance(obj, list):
        for i, v in enumerate(list(obj)):
            if isinstance(v, str):
                s = v.strip()
                if s.startswith("+") and s[1:].isdigit():
                    obj[i] = int(s[1:])
                    changed = True
            else:
                if convert_plus_number_strings(v):
                    changed = True
    return changed


def ensure_trait_arrays(traits: Dict[str, Any], key: str, changes: List[str]) -> bool:
    """
    Ensure system.traits.<key> exists and has:
      - value as list (default [])
      - custom/customTotal as list if present as string
    Returns changed?
    """
    changed = False

    if key not in traits or not isinstance(traits.get(key), dict):
        traits[key] = {}
        changed = True
        changes.append(f"traits.{key}: created dict")

    trait = traits[key]
    assert isinstance(trait, dict)

    # Ensure value is list (this fixes value.forEach crashes)
    v = trait.get("value", None)
    if v is None:
        trait["value"] = []
        changed = True
        changes.append(f"traits.{key}.value: None/missing -> []")
    elif isinstance(v, str):
        # some bad imports store "fire; cold" as string
        trait["value"] = str_to_list(v)
        changed = True
        changes.append(f"traits.{key}.value: str -> list")
    elif isinstance(v, list):
        # clean list
        before = list(v)
        cleaned = [x for x in v if isinstance(x, str) and x.strip()]
        if cleaned != before:
            trait["value"] = cleaned
            changed = True
            changes.append(f"traits.{key}.value: cleaned list")
    else:
        # any other type -> safest default
        trait["value"] = []
        changed = True
        changes.append(f"traits.{key}.value: invalid type -> []")

    # Ensure custom/customTotal are lists if they exist as strings
    for field in ("custom", "customTotal"):
        val = trait.get(field)
        if isinstance(val, str):
            trait[field] = str_to_list(val)
            changed = True
            changes.append(f"traits.{key}.{field}: str -> list")

        elif isinstance(val, list):
            before = list(val)
            cleaned = [x for x in val if isinstance(x, str) and x.strip()]
            if cleaned != before:
                trait[field] = cleaned
                changed = True
                changes.append(f"traits.{key}.{field}: cleaned list")

    return changed


def repair_actor_doc(doc: Dict[str, Any]) -> Tuple[bool, List[str]]:
    """
    Repair a single actor doc for PF1 Character-sheet resistance parsing.
    """
    changes: List[str] = []
    changed = False

    # Only act on documents that look like PF1 actors with system.traits
    traits = get(doc, "system.traits")
    if not isinstance(traits, dict):
        # still normalize +numbers globally
        if convert_plus_number_strings(doc):
            changed = True
            changes.append("global: converted +N strings")
        return changed, changes

    # These are the usual suspects for parseResistances / trait iteration:
    # - eres: energy resistances
    # - dr: damage reduction
    # - dv: damage vulnerabilities / immunities sometimes referenced nearby
    for key in ("eres", "dr", "dv"):
        if ensure_trait_arrays(traits, key, changes):
            changed = True

    # Also: nulls in languages.value can still exist
    lang_val = get(doc, "system.traits.languages.value")
    if isinstance(lang_val, list):
        nulls = sum(1 for x in lang_val if x is None)
        if nulls:
            ensure_dict_path(doc, "system.traits.languages")
            doc["system"]["traits"]["languages"]["value"] = [x for x in lang_val if x is not None]
            changed = True
            changes.append(f"languages.value: removed {nulls} null(s)")

    # Normalize "+2" strings anywhere (prevents the jquery number-input warning)
    if convert_plus_number_strings(doc):
        changed = True
        changes.append("global: converted +N strings")

    return changed, changes


def should_patch_doc(doc: Dict[str, Any]) -> bool:
    """
    We target actors that might render in ActorSheetPFCharacter.
    In PF1 these are commonly type 'character' (and sometimes 'npc' in some packs).
    """
    t = doc.get("type")
    return t in ("character", "npc")


def process_db_file(inp: Path, outp: Path, backup: bool, report_dir: Path | None) -> int:
    outp.parent.mkdir(parents=True, exist_ok=True)

    if backup:
        bak = outp.with_suffix(outp.suffix + ".bak")
        shutil.copy2(inp, bak)

    patched = 0
    report_lines: List[str] = []

    with inp.open("r", encoding="utf-8", errors="replace") as r, outp.open("w", encoding="utf-8", newline="\n") as w:
        for line_no, line in enumerate(r, start=1):
            raw = line.rstrip("\n")
            if not raw.strip():
                w.write(line)
                continue

            try:
                doc = json.loads(raw)
            except json.JSONDecodeError:
                w.write(line)
                continue

            if not isinstance(doc, dict):
                w.write(line)
                continue

            if should_patch_doc(doc):
                changed, changes = repair_actor_doc(doc)
                if changed:
                    patched += 1
                    report_lines.append(
                        f"Line {line_no}: type={doc.get('type')!r}, name={doc.get('name')!r}, _id={doc.get('_id')!r} -> "
                        + "; ".join(changes)
                    )

            w.write(json.dumps(doc, ensure_ascii=False) + "\n")

    if report_dir is not None:
        report_dir.mkdir(parents=True, exist_ok=True)
        (report_dir / (inp.name + ".repair_report.txt")).write_text("\n".join(report_lines), encoding="utf-8")

    return patched


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Repair PF1 character-sheet resistance parsing issues in selected packs (*.db) from packages/ -> packages_processed/."
    )
    ap.add_argument("--packages", type=Path, default=Path("packages"), help='Input folder (default: "packages")')
    ap.add_argument(
        "--packages-processed",
        type=Path,
        default=Path("packages_processed"),
        help='Output folder (default: "packages_processed")',
    )
    ap.add_argument("--recursive", action="store_true", help="Search recursively under packages/")
    ap.add_argument("--backup", action="store_true", help="Create .bak next to each processed output file")
    ap.add_argument("--reports", action="store_true", help="Write per-file reports into packages_processed/_reports/")
    args = ap.parse_args()

    in_dir: Path = args.packages
    out_dir: Path = args.packages_processed

    if not in_dir.exists() or not in_dir.is_dir():
        print(f"ERROR: packages folder not found: {in_dir}")
        return 2

    pattern = "**/*.db" if args.recursive else "*.db"
    candidates = sorted(in_dir.glob(pattern))

    targets = [p for p in candidates if p.name in TARGET_FILES]
    if not targets:
        print("No target .db files found. Looking for:")
        for f in sorted(TARGET_FILES):
            print(f" - {f}")
        print(f"In folder: {in_dir} (recursive={args.recursive})")
        return 0

    report_dir = (out_dir / "_reports") if args.reports else None

    total_patched = 0
    for i, inp in enumerate(targets, start=1):
        rel = inp.relative_to(in_dir)
        outp = out_dir / rel
        patched = process_db_file(inp, outp, backup=args.backup, report_dir=report_dir)
        total_patched += patched
        print(f"[{i}/{len(targets)}] {rel} -> patched_docs={patched}")

    print("\nDone.")
    print(f"Output folder: {out_dir}")
    print(f"Patched docs total: {total_patched}")
    if report_dir is not None:
        print(f"Reports folder: {report_dir}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())