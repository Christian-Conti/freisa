import yaml
from ..core import Backend, backend

@backend
class FusesocCore(Backend):
    """Resolve RTL file list from a FuseSoC .core target (no fusesoc needed)."""
    stage, name = "sources", "core"
    def run(self, ctx):
        core = yaml.safe_load(open(ctx.root / ctx.cfg["core"]))
        tgt = core["targets"][ctx.cfg.get("core_target", "default")]
        files = []
        for fs in tgt["filesets"]:
            for f in core["filesets"][fs]["files"]:
                path, ft = (f, core["filesets"][fs].get("file_type")) if isinstance(f, str) else (
                    list(f)[0], list(f.values())[0].get("file_type"))
                if ft in ("systemVerilogSource", "verilogSource", "vhdlSource"):
                    files.append((str(ctx.root / path), ft))
        ctx.art["rtl"] = files

@backend
class Files(Backend):
    """Plain glob list from the design file (`rtl: [...]`)."""
    stage, name = "sources", "files"
    def run(self, ctx):
        ext = {".v": "verilogSource", ".sv": "systemVerilogSource", ".vhd": "vhdlSource", ".vhdl": "vhdlSource"}
        fs = [f for g in ctx.cfg["rtl"] for f in sorted(ctx.root.glob(g))]
        if not fs: raise SystemExit(f"no RTL matched {ctx.cfg['rtl']} under {ctx.root}")
        ctx.art["rtl"] = [(str(f), ext[f.suffix]) for f in fs]

@backend
class NoNetlist(Backend):
    stage, name = "netlist", "none"
    def run(self, ctx): pass
