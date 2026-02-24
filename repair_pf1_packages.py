#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import shutil
from pathlib import Path
from typing import Any, Dict, List, Tuple


TRAIT_KEYS = ["di", "dv", "ci", "languages", "armorProf", "weaponProf"]

# split on semicolon or comma; keep it conservative
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
    """
    Convert "A;B;" or "A, B" into ["A","B"].
    Removes empty tokens and trims whitespace.
    """
    if not isinstance(s, str):
        return []
    tokens = [t.strip() for t in SPLIT_RE.split(s)]
    tokens = [t for t in tokens if t]
    return tokens


def convert_plus_number_strings(obj: Any, changes: List[str] | None = None) -> bool:
    """
    Walk any dict/list and convert strings like '+2' or '+10' to int.
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
                    if changes is not None:
                        changes.append(f'plus-number: {k} "{v}" -> {obj[k]}')
            else:
                if convert_plus_number_strings(v, changes):
                    changed = True

    elif isinstance(obj, list):
        for i, v in enumerate(list(obj)):
            if isinstance(v, str):
                s = v.strip()
                if s.startswith("+") and s[1:].isdigit():
                    obj[i] = int(s[1:])
                    changed = True
                    if changes is not None:
                        changes.append(f'plus-number: [{i}] "{v}" -> {obj[i]}')
            else:
                if convert_plus_number_strings(v, changes):
                    changed = True

    return changed


def repair_doc(doc: Dict[str, Any]) -> Tuple[bool, List[str]]:
    changes: List[str] = []
    changed = False

    # We'll patch anything that has system.traits.<...>
    traits = get(doc, "system.traits")
    if not isinstance(traits, dict):
        # Still run +number conversion globally (can fix input-number warnings in other docs)
        if convert_plus_number_strings(doc, changes):
            changed = True
        return changed, changes

    # 1) Fix languages.value: remove nulls (this one also causes weirdness elsewhere)
    lang_val = get(doc, "system.traits.languages.value")
    if isinstance(lang_val, list):
        nulls = sum(1 for x in lang_val if x is None)
        if nulls:
            ensure_dict_path(doc, "system.traits.languages")
            doc["system"]["traits"]["languages"]["value"] = [x for x in lang_val if x is not None]
            changed = True
            changes.append(f"languages.value: removed {nulls} null(s)")

    # 2) The real crash-fix: custom/customTotal must be arrays, not strings
    for k in TRAIT_KEYS:
        trait = traits.get(k)
        if not isinstance(trait, dict):
            continue

        for field in ("custom", "customTotal"):
            val = trait.get(field)
            if isinstance(val, str):
                new_list = str_to_list(val)
                trait[field] = new_list  # type: ignore[assignment]
                changed = True
                changes.append(f"{k}.{field}: str -> list ({len(new_list)} item(s))")

            elif val is None:
                pass
            elif isinstance(val, list):
                before = list(val)
                cleaned = [x for x in val if isinstance(x, str) and x.strip()]
                if cleaned != before:
                    trait[field] = cleaned  # type: ignore[assignment]
                    changed = True
                    changes.append(f"{k}.{field}: cleaned list")

    # 3) Optional: If someone stored value as a single string with separators,
    # convert to list (PF1 already wraps non-array into [value], but this makes it nicer)
    for k in ("di", "dv", "ci"):
        trait = traits.get(k)
        if not isinstance(trait, dict):
            continue
        v = trait.get("value")
        if isinstance(v, str) and (";" in v or "," in v):
            new_v = str_to_list(v)
            trait["value"] = new_v
            changed = True
            changes.append(f"{k}.value: split str -> list ({len(new_v)} item(s))")

    # 4) Fix UI warning: convert "+2" style strings to ints across the document
    if convert_plus_number_strings(doc, changes):
        changed = True

    return changed, changes


def process_db_file(
    inp: Path,
    outp: Path,
    only_npc: bool = True,
    backup: bool = False,
    report_dir: Path | None = None,
) -> Tuple[int, int]:
    """
    Process one .db (NeDB JSON-lines) file.
    Returns (patched_docs, total_lines).
    """
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

            if only_npc and doc.get("type") != "npc":
                w.write(json.dumps(doc, ensure_ascii=False) + "\n")
                continue

            changed, changes = repair_doc(doc)
            if changed:
                patched += 1
                name = doc.get("name")
                _id = doc.get("_id")
                dtype = doc.get("type")
                report_lines.append(
                    f"Line {line_no}: type={dtype!r}, name={name!r}, _id={_id!r} -> " + "; ".join(changes)
                )

            w.write(json.dumps(doc, ensure_ascii=False) + "\n")

    if report_dir is not None:
        report_dir.mkdir(parents=True, exist_ok=True)
        report_path = report_dir / (inp.name + ".repair_report.txt")
        report_path.write_text("\n".join(report_lines), encoding="utf-8")

    return patched, line_no


def main() -> int:
    ap = argparse.ArgumentParser(
        description=(
            "Batch-repair Foundry PF1 NeDB .db files by converting system.traits.*.custom strings into arrays "
            "(fixes n.forEach crash) and normalizing '+N' numeric strings."
        )
    )
    ap.add_argument("--packages", type=Path, default=Path("packages"), help='Input folder (default: "packages")')
    ap.add_argument(
        "--packages-processed",
        type=Path,
        default=Path("packages_processed"),
        help='Output folder (default: "packages_processed")',
    )
    ap.add_argument("--recursive", action="store_true", help="Search for .db files recursively under packages/")
    ap.add_argument("--only-npc", action="store_true", help="Only patch documents with type=='npc' (recommended)")
    ap.add_argument("--backup", action="store_true", help="Create a .bak copy alongside each processed output file")
    ap.add_argument(
        "--reports",
        action="store_true",
        help="Write per-file reports into packages_processed/_reports/",
    )
    args = ap.parse_args()

    in_dir: Path = args.packages
    out_dir: Path = args.packages_processed
    if not in_dir.exists() or not in_dir.is_dir():
        print(f"ERROR: packages folder not found: {in_dir}")
        return 2

    pattern = "**/*.db" if args.recursive else "*.db"
    db_files = sorted(in_dir.glob(pattern))

    if not db_files:
        print(f"No .db files found in {in_dir} (recursive={args.recursive})")
        return 0

    report_dir = (out_dir / "_reports") if args.reports else None

    total_files = 0
    total_patched = 0

    for inp in db_files:
        rel = inp.relative_to(in_dir)
        outp = out_dir / rel
        outp.parent.mkdir(parents=True, exist_ok=True)

        patched, _ = process_db_file(
            inp=inp,
            outp=outp,
            only_npc=args.only_npc,
            backup=args.backup,
            report_dir=report_dir,
        )

        total_files += 1
        total_patched += patched
        print(f"[{total_files}/{len(db_files)}] {rel} -> patched_docs={patched}")

    print("\nDone.")
    print(f"Processed files: {total_files}")
    print(f"Patched docs total: {total_patched}")
    print(f"Output folder: {out_dir}")
    if report_dir is not None:
        print(f"Reports folder: {report_dir}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())