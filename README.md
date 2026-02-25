Below is the full English version of README

IMPORTANT:  The folder "modules_fixed_as_full" contains the fixed versions of the whole modules for Pathfinder 1e. You can just exchange the modules in your Foundry "data/modules" folder with the ones in "modules_fixed_as_full". 
            This way you don´t need to use the scripts at all. The scripts are only for those who want to fix the .db files on their own or want to understand how the fixing process works.

This project is a fix for the migration of the discontinued modules:

- "Pathfinder 1e - Bestiary" (https://foundryvtt.com/packages/pf1-bestiary/)
- "Pathfinder 1e Content" (https://foundryvtt.com/packages/pf-content/)

Those modules had actors that were migrated falsely, which caused errors when: opening them. The scripts in this project fix those errors by repairing the `.db` files of the modules.

---

# Folder Structure

The scripts expect the following structure:

```
project-folder/
│
├── modules_fixed_as_full/   ← Oroginal Modules with fixed .db files (just exchange in your Foundry "data/modules" folder) - IMPORTANT: you don´t need to usw the scripts. You can just use these modules in the folder directly. 
├── packages/                ← Original .db files
│
├── packages_processed/      ← Repaired files will be written here
│
├── repair_pf1_packages.py
├── repair_pf1_character_resistances_packages.py
├── repair_pf_eidolon_forms_identifiers.py
```

---

# Console Commands (Run in this Order)

Execute the following commands in your console:

1.

```
python .\repair_pf1_packages.py --only-npc --recursive --backup --reports
```

2.

```
python .\repair_pf1_character_resistances_packages.py --recursive --backup --reports
```

3.

```
python .\repair_pf_eidolon_forms_identifiers.py --backup --report
```

---

# Pathfinder 1e – Foundry DB Repair Scripts

This project provides Python scripts to repair improperly migrated Foundry VTT Pathfinder 1e compendium databases (`.db` files).

The scripts fix common issues that occur after migration (for example Foundry V10 → V11), including:

* Actors cannot be opened
* Errors such as `n.forEach is not a function`
* `Cannot read properties of undefined (reading 'forEach')`
* `Duplicate item identifier`
* UI errors caused by numeric values like `+2`

---

## Purpose of This Project

These scripts automatically repair:

* Broken trait arrays (`system.traits`)
* Invalid resistances (`eres`, `dr`, `dv`)
* Duplicate item identifiers (`system.tag`)
* Conflicts between items and actor resources
* Incorrectly stored numeric values such as `"+2"`

Original files can optionally be preserved as backups.

---

# Requirements

You need:

* Python 3.10 or newer
* Access to your Foundry module folders
* Ability to run console commands (copy and paste is sufficient)

---

# Usage

Open a PowerShell or terminal inside the project folder and execute the commands listed above in order.

---

## 1. NPC & Trait Repair

Fixes:

* `n.forEach is not a function`
* Broken traits (`di`, `dv`, `ci`, `languages`, etc.)
* String-to-array conversion issues

```
python .\repair_pf1_packages.py --only-npc --recursive --backup --reports
```

What happens:

* All `.db` files inside the `packages` folder
* Are scanned recursively
* Repaired automatically
* Written to `packages_processed`
* Backups are created
* A repair report is generated

---

## 2. Character / Resistance Repair

Fixes:

* `Cannot read properties of undefined (reading 'forEach')`
* Broken resistances (`eres`, `dr`, `dv`)
* Missing arrays
* Invalid numeric values such as `+2`

```
python .\repair_pf1_character_resistances_packages.py --recursive --backup --reports
```

Use this if:

* Animal Companions
* Eidolons
* Familiars
* Player-like actors

crash when opened.

---

## 3. Eidolon Forms – Duplicate Identifier Fix

Fixes:

* `Duplicate item identifier "maximumAttacks"`
* Conflicts between:

  * `system.tag`
  * `system.actions[*].tag`
  * `actor.system.resources`

Only applies to:

```
pf-eidolon-forms.db
```

```
python .\repair_pf_eidolon_forms_identifiers.py --backup --report
```

---

# Safety

* Original files are not overwritten
* `--backup` creates a `.bak` file
* All changes are documented
* No gameplay content is deleted
* Only structural data issues are corrected

---

# After Repair

1. Close Foundry
2. Copy the repaired `.db` file from `packages_processed`
3. Replace the original file in your module
4. Delete the older `.ldb` folder of the package if it exists (Foundry will not use the repaired `.db` if the `.ldb` version is present - here: https://foundryvtt.com/article/v11-leveldb-packs/?utm_source=chatgpt.com)
5. Restart Foundry

If Foundry has already migrated the pack to LevelDB:

* Re-import the pack
* Or remove the existing `.ldb` version so the `.db` file is used again

---

# Common Errors and Solutions

| Error Message                                             | Solution |
| --------------------------------------------------------- | -------- |
| `n.forEach is not a function`                             | Script 1 |
| `Cannot read properties of undefined (reading 'forEach')` | Script 2 |
| `Duplicate item identifier`                               | Script 3 |
| `The specified value "+2" cannot be parsed`               | Script 2 |

---

# Important Note

These scripts are specifically designed for:

* Foundry VTT
* Pathfinder 1e system
* Legacy NeDB `.db` compendium files

They are not intended for LevelDB `.ldb` files. Those need to migrated via the automaic Foundry migration process described here (https://foundryvtt.com/article/v11-leveldb-packs/?utm_source=chatgpt.com). Always keep backups before making changes.



