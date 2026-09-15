"""Re-target the tested Crimson Desert 2.00 release (build AX) to a newer game build.

The pristine v1.5.10 input is not required: this works on the released AX ASI
(SHA-256 C2B9848F...), whose bytes are pinned, and rewrites only the game-side
values that the newer executable moved. Every value is derived from the
executable by shape, never typed in, and the build stops on any ambiguity.

Scope of the AY build -- deliberately narrow, one testable change at a time:

  * fixed:    the startup FATAL. The mod's own MainCharGlobal scanner looks for
              a `mov rax,[rip] / mov r,[rax+0x48] / cmp byte [r+0xCxx]` idiom
              that no longer exists in the game. Its scan loop is replaced by a
              direct store of the build-time-derived global, so initialization
              completes and the three hooks install.
  * re-aimed: ModeSwitch (capture hook target), the mode object's offset inside
              its parent (+0x1158 -> derived), ResolveActor and CampWareHouse.
  * verified: the mode-state layout and the in-game/store mode values are
              unchanged; the build refuses to continue if they are not.
  * DISABLED: both capacity features. NameToKey and the InventoryInfo manager
              could not be re-anchored yet, and the container/info field
              offsets they write through have not been re-verified. The private
              slots wrapper exits before any game lookup and the housing slot
              patcher call returns 0, so AY writes nothing into inventory data.

With --housing (build AZ) the F5-F9 housing-chest expansion is restored:

  * The mod's inventory-manager resolver (which scanned SetInventory for a
    `mov r10,[rip+X]` the newer build no longer contains) is short-circuited
    at boot to point the mod's INVMGR slot at a zeroed qword in .psdata, so the
    worker thread starts and the on-open slot patch is enabled.
  * INVSCAN, a new routine called on every wrapper entry, locates the real
    InventoryInfoManager at runtime: it walks the game's block of manager
    pointer globals (derived from the bucket-idiom sites) and accepts the one
    whose object carries the RTTI vtable of pa::InventoryInfoManager (derived
    from the executable's RTTI). Exact identity, no guessing; every candidate
    is VirtualQuery-checked before it is read. Found -> the mod's original
    housing slot patcher (10 -> 1000, SEH-wrapped) runs unchanged.
  * The F4 (PrivateStorageSlots) path stays closed: NameToKey is still not
    re-anchored.

With --f4 dry (build BA) or --f4 live (build BB), on top of --housing, the
private-storage (F4, PrivateStorageSlots) path of the AX wrapper is reopened.
NameToKey is still not re-anchored; instead the InventoryKey of CampWareHouse
is taken as the constant 8 -- the value NameToKey returned on 2.00, and an
immediate that recurs in the 2850 consumers of the InventoryInfoManager
global. The wrapper's own bucket walk validates it: a key that is not in the
manager's table ends in `[PRIV] no entry` and nothing else happens. `dry`
keeps every guard and every `[PRIV]` log line but turns the two game-memory
stores (info base, container total) into nops, so the log shows what would be
written; `live` is the AX behaviour.

Usage:
    python tools/retarget_ay.py <AX.asi> <output.asi> <CrimsonDesert.exe> [--housing] [--f4 dry|live]
"""
from __future__ import annotations

import bisect
import collections
import hashlib
import re
import struct
import sys
import time
from pathlib import Path

import capstone
import pefile
from capstone import x86

import derive_modestate as D

AX_SHA256 = "c2b9848f33a3822532c563c31965f4dff74b0d02a369ae7626d3e43056c49840"

# What AX has baked in for 2.00. Each is located in the binary by its exact
# instruction bytes and must occur exactly once.
AX = dict(MODE_SWITCH=0x530E20, RESOLVE_ACTOR=0x75BF90, NAME_TO_KEY=0x1E37F50,
          CAMP_NAME=0x501C6B8, MODE_OBJ_DISP=0x1158)
AX_LAYOUT = dict(mode=0x28, submode=0x29, flags=0x31, subtypes=0x38, dirty=0x5B)
AX_MODES = dict(ingame_mode=4, store_sub=5)
MODE_SWITCH_PROLOGUE = bytes.fromhex("48895C2408" "4889742410" "48897C2418")

# ASI-side anchors (unchanged from the AX build; all verified by expected bytes)
GAME_BASE = 0x3D350          # qword: game image base
MAINCHAR_SLOT = 0x3D518      # qword: address of the game's root/mainChar global
INVMGR_PTR = 0x3D598         # qword: the mod's inventory-manager global
SCAN_ENTRY = 0x9AE9          # MainCharGlobal singleton scan: loop entry
SCAN_END = 0x9BB1            # ... up to the OK path
SCAN_OK = 0x9BCD             # `lea rcx,"MainCharGlobal: OK ..." ; sub rdx,rdi ; call log`
SLOT_PATCHER = 0x8720
OLD_TAG, NEW_TAG = b"CD 2.00.AX", b"CD 2850.AY"
TAG_AZ = b"CD 2850.AZ"
TAG_BA, TAG_BB = b"CD 2850.BA", b"CD 2850.BB"
CAMP_KEY = 8                 # InventoryKey::CampWareHouse (2.00 value; see --f4 in the docstring)
GAME_SIZE = 0x3D358          # qword: game SizeOfImage
LOGGER = 0x6DE0              # printf-style log sink
INV_SCAN_ENTRY = 0xA47E      # inventory-manager resolver: scan entry (fall-through only)
INV_SCAN_END = 0xA4B3        # ... up to the loop head
INV_FOUND_CONT = 0xA8A5      # where the resolver continues once [INVMGR_PTR] != 0
IAT_LOADLIBRARYA = 0x280F8
IAT_GETPROCADDRESS = 0x280F0
PD_RVA, PD_SIZE = 0x48000, 0x1000
PS_RVA, PS_SIZE = 0x46000, 0x2000
VQ_PTR = PD_RVA + 16         # qword: cached VirtualQuery (shared with the AW block)
PS_INVMGR = PD_RVA + 56      # qword: placeholder the resolver points INVMGR_PTR at (stays 0)
PS_INVFOUND = PD_RVA + 64    # dword: 0 searching, 1 found, 2 gave up
PS_INVTRIES = PD_RVA + 68    # dword: scan attempts
INV_MAX_TRIES = 1800         # worker calls the wrapper every 1 s until the first patch
INV_RTTI = b".?AVInventoryInfoManager@pa@@"


def fail(msg):
    raise SystemExit("STOP: " + msg)


T0 = time.time()


def note(msg):
    print(f"  [{time.time() - T0:6.0f}s] " + msg, flush=True)


# ---------------------------------------------------------------- game side
class Game:
    def __init__(self, path):
        self.path = Path(path)
        self.data = self.path.read_bytes()
        self.pe = pefile.PE(data=self.data, fast_load=True)
        self.pe.parse_data_directories(
            directories=[pefile.DIRECTORY_ENTRY["IMAGE_DIRECTORY_ENTRY_EXCEPTION"]])
        self.base = self.pe.OPTIONAL_HEADER.ImageBase
        self.code = [s for s in self.pe.sections if s.Characteristics & 0x20000000]
        # pefile copies a section on every get_data(); read each one once and
        # use the copy everywhere below (derive_modestate's own calls are few).
        self.blob = {s.VirtualAddress: s.get_data() for s in self.code}
        self.md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
        self.md.detail = True
        self.pdata = sorted((e.struct.BeginAddress, e.struct.EndAddress)
                            for e in self.pe.DIRECTORY_ENTRY_EXCEPTION)
        self._starts = [a for a, _ in self.pdata]
        self.size = self.pe.OPTIONAL_HEADER.SizeOfImage

    def sec_of(self, rva):
        for s in self.code:
            if s.VirtualAddress <= rva < s.VirtualAddress + len(self.blob[s.VirtualAddress]):
                return s
        return None

    def read(self, rva, n):
        s = self.sec_of(rva)
        if s is None:
            return b""
        o = rva - s.VirtualAddress
        return self.blob[s.VirtualAddress][o:o + n]

    def dis(self, rva, n):
        return list(self.md.disasm(self.read(rva, n), self.base + rva))

    def merged_function(self, rva):
        """The .pdata range holding rva, extended over chained entries that
        start exactly where the previous one ends."""
        k = bisect.bisect_right(self._starts, rva) - 1
        if k < 0 or not (self.pdata[k][0] <= rva < self.pdata[k][1]):
            return None
        lo, hi = self.pdata[k]
        while k + 1 < len(self.pdata) and self.pdata[k + 1][0] == hi:
            k += 1
            hi = self.pdata[k][1]
        return lo, hi

    def direct_callers(self, target):
        n = 0
        for s in self.code:
            b = self.blob[s.VirtualAddress]
            va = s.VirtualAddress
            p = 0
            while True:
                i = b.find(b"\xE8", p)
                if i < 0 or i + 5 > len(b):
                    break
                p = i + 1
                if va + i + 5 + struct.unpack_from("<i", b, i + 1)[0] == target:
                    n += 1
        return n

    def rip_loads(self):
        """Every `mov r64,[rip+X]` into a global, as {target: [(sec, off)]}."""
        out = collections.defaultdict(list)
        for s in self.code:
            b = self.blob[s.VirtualAddress]
            va = s.VirtualAddress
            j = 0
            while True:
                j = b.find(b"\x8B", j + 1)
                if j < 1 or j + 6 > len(b):
                    break
                if b[j - 1] & 0xF8 != 0x48 or b[j + 1] & 0xC7 != 0x05:
                    continue
                rel = struct.unpack_from("<i", b, j + 2)[0]
                t = va + j - 1 + 7 + rel
                if 0x1000 <= t < self.size and self.sec_of(t) is None:
                    out[t].append((s, j - 1))
        return out


def derive_mode_obj_disp(g: Game, ms):
    """ModeSwitch's single direct call site is `mov r64,[r64+disp32] ; call`:
    the disp32 is where the mode object lives inside its parent (+0x1158 on
    2.00). Read it from that one instruction; refuse anything else."""
    if ms % 8:
        fail(f"ModeSwitch {ms:#x} is not 8-byte aligned")
    if g.read(ms, 15) != MODE_SWITCH_PROLOGUE:
        fail("ModeSwitch prologue mismatch")
    sites = []
    for s in g.code:
        b = g.blob[s.VirtualAddress]
        va = s.VirtualAddress
        p = 0
        while True:
            i = b.find(b"\xE8", p)
            if i < 0 or i + 5 > len(b):
                break
            p = i + 1
            if va + i + 5 + struct.unpack_from("<i", b, i + 1)[0] == ms:
                sites.append(va + i)
    if len(sites) != 1:
        fail(f"ModeSwitch {ms:#x} has {len(sites)} direct callers, expected 1")
    pre = g.read(sites[0] - 7, 7)
    if not (pre[0] & 0xF8 == 0x48 and pre[1] == 0x8B and pre[2] >> 6 == 2 and pre[2] & 7 != 4):
        fail(f"instruction before the ModeSwitch call is not mov r64,[r64+disp32]: {pre.hex(' ')}")
    disp = struct.unpack_from("<i", pre, 3)[0]
    if not 0x800 <= disp <= 0x4000:
        fail(f"mode-object offset {disp:#x} is outside the plausible range")
    return disp


def derive_layout(g: Game):
    """derive_modestate's chain, but over merged .pdata ranges: on newer builds
    BuildModeTagList and ModeSwitch are split into chained unwind entries and
    the original owning_function() sees only the first piece."""
    tag_vas = D.find_tag_pool(g.pe, g.data)
    _, lea = D.find_tag_builder(g.pe, g.data, tag_vas)
    builder = g.merged_function(lea)
    if not builder:
        fail("BuildModeTagList has no .pdata entry")
    ingame = store = None
    for tbl, entries in D.read_jump_tables(g.pe, builder, tag_vas):
        labelled = [(i, t) for i, _, t in entries if t]
        for i, tags in labelled:
            if "ingame-global" in tags and i < 7 and ingame is None:
                ingame = i
        stores = [i for i, tags in labelled if "store" in tags]
        if stores:
            store = stores[0]            # the sub-mode table is read last
    ms = None
    for va in D.callers_of(g.pe, g.base + builder[0]):
        f = g.merged_function(va - g.base)
        if not f or f == builder:
            continue
        got = D.derive_from_modeswitch(g.pe, f, g.base + builder[0])
        if got[0] is not None and got[2] is not None:
            ms = (f, got)
            break
    if not ms:
        fail("could not identify ModeSwitch among BuildModeTagList's callers")
    (lo, hi), (mode, submode, flags, subtypes, dirty) = ms
    lay = dict(mode=mode, submode=submode, flags=flags, subtypes=subtypes, dirty=dirty)
    if None in lay.values():
        fail(f"layout incomplete: {lay}")
    for name, ok in D.INVARIANTS:
        if not ok(lay):
            fail(f"layout invariant failed: {name} ({lay})")
    return lo, lay, dict(ingame_mode=ingame, store_sub=store)


def derive_mainchar(g: Game, loads):
    """The root/mainChar global: hundreds of loads whose first dereference is
    dominated by +0x00 and includes +0x50/+0x90/+0xA0/+0xB0 -- the profile the
    2.00 global showed (886 loads: +0x00 273, +0xB0 173, +0x50 135, +0xA0 91,
    +0x90 64). Exactly one global may match."""
    need = {0x0, 0x50, 0x90, 0xA0, 0xB0}
    found = []
    for tgt, sites in loads.items():
        if len(sites) < 300:
            continue
        first = collections.Counter()
        for s, off in sites:
            ins = list(g.md.disasm(g.blob[s.VirtualAddress][off:off + 40], g.base + s.VirtualAddress + off))
            if not ins or not ins[0].operands:
                continue
            reg = ins[0].operands[0].reg
            for i in ins[1:7]:
                hit = None
                for op in i.operands:
                    if op.type == x86.X86_OP_MEM and op.mem.base == reg:
                        hit = op.mem.disp
                if hit is not None:
                    first[hit] += 1
                    break
                if i.mnemonic in ("call", "ret", "jmp"):
                    break
                if (i.operands and i.operands[0].type == x86.X86_OP_REG
                        and i.operands[0].reg == reg and i.mnemonic not in ("test", "cmp")):
                    break
        if need <= set(first) and first.most_common(1)[0][0] == 0x0:
            found.append((tgt, len(sites), first))
    if len(found) != 1:
        fail("mainChar global is not unique: "
             + str([(hex(t), n) for t, n, _ in found]))
    tgt, n, first = found[0]
    note(f"mainChar profile: {n} loads, first-deref "
         + " ".join(f"+{k:#x}:{v}" for k, v in first.most_common(8)))
    return tgt


def derive_resolve_actor(g: Game, loads, mainchar):
    """rcx = [[mainChar]] ; ... ; call X -- the handle resolver. The winner needs
    a clear majority and the body shape (`mov rbx,rdx`, a `[rcx+0x50]` load)."""
    votes = collections.Counter()
    for s, off in loads.get(mainchar, []):
        ins = list(g.md.disasm(g.blob[s.VirtualAddress][off:off + 80], g.base + s.VirtualAddress + off))
        if not ins:
            continue
        reg = ins[0].operands[0].reg
        deref = False
        for i in ins[1:11]:
            if (i.mnemonic == "mov" and len(i.operands) == 2
                    and i.operands[1].type == x86.X86_OP_MEM
                    and i.operands[1].mem.base == reg and i.operands[1].mem.disp == 0
                    and i.operands[1].mem.index == 0):
                deref = True
            if i.mnemonic == "call":
                if deref and i.op_str.startswith("0x"):
                    votes[int(i.op_str, 16) - g.base] += 1
                break
            if i.mnemonic in ("ret", "jmp"):
                break
    top = votes.most_common(2)
    if not top or top[0][1] < 50 or (len(top) > 1 and top[0][1] < 2 * top[1][1]):
        fail(f"ResolveActor has no clear majority: {[(hex(t), n) for t, n in top]}")
    ra = top[0][0]
    head = g.read(ra, 0x40)
    if b"\x48\x8B\xDA" not in head or not re.search(rb"\x48\x8B[\x41\x49\x51\x59\x61\x69\x71\x79]\x50", head):
        fail(f"ResolveActor {ra:#x} lacks the expected body (mov rbx,rdx / [rcx+0x50])")
    note(f"ResolveActor votes: {[(hex(t), n) for t, n in top]}")
    return ra


def derive_camp_name(g: Game):
    """The 'CampWareHouse' copy that code references with any REX-prefixed lea."""
    hits = {}
    for m in re.finditer(rb"CampWareHouse\x00", g.data):
        try:
            rva = g.pe.get_rva_from_offset(m.start())
        except Exception:
            continue
        n = 0
        for s in g.code:
            b = g.blob[s.VirtualAddress]
            va = s.VirtualAddress
            p = 0
            while True:
                j = b.find(b"\x8D", p)
                if j < 1 or j + 6 > len(b):
                    break
                p = j + 1
                if b[j - 1] & 0xF0 != 0x40 or b[j + 1] & 0xC7 != 0x05:
                    continue
                if va + j + 6 + struct.unpack_from("<i", b, j + 2)[0] == rva:
                    n += 1
        if n:
            hits[rva] = n
    if len(hits) != 1:
        fail(f"CampWareHouse: expected one referenced copy, got {hits}")
    return next(iter(hits))


def derive_inventory_vtable(g: Game):
    """pa::InventoryInfoManager's vtable, through its RTTI: TypeDescriptor ->
    the one CompleteObjectLocator at subobject offset 0 -> the vtable whose
    slot[-1] points at that locator. Exactly one of each."""
    i = g.data.find(INV_RTTI + b"\x00")
    if i < 0:
        fail("RTTI name for InventoryInfoManager not found")
    td = g.pe.get_rva_from_offset(i) - 0x10
    cols = []
    for m in re.finditer(re.escape(struct.pack("<I", td)), g.data):
        o = m.start() - 0xC
        if o < 0:
            continue
        sig, off, cd, ptd, pcd, pself = struct.unpack_from("<6I", g.data, o)
        try:
            r = g.pe.get_rva_from_offset(o)
        except Exception:
            continue
        if sig == 1 and off == 0 and pself == r:
            cols.append(r)
    if len(cols) != 1:
        fail(f"InventoryInfoManager: expected one CompleteObjectLocator, got {[hex(c) for c in cols]}")
    vts = [g.pe.get_rva_from_offset(m.start()) + 8
           for m in re.finditer(re.escape(struct.pack("<Q", g.base + cols[0])), g.data)]
    if len(vts) != 1:
        fail(f"InventoryInfoManager: expected one vtable, got {[hex(v) for v in vts]}")
    if g.sec_of(vts[0]) is not None:
        fail("InventoryInfoManager vtable lies in a code section")
    return vts[0]


def derive_manager_window(g: Game):
    """The block of StaticInfoManager pointer globals: every `mov r10,[rip+G]`
    that feeds the bucket idiom `shl r11,8 ; add r11,[r10+0x78]`. The scan
    window is that cluster padded by 64 KB each side, page-aligned, and must
    lie inside one non-code section of the image."""
    bucket = bytes.fromhex("49C1E3084D035A78")
    globs = collections.Counter()
    for s in g.code:
        b = g.blob[s.VirtualAddress]
        va = s.VirtualAddress
        p = 0
        while True:
            i = b.find(bucket, p)
            if i < 0:
                break
            p = i + 1
            w0 = max(0, i - 0x60)
            for m in re.finditer(rb"\x4C\x8B\x15(....)", b[w0:i], re.S):
                globs[va + w0 + m.start() + 7 + struct.unpack("<i", m.group(1))[0]] += 1
    if len(globs) < 10:
        fail(f"too few manager globals found ({len(globs)})")
    lo, hi = min(globs), max(globs) + 8
    lo = (lo - 0x10000) & ~0xFFF
    hi = (hi + 0x10000 + 0xFFF) & ~0xFFF
    sec = next((x for x in g.pe.sections if x.VirtualAddress <= lo
                and hi <= x.VirtualAddress + x.Misc_VirtualSize), None)
    if sec is None or sec.Characteristics & 0x20000000:
        fail(f"manager window {lo:#x}..{hi:#x} is not inside one data section")
    if hi - lo > 0x100000:
        fail(f"manager window too large ({hi - lo:#x})")
    note(f"manager globals: {len(globs)} distinct, {min(globs):#x}..{max(globs):#x}")
    return lo, hi


# ----------------------------------------------------------------- ASI side
class Asi:
    def __init__(self, path):
        self.img = bytearray(Path(path).read_bytes())
        self.pe = pefile.PE(data=bytes(self.img))
        self.base = self.pe.OPTIONAL_HEADER.ImageBase
        self.md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)

    def off(self, rva):
        return self.pe.get_offset_from_rva(rva)

    def rva(self, off):
        return self.pe.get_rva_from_offset(off)

    def expect(self, rva, hexs):
        want = bytes.fromhex(hexs)
        got = bytes(self.img[self.off(rva):self.off(rva) + len(want)])
        if got != want:
            fail(f"unexpected bytes at rva {rva:#x}: got {got.hex(' ')}, want {want.hex(' ')}")

    def replace_unique(self, old: bytes, new: bytes, label):
        hits = [m.start() for m in re.finditer(re.escape(old), bytes(self.img))]
        if len(hits) != 1:
            fail(f"{label}: expected exactly one occurrence, found {len(hits)}")
        self.img[hits[0]:hits[0] + len(new)] = new
        note(f"{label:<28} rva {self.rva(hits[0]):#07x}  {old.hex(' ')} -> {new.hex(' ')}")
        return self.rva(hits[0])

    def replace_all(self, old: bytes, new: bytes, label, count):
        hits = [m.start() for m in re.finditer(re.escape(old), bytes(self.img))]
        if len(hits) != count:
            fail(f"{label}: expected {count} occurrences, found {len(hits)} "
                 f"at {[hex(self.rva(h)) for h in hits]}")
        for h in hits:
            self.img[h:h + len(new)] = new
        note(f"{label:<28} x{count} at {[hex(self.rva(h)) for h in hits]}")

    def dis(self, rva, n):
        return list(self.md.disasm(bytes(self.img[self.off(rva):self.off(rva) + n]), self.base + rva))


def imm32(v):
    return struct.pack("<I", v)


class Emit:
    """Position-aware emitter with labels; every rip-relative displacement and
    every rel32 branch is resolved once the block's base rva is known."""

    def __init__(self, rva):
        self.rva = rva
        self.code = bytearray()
        self.fix = []
        self.lbl = {}

    def h(self, hexs):
        self.code.extend(bytes.fromhex(hexs))

    def raw(self, b):
        self.code.extend(b)

    def rip(self, hexs, target):          # opcode + rel32 to an absolute rva
        self.h(hexs)
        self.fix.append((len(self.code), target, 0))
        self.code.extend(bytes(4))

    def j(self, hexs, label):             # branch to a local label
        self.h(hexs)
        self.fix.append((len(self.code), label, 0))
        self.code.extend(bytes(4))

    def label(self, name):
        self.lbl[name] = len(self.code)

    def here(self):
        return self.rva + len(self.code)

    def align(self, n, fill=b"\xCC"):
        while len(self.code) % n:
            self.raw(fill)

    def finish(self):
        for at, tgt, tail in self.fix:
            dest = self.rva + self.lbl[tgt] if isinstance(tgt, str) else tgt
            self.code[at:at + 4] = struct.pack("<i", dest - (self.rva + at + 4 + tail))
        return bytes(self.code)


def apply_f4(asi, mode):
    """Reopen the AX private-storage path with a constant CampWareHouse key.

    The AX sequence is
        mov word [rsp+0x28],0xFFFF ; lea rcx,[base+"CampWareHouse"]
        lea rdx,[rsp+0x28] ; add rax,NAME_TO_KEY ; call rax ; test al,al ; je nf
        movzx eax,word [rsp+0x28]
    and becomes
        mov word [rsp+0x28],CAMP_KEY ; mov al,1 ; nop*18 ; test al,al ; je nf
    so everything downstream (bucket walk, entry, owner walk, containers,
    logging) runs unchanged. In `dry` mode the two stores into game memory
    are nops; the PS_DIRTY/BASE_ORIG/EXP_CACHE bookkeeping in .psdata stays."""
    old = bytes.fromhex("66C7442428FFFF") + b"\x48\x8D\x88"
    hits = [m.start() for m in re.finditer(re.escape(old), bytes(asi.img))]
    if len(hits) != 1:
        fail(f"F4 NameToKey block not unique: {len(hits)}")
    o = hits[0]
    # 7 (outKey) + 7 (lea rcx) + 5 (lea rdx) + 6 (add rax) + 2 (call rax) = 27 bytes, then test al,al
    if bytes(asi.img[o + 7 + 7:o + 7 + 7 + 5]) != bytes.fromhex("488D542428") or bytes(asi.img[o + 25:o + 29]) != bytes.fromhex("FFD084C0"):
        fail("F4 NameToKey block has an unexpected shape")
    new = bytes.fromhex("66C7442428") + struct.pack("<H", CAMP_KEY) + b"\xB0\x01" + b"\x90" * 18
    asi.img[o:o + 27] = new
    note(f"F4 key                       rva {asi.rva(o):#x}: NameToKey call -> key={CAMP_KEY}, al=1")
    if mode == "dry":
        asi.replace_unique(bytes.fromhex("66895148"), b"\x90" * 4, "F4 dry: info base store")
        asi.replace_unique(bytes.fromhex("66894114"), b"\x90" * 4, "F4 dry: container total store")
    else:
        for pat in ("66895148", "66894114"):
            if bytes(asi.img).count(bytes.fromhex(pat)) != 1:
                fail(f"F4 live: store {pat} not unique")
        note("F4 live: both game-memory stores active (AX behaviour)")


def apply_housing(asi, pb, pv, slot_call, inv_vt, win_lo, win_hi):
    """Build AZ: defer the inventory-manager resolution to a runtime vtable scan."""
    used = len(pb.rstrip(b"\x00"))
    free = (pv + used + 15) & ~15
    k32 = pb.find(b"kernel32.dll\x00")
    vq = pb.find(b"VirtualQuery\x00")
    if k32 < 0 or vq < 0:
        fail("kernel32/VirtualQuery strings not found in .pstext")
    k32, vq = pv + k32, pv + vq
    pd = next(s for s in asi.pe.sections if s.Name.startswith(b".psdata"))
    pdb = bytes(asi.img[pd.PointerToRawData:pd.PointerToRawData + pd.SizeOfRawData])
    if any(pdb[PS_INVMGR - PD_RVA:PS_INVTRIES - PD_RVA + 4]):
        fail(".psdata slots for AZ are not zero in the input")
    for iat in (IAT_LOADLIBRARYA, IAT_GETPROCADDRESS):
        if not any(pv + m.start() + 6 + struct.unpack("<i", m.group(1))[0] == iat
                   for m in re.finditer(rb"\xFF\x15(....)", pb, re.S)):
            fail(f"IAT slot {iat:#x} is not referenced from .pstext")
    asi.expect(INV_SCAN_ENTRY, "48 8b 1d 3b 30 03 00 45 33 e4")
    asi.expect(INV_FOUND_CONT, "4c 8b bc 24 e0 01 00 00 4c 8b a4 24 f8 01 00 00")
    hook_call = slot_call - 5                    # `call AW_HOOKINST` precedes `call SLOT_PATCHER`
    asi.expect(hook_call, "e8")
    hookinst = hook_call + 5 + struct.unpack_from("<i", bytes(asi.img), asi.off(hook_call) + 1)[0]
    if not PS_RVA <= hookinst < PS_RVA + PS_SIZE:
        fail(f"wrapper's first call does not target .pstext ({hookinst:#x})")

    e = Emit(free)
    strs = {}
    for name, txt in (
            ("boot", b"Inventory mgr ptr:   DEFERRED (AZ) - resolved at runtime by InventoryInfoManager vtable base+0x%llX"),
            ("found", b"  [INV] InventoryInfoManager global at base+0x%llX (object %llX, vtable match) - housing slot patch enabled"),
            ("giveup", b"  [INV] InventoryInfoManager NOT found after %u scans - housing slot patch stays off"),
            ("novq", b"  [INV] VirtualQuery unavailable - housing slot patch stays off")):
        strs[name] = e.here()
        e.raw(txt + b"\x00")
        e.align(4, b"\x00")
    e.align(16)

    # INVBOOT: entered by `jmp` from the resolver's scan entry, on the
    # resolver's own call-aligned stack. Points INVMGR_PTR at the zero
    # placeholder, logs, restores the two registers the continuation reads.
    e.label("boot")
    e.rip("4C 8D 3D", PS_INVMGR)                 # lea r15,[PS_INVMGR]
    e.rip("4C 89 3D", INVMGR_PTR)                # mov [INVMGR_PTR],r15
    e.rip("48 8D 0D", strs["boot"])              # lea rcx,[fmt]
    e.raw(b"\xBA" + imm32(inv_vt))               # mov edx,vtable rva
    e.rip("E8", LOGGER)
    e.rip("48 8B 35", GAME_BASE)                 # mov rsi,[GAME_BASE]
    e.rip("4C 8B 35", GAME_SIZE)                 # mov r14,[GAME_SIZE]
    e.rip("E9", INV_FOUND_CONT)                  # jmp -> resolver continues as "found"

    # rdbl(rcx) -> al: committed, readable page (a copy of the AW helper)
    e.align(16)
    e.label("rdbl")
    e.h("48 83 EC 58")
    e.h("48 85 C9"); e.j("0F 84", "rdblno")
    e.rip("48 8B 05", VQ_PTR); e.h("48 85 C0"); e.j("0F 84", "rdblno")
    e.h("48 8D 54 24 20"); e.h("41 B8 30 00 00 00"); e.h("FF D0")
    e.h("48 85 C0"); e.j("0F 84", "rdblno")
    e.h("8B 44 24 40"); e.h("3D 00 10 00 00"); e.j("0F 85", "rdblno")   # State == MEM_COMMIT
    e.h("8B 44 24 44"); e.h("A8 01"); e.j("0F 85", "rdblno")            # not PAGE_NOACCESS
    e.h("A9 00 01 00 00"); e.j("0F 85", "rdblno")                       # not PAGE_GUARD
    e.h("B0 01"); e.h("48 83 C4 58"); e.h("C3")
    e.label("rdblno")
    e.h("30 C0"); e.h("48 83 C4 58"); e.h("C3")

    # INVSCAN: called from the wrapper in place of `call AW_HOOKINST`; calls
    # it itself first so the capture hook still arms. Frame 0x58:
    # +0x20..+0x2F shadow, +0x30 p, +0x38 end, +0x40 wanted vptr, +0x48 object.
    e.align(16)
    e.label("scan")
    e.h("48 83 EC 58")
    e.rip("E8", hookinst)
    e.rip("8B 05", PS_INVFOUND); e.h("85 C0"); e.j("0F 85", "out")
    e.rip("48 8B 05", VQ_PTR); e.h("48 85 C0"); e.j("0F 85", "havevq")
    e.rip("48 8D 0D", k32); e.rip("FF 15", IAT_LOADLIBRARYA)
    e.h("48 85 C0"); e.j("0F 84", "novq")
    e.h("48 89 C1"); e.rip("48 8D 15", vq); e.rip("FF 15", IAT_GETPROCADDRESS)
    e.rip("48 89 05", VQ_PTR); e.h("48 85 C0"); e.j("0F 84", "novq")
    e.label("havevq")
    e.rip("8B 05", PS_INVTRIES); e.h("FF C0"); e.rip("89 05", PS_INVTRIES)
    e.raw(b"\x3D" + imm32(INV_MAX_TRIES)); e.j("0F 87", "giveup")
    e.rip("48 8B 05", GAME_BASE)
    e.raw(b"\x48\x8D\x88" + imm32(win_lo)); e.h("48 89 4C 24 30")       # p   = base+win_lo
    e.raw(b"\x48\x8D\x88" + imm32(win_hi)); e.h("48 89 4C 24 38")       # end = base+win_hi
    e.raw(b"\x48\x05" + imm32(inv_vt)); e.h("48 89 44 24 40")           # wanted vptr
    e.label("loop")
    e.h("48 8B 4C 24 30"); e.h("48 3B 4C 24 38"); e.j("0F 83", "notfound")
    e.h("48 8B 01")                                                     # rax = [p]
    e.h("48 3D 00 00 01 00"); e.j("0F 86", "next")                      # > 0x10000
    e.h("A8 07"); e.j("0F 85", "next")                                  # 8-aligned
    e.h("49 89 C3"); e.h("49 C1 EB 2F"); e.j("0F 85", "next")           # canonical user pointer
    e.h("48 89 44 24 48")
    e.h("48 89 C1"); e.j("E8", "rdbl"); e.h("84 C0"); e.j("0F 84", "next")
    e.h("48 8B 44 24 48"); e.h("48 8B 00")                              # rax = [obj] = vptr
    e.h("48 3B 44 24 40"); e.j("0F 85", "next")
    e.h("48 8B 4C 24 30"); e.rip("48 89 0D", INVMGR_PTR)                # INVMGR_PTR = p
    e.h("B8 01 00 00 00"); e.rip("89 05", PS_INVFOUND)
    e.h("48 8B 54 24 30"); e.rip("48 2B 15", GAME_BASE)                 # rdx = p - base
    e.h("4C 8B 44 24 48")                                               # r8 = object
    e.rip("48 8D 0D", strs["found"]); e.rip("E8", LOGGER)
    e.j("E9", "out")
    e.label("next")
    e.h("48 83 44 24 30 08"); e.j("E9", "loop")
    e.label("notfound")
    e.j("E9", "out")                             # flag stays 0: retried on the next wrapper entry
    e.label("giveup")
    e.h("B8 02 00 00 00"); e.rip("89 05", PS_INVFOUND)
    e.rip("8B 15", PS_INVTRIES); e.rip("48 8D 0D", strs["giveup"]); e.rip("E8", LOGGER)
    e.j("E9", "out")
    e.label("novq")
    e.h("B8 02 00 00 00"); e.rip("89 05", PS_INVFOUND)
    e.rip("48 8D 0D", strs["novq"]); e.rip("E8", LOGGER)
    e.label("out")
    e.h("48 83 C4 58"); e.h("C3")

    code = e.finish()
    if free + len(code) > PS_RVA + PS_SIZE:
        fail(f"AZ block overruns .pstext by {free + len(code) - (PS_RVA + PS_SIZE)} bytes")
    o = asi.off(free)
    if any(asi.img[o:o + len(code)]):
        fail("AZ block target area is not empty")
    asi.img[o:o + len(code)] = code
    boot, scan = free + e.lbl["boot"], free + e.lbl["scan"]
    note(f"AZ block                     rva {free:#x}: {len(code)} bytes (boot={boot:#x} scan={scan:#x} rdbl={free + e.lbl['rdbl']:#x})")

    o = asi.off(INV_SCAN_ENTRY)
    j = b"\xE9" + struct.pack("<i", boot - (INV_SCAN_ENTRY + 5))
    asi.img[o:o + (INV_SCAN_END - INV_SCAN_ENTRY)] = j + b"\xCC" * (INV_SCAN_END - INV_SCAN_ENTRY - 5)
    note(f"inventory-mgr resolver       rva {INV_SCAN_ENTRY:#x}: jmp INVBOOT (INVMGR_PTR -> .psdata placeholder)")
    o = asi.off(hook_call)
    asi.img[o:o + 5] = b"\xE8" + struct.pack("<i", scan - (hook_call + 5))
    note(f"wrapper entry                rva {hook_call:#x}: call AW_HOOKINST -> call INVSCAN; slot patcher call kept")


def main():
    housing = "--housing" in sys.argv
    f4 = None
    if "--f4" in sys.argv:
        f4 = sys.argv[sys.argv.index("--f4") + 1]
        if f4 not in ("dry", "live") or not housing:
            raise SystemExit(__doc__)
    args = [a for a in sys.argv[1:] if a not in ("--housing", "--f4", "dry", "live")]
    if len(args) != 3:
        raise SystemExit(__doc__)
    src, dst, exe = Path(args[0]), Path(args[1]), Path(args[2])

    asi = Asi(src)
    digest = hashlib.sha256(bytes(asi.img)).hexdigest()
    if digest != AX_SHA256:
        fail(f"input is not the tested AX release (sha256 {digest})")

    print("deriving from", exe)
    g = Game(exe)
    note(f"SizeOfImage {g.size:#x}")
    ms, layout, modes = derive_layout(g)
    mode_disp = derive_mode_obj_disp(g, ms)
    note(f"ModeSwitch game+{ms:#x}  mode object at [parent+{mode_disp:#x}]")
    note("layout " + " ".join(f"{k}={v:#x}" for k, v in layout.items())
         + f"  ingame={modes['ingame_mode']} store={modes['store_sub']}")
    if layout != AX_LAYOUT:
        fail(f"mode-state layout changed ({layout} vs AX {AX_LAYOUT}); "
             "AX's layout stub must be re-emitted, which this script does not do")
    if modes != AX_MODES:
        fail(f"mode values changed ({modes} vs AX {AX_MODES})")
    loads = g.rip_loads()
    mainchar = derive_mainchar(g, loads)
    note(f"mainChar global game+{mainchar:#x}")
    ra = derive_resolve_actor(g, loads, mainchar)
    note(f"ResolveActor game+{ra:#x}")
    camp = derive_camp_name(g)
    note(f"CampWareHouse game+{camp:#x}")
    if housing:
        inv_vt = derive_inventory_vtable(g)
        note(f"InventoryInfoManager vtable game+{inv_vt:#x}")
        win_lo, win_hi = derive_manager_window(g)
        note(f"manager scan window game+{win_lo:#x}..{win_hi:#x} ({(win_hi - win_lo) // 8} qwords)")

    print("\npatching")
    # (1) MainCharGlobal: replace the singleton scan loop with a direct store.
    #     Entered only by fall-through (verified: no branch targets inside),
    #     hands the OK path exactly the registers it expects: rdi = image base,
    #     rdx = absolute address (it prints rdx-rdi), r8d/r9d = the two
    #     cosmetic %d/%X fields of the message.
    asi.expect(SCAN_ENTRY, "4c 8b 35 68 38 03 00 45 33 c0 48 8b 3d 56 38 03 00")
    asi.expect(SCAN_OK, "48 8d 0d fc 2c 02 00 48 2b d7 e8")
    stub = bytearray()
    def riprel(opc, target):
        stub.extend(opc + struct.pack("<i", target - (SCAN_ENTRY + len(stub) + len(opc) + 4)))
    riprel(b"\x48\x8B\x3D", GAME_BASE)                 # mov rdi,[GAME_BASE]
    stub += b"\x48\x8D\x97" + imm32(mainchar)          # lea rdx,[rdi+mainchar]
    riprel(b"\x48\x89\x15", MAINCHAR_SLOT)             # mov [MAINCHAR_SLOT],rdx
    stub += b"\x45\x31\xC0" b"\x45\x31\xC9"            # xor r8d,r8d ; xor r9d,r9d
    riprel(b"\xE9", SCAN_OK)                           # jmp -> "MainCharGlobal: OK"
    if SCAN_ENTRY + len(stub) > SCAN_END:
        fail("mainChar stub does not fit")
    o = asi.off(SCAN_ENTRY)
    asi.img[o:o + (SCAN_END - SCAN_ENTRY)] = bytes(stub) + b"\xCC" * (SCAN_END - SCAN_ENTRY - len(stub))
    note(f"MainCharGlobal scanner       rva {SCAN_ENTRY:#x}: {len(stub)} bytes, direct store of game+{mainchar:#x}")

    # (2) game-side immediates baked into .pstext
    asi.replace_unique(b"\x48\x05" + imm32(AX["MODE_SWITCH"]), b"\x48\x05" + imm32(ms), "ModeSwitch (hook target)")
    asi.replace_unique(b"\x48\x05" + imm32(AX["MODE_SWITCH"] + 15), b"\x48\x05" + imm32(ms + 15), "ModeSwitch+0xF (stub return)")
    asi.replace_unique(b"\x48\x05" + imm32(AX["RESOLVE_ACTOR"]), b"\x48\x05" + imm32(ra), "ResolveActor")
    asi.replace_unique(b"\x48\x8D\x88" + imm32(AX["CAMP_NAME"]), b"\x48\x8D\x88" + imm32(camp), "CampWareHouse")
    # NameToKey is not re-anchored. The only path that reaches it is closed in
    # (4); the immediate is zeroed so nothing stale survives in the image.
    asi.replace_unique(b"\x48\x05" + imm32(AX["NAME_TO_KEY"]), b"\x48\x05" + imm32(0), "NameToKey (unreachable, zeroed)")

    # (3) the mode object's offset inside its parent: telemetry stub, the
    #     get_mode_obj fallback walk, and the six diagnostic candidates.
    old, new = imm32(AX["MODE_OBJ_DISP"]), imm32(mode_disp)
    asi.replace_all(b"\x48\x8B\x80" + old, b"\x48\x8B\x80" + new, "mode-obj disp mov rax,[rax+]", 2)
    asi.replace_all(b"\x48\x8D\x89" + old, b"\x48\x8D\x89" + new, "mode-obj disp lea rcx,[rcx+]", 6)
    asi.replace_all(b"\x48\x8B\x89" + old, b"\x48\x8B\x89" + new, "mode-obj disp mov rcx,[rcx+]", 6)

    # (4) capacity features off. The wrapper's first game-side step is the
    #     inventory-manager test; make it an unconditional exit to `done`, and
    #     make the housing slot patcher call return 0 instead of running.
    ps = next(s for s in asi.pe.sections if s.Name.startswith(b".pstext"))
    pb, pv = bytes(asi.img[ps.PointerToRawData:ps.PointerToRawData + ps.SizeOfRawData]), ps.VirtualAddress
    gate = None
    for m in re.finditer(rb"\x48\x8B\x05(....)\x48\x85\xC0\x0F\x84(....)", pb, re.S):
        if pv + m.start() + 7 + struct.unpack("<i", m.group(1))[0] == INVMGR_PTR:
            gate = pv + m.start() + 10          # the `je rel32`
            break
    if gate is None:
        fail("wrapper's inventory-manager gate not found")
    done = [pv + m.start() for m in re.finditer(rb"\x8B\x44\x24\x30\x48\x81\xC4\xC8\x00\x00\x00\xC3", pb)]
    if len(done) != 1:
        fail(f"wrapper epilogue not unique: {done}")
    if f4 is None:
        jmp = b"\x90\xE9" + struct.pack("<i", done[0] - (gate + 6))
        asi.img[asi.off(gate):asi.off(gate) + 6] = jmp
        note(f"capacity gate                rva {gate:#x}: je -> nop; jmp done ({done[0]:#x})")
    else:
        note(f"capacity gate                rva {gate:#x}: left open (--f4 {f4})")
    calls = [pv + m.start() for m in re.finditer(rb"\xE8(....)", pb, re.S)
             if pv + m.start() + 5 + struct.unpack("<i", m.group(1))[0] == SLOT_PATCHER]
    if len(calls) != 1:
        fail(f"housing slot patcher call not unique in the wrapper: {calls}")
    if not housing:
        asi.img[asi.off(calls[0]):asi.off(calls[0]) + 5] = b"\x31\xC0\x90\x90\x90"   # xor eax,eax
        note(f"housing slot patcher call    rva {calls[0]:#x}: call -> xor eax,eax (returns 0 entries)")
    else:
        apply_housing(asi, pb, pv, calls[0], inv_vt, win_lo, win_hi)
    if f4 is not None:
        apply_f4(asi, f4)

    # (5) build tag
    at = bytes(asi.img).find(OLD_TAG)
    if at < 0 or bytes(asi.img).find(OLD_TAG, at + 1) >= 0:
        fail("build tag not unique")
    tag = {None: TAG_AZ if housing else NEW_TAG, "dry": TAG_BA, "live": TAG_BB}[f4]
    asi.img[at:at + len(OLD_TAG)] = tag

    # ------------------------------------------------------------- checks
    print("\nchecks")
    img = bytes(asi.img)
    for name, val in (("MODE_SWITCH", AX["MODE_SWITCH"]), ("MODE_SWITCH+15", AX["MODE_SWITCH"] + 15),
                      ("RESOLVE_ACTOR", AX["RESOLVE_ACTOR"]), ("NAME_TO_KEY", AX["NAME_TO_KEY"]),
                      ("CAMP_NAME", AX["CAMP_NAME"])):
        if imm32(val) in img:
            fail(f"stale 2.00 immediate {name} survives")
    note("no stale 2.00 immediate survives")
    for name, val in (("MODE_SWITCH", ms), ("MODE_SWITCH+15", ms + 15), ("RESOLVE_ACTOR", ra),
                      ("CAMP_NAME", camp), ("mainChar", mainchar)):
        if name == "CAMP_NAME" and f4 is not None:
            continue                      # the lea is nopped out with the NameToKey call
        if imm32(val) not in img:
            fail(f"new value {name} missing from the image")
    note("all new values present")
    pe2 = pefile.PE(data=img)
    if [s.Name for s in pe2.sections] != [s.Name for s in asi.pe.sections] or len(img) != len(asi.pe.__data__):
        fail("PE shape changed")
    note(f"PE shape unchanged ({len(pe2.sections)} sections, {len(img)} bytes)")
    print("  mainChar stub as assembled:")
    for i in asi.dis(SCAN_ENTRY, len(stub)):
        print(f"     {i.address - asi.base:05X}  {i.bytes.hex(' '):<24} {i.mnemonic} {i.op_str}")
    cap = asi.dis(gate - 10, 16)
    print("  capacity gate as assembled:")
    for i in cap:
        print(f"     {i.address - asi.base:05X}  {i.bytes.hex(' '):<24} {i.mnemonic} {i.op_str}")

    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_bytes(img)
    print(f"\ninput_sha256={digest}")
    print(f"output_sha256={hashlib.sha256(img).hexdigest()}")
    print(f"wrote={dst} bytes={len(img)} tag={tag.decode()}")


if __name__ == "__main__":
    main()
