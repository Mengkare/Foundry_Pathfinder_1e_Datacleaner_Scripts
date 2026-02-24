#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path
from typing import Any, Dict, List, Tuple


TARGET_FILE = "pf-eidolon-forms.db"


def is_actor_doc(doc: Dict[str, Any]) -> bool:
    return doc.get("type") in ("character", "npc") and isinstance(doc.get("items"), list)


def get_item_tag(item: Dict[str, Any]) -> str | None:
    sysd = item.get("system")
    if isinstance(sysd, dict):
        t = sysd.get("tag")
        if isinstance(t, str) and t.strip():
            return t.strip()
    return None


def set_item_tag(item: Dict[str, Any], new_tag: str) -> None:
    sysd = item.setdefault("system", {})
    if not isinstance(sysd, dict):
        item["system"] = {}
        sysd = item["system"]
    sysd["tag"] = new_tag
    # PF1 expects custom tags for many resources
    sysd["useCustomTag"] = True


def iter_actions(item: Dict[str, Any]) -> List[Dict[str, Any]]:
    sysd = item.get("system")
    if not isinstance(sysd, dict):
        return []
    acts = sysd.get("actions")
    if not isinstance(acts, list):
        return []
    return [a for a in acts if isinstance(a, dict)]


def get_action_tag(action: Dict[str, Any]) -> str | None:
    t = action.get("tag")
    if isinstance(t, str) and t.strip():
        return t.strip()
    return None


def set_action_tag(action: Dict[str, Any], new_tag: str) -> None:
    action["tag"] = new_tag


def unique_tag(base: str, suffix: str, seen: set[str]) -> str:
    cand = f"{base}{suffix}"
    if cand not in seen:
        return cand
    i = 2
    while f"{cand}_{i}" in seen:
        i += 1
    return f"{cand}_{i}"


def get_resources_dict(actor: Dict[str, Any]) -> Dict[str, Any] | None:
    sysd = actor.get("system")
    if not isinstance(sysd, dict):
        return None
    res = sysd.get("resources")
    if isinstance(res, dict):
        return res
    return None


def fix_actor_identifiers_and_resources(actor: Dict[str, Any]) -> Tuple[bool, List[str]]:
    """
    Fixes:
      1) duplicate item tags inside actor
      2) action tags that collide with any existing identifier (items + other actions)
      3) resource keys in actor.system.resources that collide with item tags (main fix for your warning)
    """
    items = actor.get("items")
    if not isinstance(items, list):
        return False, []

    changes: List[str] = []
    changed = False

    # -------------------------
    # PASS 1: Unique item tags
    # -------------------------
    seen: set[str] = set()
    item_tags_in_actor: List[str] = []

    for it in items:
        if not isinstance(it, dict):
            continue
        tag = get_item_tag(it)
        if not tag:
            continue

        if tag not in seen:
            seen.add(tag)
            item_tags_in_actor.append(tag)
            continue

        # duplicate item tag -> rename duplicate
        item_id = it.get("_id")
        if not isinstance(item_id, str) or not item_id:
            item_id = "noid"
        new_tag = unique_tag(tag, f"_{item_id}", seen)
        set_item_tag(it, new_tag)

        seen.add(new_tag)
        item_tags_in_actor.append(new_tag)

        changed = True
        changes.append(f'Item "{it.get("name")}" ({item_id}): tag "{tag}" -> "{new_tag}"')

    # --------------------------------------
    # PASS 2: Action tags must not collide
    # --------------------------------------
    for it in items:
        if not isinstance(it, dict):
            continue
        it_name = it.get("name")
        for act in iter_actions(it):
            a_tag = get_action_tag(act)
            if not a_tag:
                continue

            if a_tag in seen:
                act_id = act.get("_id")
                if not isinstance(act_id, str) or not act_id:
                    act_id = "noactid"
                new_a_tag = unique_tag(a_tag, f"_act_{act_id}", seen)
                set_action_tag(act, new_a_tag)
                seen.add(new_a_tag)

                changed = True
                changes.append(f'Action tag on "{it_name}": "{a_tag}" -> "{new_a_tag}"')
            else:
                seen.add(a_tag)

    # ---------------------------------------------------------
    # PASS 3 (IMPORTANT): Remove colliding actor resource keys
    # ---------------------------------------------------------
    # This specifically fixes: actor.system.resources.maximumAttacks exists
    # while an item tag maximumAttacks also exists -> warning.
    res = get_resources_dict(actor)
    if isinstance(res, dict):
        # Remove only keys that are EXACTLY the same as an item tag.
        # That lets PF1 rebuild resources from items without duplicates.
        to_delete = [k for k in res.keys() if k in set(item_tags_in_actor)]
        if to_delete:
            for k in to_delete:
                del res[k]
                changes.append(f"resources: removed duplicate key '{k}' (will be rebuilt from item tag)")
            changed = True

    return changed, changes


def process_file(inp: Path, outp: Path, backup: bool, report_path: Path | None) -> int:
    outp.parent.mkdir(parents=True, exist_ok=True)

    if backup:
        bak = outp.with_suffix(outp.suffix + ".bak")
        shutil.copy2(inp, bak)

    patched_actors = 0
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

            if is_actor_doc(doc):
                changed, changes = fix_actor_identifiers_and_resources(doc)
                if changed:
                    patched_actors += 1
                    report_lines.append(
                        f"Line {line_no}: Actor {doc.get('name')!r} ({doc.get('_id')!r}) -> "
                        + "; ".join(changes)
                    )

            w.write(json.dumps(doc, ensure_ascii=False) + "\n")

    if report_path is not None:
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text("\n".join(report_lines), encoding="utf-8")

    return patched_actors


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Fix duplicate PF1 item identifiers in pf-eidolon-forms.db by making tags unique and removing colliding actor.system.resources keys."
    )
    ap.add_argument("--packages", type=Path, default=Path("packages"), help='Input folder (default: "packages")')
    ap.add_argument(
        "--packages-processed",
        type=Path,
        default=Path("packages_processed"),
        help='Output folder (default: "packages_processed")',
    )
    ap.add_argument("--backup", action="store_true", help="Create .bak next to the processed output file")
    ap.add_argument("--report", action="store_true", help="Write a report to packages_processed/_reports/")
    args = ap.parse_args()

    inp = args.packages / TARGET_FILE
    if not inp.exists():
        print(f"ERROR: not found: {inp}")
        return 2

    outp = args.packages_processed / TARGET_FILE
    if outp.exists():
        print(f"ERROR: output already exists (delete it first or change output folder): {outp}")
        return 2

    report_path = (args.packages_processed / "_reports" / f"{TARGET_FILE}.identifiers_report.txt") if args.report else None

    patched = process_file(inp, outp, backup=args.backup, report_path=report_path)
    print(f"Written: {outp}")
    print(f"Patched actors: {patched}")
    if report_path:
        print(f"Report: {report_path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())