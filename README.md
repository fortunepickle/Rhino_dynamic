# Rhino Dynamic Blocks (MVP)

This repository contains a RhinoPython utility that adds **dynamic block-like behavior** to Rhinoceros, inspired by AutoCAD dynamic blocks.

## What it does

The script lets you:

- Create a **parametric block family** (currently rectangle type with `Width` + `Height`).
- Insert instances with custom parameter values.
- Edit parameters of an existing instance.
- Sync all instances in a family while preserving per-instance parameter values.

Under the hood, the tool caches metadata in Rhino document strings and generates/reuses block definitions per parameter set.

## File

- `dynamic_blocks.py` — RhinoPython script.

## Install / Run in Rhino

1. Open Rhino (Rhino 7/8 supported).
2. Run `EditPythonScript`.
3. Open `dynamic_blocks.py`.
4. Run the script.
5. Choose an action from:
   - `CreateRectangleFamily`
   - `InsertInstance`
   - `EditInstance`
   - `SyncFamily`

## Notes

- This is an MVP utility, not a full compiled RhinoCommon plug-in.
- Script is kept compatible with Rhino's IronPython runtime (no `dataclasses` / postponed annotations).
- Currently supported family type: rectangle only.
- You can extend `build_geometry(...)` to support additional parametric types (doors, windows, furniture blocks, etc.).
