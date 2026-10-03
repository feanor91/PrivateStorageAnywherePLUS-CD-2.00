# Changelog

## Crimson Desert build 2976 (2026-10-03)

No script change needed: `retarget_ay.py` re-derived every anchor on its own (ModeSwitch `0x640E20`, mode object `[parent+0x1188]`, layout `0x28/0x2A/0x32/0x39/0x5C`, mainChar `0x6D691E8`, InventoryInfoManager vtable `0x58BA0E8`). Built as `CD 2976.BB` (`4b4f7e3d…`).

### Added

- `MAJ-mod.bat` / `MAJ-mod.ps1`: one double-click rebuilds the mod for the installed game, backs up the previous ASI, installs the new one, and checks the INI setting. `-Test` builds the read-only dry run; `-Jeu <path>` overrides game detection.
- `MAJ.md`: the three-step procedure in plain French, for use without reading the technical documents.


## Crimson Desert build 2944 re-targeting (2026-09-20)

See [PORT-2944.md](PORT-2944.md). Script changes: tag-pool window widened, jump tables bounded per dispatch, mode/sub-mode taken from the BuildModeTagList arguments (a byte was inserted between them), layout re-emitted when it differs from AX, capture hook left disarmed when ModeSwitch's prologue changed, build tag from FileVersion. Tested: BB `930980fb…` — six panels, housing chests 1000, private storage 244/1000 with transfers.


## Crimson Desert build 2850 re-targeting (2026-09-15)

Not a new release package: a build script and its record. See [PORT-2850.md](PORT-2850.md) and [PORTING.md](PORTING.md).

### Added

- `tools/retarget_ay.py`: re-targets the tested AX release to a newer executable. Derives the mainChar global by access profile, ModeSwitch and the mode-object offset from the tag-builder route, ResolveActor by call-site majority, CampWareHouse by string xref, and the InventoryInfoManager vtable from RTTI; stops on any ambiguity.
- Runtime resolution of the InventoryInfoManager global by vtable identity (`--housing`), replacing the mod's SetInventory scan that build 2850 defeated.
- `--f4 dry|live`: reopens the private-storage path with the CampWareHouse key as a constant, first as a read-only dry run.
- `docs/logs-2850/`: the FATAL log on the AX release and the passing logs of each build.

### Changed on build 2850

- `PrivateStorageExpansions` must be an explicit value; with `-1` the base is written after the save has built the container and transfers are refused.

### Not carried over

- NameToKey is not re-anchored (key 8 assumed and validated at runtime).
- The capture hook does not arm (VirtualAlloc stage 3); the fallback route is used.


## Crimson Desert 2.00 compatibility release

Tested on Crimson Desert 2.00: all six panels opened and closed, both capacity behaviors were confirmed, and no crash or freeze occurred.

### Fixed

- Replaced three stale game addresses that caused the 1.18.2 build to crash on 2.00.
- Restored the early exit that makes `PrivateStorageSlots=0` safe while still allowing a previously changed value to be restored.
- Updated the mode-state layout for Crimson Desert 2.00.
- Corrected mode and sub-mode detection to use offsets `+0x28` and `+0x29`.
- Changed the patcher to derive game-side targets from executable structure rather than typed addresses.

### Added

- Deterministic build output for the tested 2.00 executable.
- Independent layout derivation and validation tools.
- Build-time ambiguity checks that stop instead of emitting an unsafe ASI.
- A guarded diagnostic probe for refused storage opens.
- Validation of hook bytes, section layout, exception data, stack arithmetic, field offsets, vararg marshalling, stale addresses, and memory writes.

### Capacity behavior

- F5–F9 housing chests remain fixed at 1,000 slots.
- F4 Private Storage is separately configurable with `PrivateStorageSlots`.
- `PrivateStorageSlots=0` restores/defaults to normal game capacity.
- `PrivateStorageSlots=1000` sets the total to exactly 1,000, including purchased expansions.

### Diagnostic build history

- **AT:** resolved moved addresses but read the wrong mode offset, producing safe `BLOCKED` results.
- **AU:** attempted a broad pointer search; it was unsafe, withdrawn, and never reused.
- **AV:** used guarded fixed candidates safely, but its secondary log labels were incorrect; retracted as diagnostic evidence.
- **AW:** captured the exact mode object passed by the game and proved the object route was already correct.
- **AX:** corrected the mode/sub-mode offsets. Five bytes differed from AW; this became the tested final release.

See [docs/FINDINGS-2.00.md](docs/FINDINGS-2.00.md) for the full evidence trail.
