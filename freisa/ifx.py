# Copyright 2026 FREISA contributors
# Apache License, Version 2.0, see LICENSE.md for details.
# SPDX-License-Identifier: Apache-2.0
#
# Info     : FPGA Interchange helpers shared by all steps: the exchange format between steps is a logical netlist
#            (`.netlist`) plus a physical netlist (`.phys`). Tools that speak another format convert at their own edges
#            with these functions (DCP via RapidWright; FASM via python-fpga-interchange). Also builds the per-part
#            device databases (`.device`, nextpnr `.bin`) on first use.
# Module   : ifx.py
# Author   : Christian Conti
# Contact  : christian.conti@mail.it
import os, pathlib, shutil, subprocess, sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
TP = ROOT / "third_party"
SCHEMA = TP / "fpga-interchange-schema" / "interchange"
PYIF = TP / "python-fpga-interchange"
DEVDIR = ROOT / "install" / "share" / "interchange"
IF_ENV = os.environ.get("FREISA_IF_ENV", "freisa-if")  # conda env with python-fpga-interchange (needs pycapnp 1.1.0)

def if_python():
    """Python of the conda env that runs python-fpga-interchange (it needs older packages than the main env)."""
    if os.environ.get("FREISA_IF_PYTHON"): return os.environ["FREISA_IF_PYTHON"]
    base = pathlib.Path(sys.executable).resolve().parents[1]
    for cand in (base.parent / IF_ENV / "bin" / "python", base / "envs" / IF_ENV / "bin" / "python"):
        if cand.exists(): return str(cand)
    return None

def jar():
    """Path of the RapidWright jar, found without importing the package: importing it starts a JVM in this process
    (blocks when called from an explore thread, and keeps the flow from exiting)."""
    import importlib.util
    spec = importlib.util.find_spec("rapidwright")
    return next(pathlib.Path(spec.submodule_search_locations[0]).glob("rapidwright-*-standalone-*.jar"))

def rw(ctx, cls, args, log, cwd=None):
    """Run a RapidWright command-line class."""
    ctx.sh(["java", f"-Xmx{ctx.cfg.get('java_mem', '16g')}", "-cp", jar(), f"com.xilinx.rapidwright.{cls}", *args], log, cwd=cwd or ctx.work)

def pyif(ctx, module, args, log, cwd=None):
    """Run a python-fpga-interchange module in its own environment."""
    py = if_python()
    if py is None: raise SystemExit(f"python-fpga-interchange environment '{IF_ENV}' not found: make install-interchange")
    ctx.sh([py, "-m", f"fpga_interchange.{module}", *args], log, cwd=cwd or ctx.work)

# ------------------------------------------------------------------ device databases (built once per part)
def device(ctx, patched=True):
    """Interchange device description of the target part. xc7 parts get the constraint and LUT patches nextpnr needs."""
    part = ctx.target["part"]; DEVDIR.mkdir(parents=True, exist_ok=True)
    raw = DEVDIR / f"{part}.device"
    if not raw.exists():
        rw(ctx, "interchange.DeviceResourcesExample", [part], "if_device", cwd=DEVDIR)
    if not patched or ctx.target.get("family") != "xc7": return raw
    out = DEVDIR / f"{part}_patched.device"
    if not out.exists():
        mid = DEVDIR / f"{part}_constraints.device"
        pyif(ctx, "patch", ["--schema_dir", SCHEMA, "--schema", "device", "--patch_path", "constraints", "--patch_format", "yaml",
                            raw, PYIF / "test_data" / "series7_constraints.yaml", mid], "if_patch_constraints")
        pyif(ctx, "patch", ["--schema_dir", SCHEMA, "--schema", "device", "--patch_path", "lutDefinitions", "--patch_format", "yaml",
                            mid, PYIF / "test_data" / "series7_luts.yaml", out], "if_patch_luts")
        mid.unlink()
    return out

def chipdb(ctx):
    """nextpnr-fpga_interchange chip database of the target part (xc7)."""
    part = ctx.target["part"]; out = DEVDIR / f"{part}.bin"
    if not out.exists():
        tmp = DEVDIR / f"{part}_db"; tmp.mkdir(exist_ok=True)
        pyif(ctx, "nextpnr_emit", ["--schema_dir", SCHEMA, "--output_dir", tmp, "--device_config",
                                   PYIF / "test_data" / "series7_device_config.yaml", "--device", device(ctx)], "if_chipdb_emit")
        ctx.sh([shutil.which("bbasm") or ROOT / "install" / "bin" / "bbasm", "-l", tmp / "chipdb.bba", out], "if_chipdb_bbasm")
        shutil.rmtree(tmp)
    return out

# ------------------------------------------------------------------ conversions at the edges
def from_dcp(ctx, dcp, name):
    """DCP -> <work>/<name>.netlist + <name>.phys (RapidWright); sets ctx.art['netlist'/'phys']."""
    d = ctx.work / f"{name}.dcp"
    if pathlib.Path(dcp).resolve() != d.resolve(): shutil.copy(dcp, d)
    edf = pathlib.Path(dcp).with_suffix(".edf")  # Vivado DCPs hold an encrypted netlist: RapidWright reads the EDIF next to it
    if edf.exists() and edf.resolve() != d.with_suffix(".edf").resolve(): shutil.copy(edf, d.with_suffix(".edf"))
    rw(ctx, "interchange.DcpToInterchange", [d], f"{name}_to_if")
    ctx.art.update(netlist=ctx.work / f"{name}.netlist", phys=ctx.work / f"{name}.phys")

def to_dcp(ctx, name, ooc=True):
    """ctx.art netlist + phys -> <work>/<name>.dcp (RapidWright); returns the path and sets ctx.art['dcp']."""
    xdc = ctx.work / f"{name}_empty.xdc"; xdc.write_text("")
    out = ctx.work / f"{name}.dcp"
    rw(ctx, "interchange.PhysicalNetlistToDcp", [ctx.art["netlist"], ctx.art["phys"], xdc, out] + (["--out_of_context"] if ooc else []),
       f"{name}_to_dcp")
    ctx.art["dcp"] = out
    return out

def pair(ctx, name):
    """Copy netlist + phys to <work>/<name>.netlist/.phys (tools that need both with the same root name)."""
    n, p = ctx.work / f"{name}.netlist", ctx.work / f"{name}.phys"
    for src, dst in ((ctx.art["netlist"], n), (ctx.art["phys"], p)):
        if pathlib.Path(src).resolve() != dst.resolve(): shutil.copy(src, dst)
    return n, p
