#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Edição determinística do system.img (ext4) via debugfs, preservando dono, modo, SELinux e capabilities.

Subcomandos:
  inventory IMG OUT.tsv
      Lista todo o FS: path, tipo, modo, uid, gid, tamanho, inode, alvo de symlink, xattrs.
  labelcheck INVENTORY.tsv FILE_CONTEXTS
      Recalcula o rótulo SELinux de cada arquivo pelo file_contexts (mesma regra do libselinux 4.4)
      e compara com o gravado na imagem — valida o rotulador antes de usá-lo em arquivos novos.
  plan INVENTORY.tsv FILE_CONTEXTS PLAN WORKDIR OUT.debugfs
      Converte o plano (rm/put/mkdir) em script do debugfs. Arquivos substituídos herdam o metadado
      do original (modo/uid/gid/todos os xattrs); arquivos novos recebem modo/uid/gid explícitos do
      plano e o rótulo do file_contexts.
  verify IMG PLAN
      Relê cada arquivo gravado (dump) e compara sha256 com a origem; confere que os removidos sumiram.
  diff OLD.tsv NEW.tsv
      Diferença de arquivos/metadados entre duas imagens.

Formato do PLAN (uma operação por linha, caminhos absolutos começando em /system):
  rm    /system/caminho                      (arquivo ou symlink)
  rmdir /system/caminho                      (diretório; remove recursivamente)
  mkdir /system/caminho MODO UID GID
  put   ORIGEM /system/caminho [MODO UID GID]
"""
import hashlib
import os
import re
import subprocess
import sys

DEBUGFS = os.environ.get("DEBUGFS", "debugfs")
COLS = ["path", "type", "mode", "uid", "gid", "size", "inode", "link", "xattrs"]


def run_debugfs(img, cmds, write=False):
    script = "\n".join(cmds) + "\n"
    args = [DEBUGFS] + (["-w"] if write else []) + ["-f", "-", img]
    p = subprocess.run(args, input=script, capture_output=True, text=True, errors="surrogateescape")
    if p.returncode != 0:
        sys.exit(f"debugfs falhou ({p.returncode}): {p.stderr[-2000:]}")
    return p.stdout, p.stderr


def split_by_cmd(out):
    """debugfs -f ecoa 'debugfs: CMD' antes de cada saída."""
    blocks, cur, key = [], [], None
    for line in out.splitlines():
        if line.startswith("debugfs: "):
            if key is not None:
                blocks.append((key, cur))
            key, cur = line[len("debugfs: "):], []
        else:
            cur.append(line)
    if key is not None:
        blocks.append((key, cur))
    return blocks


def q(path):
    if any(c in path for c in ' "\t\n'):
        sys.exit(f"caminho com espaço/aspas não suportado: {path!r}")
    return path


def fs(path):
    """/system/x -> /x (raiz do FS da partição system)."""
    if path == "/system":
        return "/"
    if not path.startswith("/system/"):
        sys.exit(f"caminho fora de /system: {path}")
    return path[len("/system"):]


def ftype(mode):
    return {0o040000: "d", 0o100000: "f", 0o120000: "l"}.get(mode & 0o170000, "?")


def inventory(img, out_tsv):
    entries, todo = {}, ["/"]
    entries["/"] = None
    while todo:
        out, _ = run_debugfs(img, [f"ls -p {q(d)}" for d in todo])
        nxt = []
        for cmd, lines in split_by_cmd(out):
            d = cmd.split(" ", 2)[2]
            for l in lines:
                m = re.match(r"^/(\d+)/(\d+)/(\d+)/(\d+)/(.*)/(\d*)/$", l)
                if not m:
                    continue
                ino, mode, uid, gid, name, size = m.groups()
                if name in (".", ".."):
                    continue
                p = (d.rstrip("/") + "/" + name)
                mode = int(mode, 8)
                entries[p] = dict(path=p, type=ftype(mode), mode=f"{mode & 0o7777:04o}", uid=uid, gid=gid,
                                  size=size or "0", inode=ino, link="", xattrs="")
                if ftype(mode) == "d":
                    nxt.append(p)
        todo = nxt
    del entries["/"]
    root_out, _ = run_debugfs(img, ["stat /"])
    paths = sorted(entries)
    # xattrs
    out, _ = run_debugfs(img, [f"ea_list {q(p)}" for p in paths] + ["ea_list /"])
    for cmd, lines in split_by_cmd(out):
        p = cmd.split(" ", 1)[1]
        xs = [l.strip() for l in lines if l.startswith("  ")]
        if p in entries:
            entries[p]["xattrs"] = " | ".join(xs)
        elif p == "/":
            root_x = " | ".join(xs)
    # symlinks
    links = [p for p in paths if entries[p]["type"] == "l"]
    if links:
        out, _ = run_debugfs(img, [f"stat {q(p)}" for p in links])
        for cmd, lines in split_by_cmd(out):
            p = cmd.split(" ", 1)[1]
            for l in lines:
                m = re.match(r'^Fast link dest: "(.*)"$', l)
                if m:
                    entries[p]["link"] = m.group(1)
    with open(out_tsv, "w") as f:
        f.write("\t".join(COLS) + "\n")
        mm = re.search(r"Mode:\s+(\d+)", root_out)
        mu = re.search(r"User:\s+(\d+)\s+Group:\s+(\d+)", root_out)
        f.write("\t".join(["/system", "d", mm.group(1)[-4:].zfill(4), mu.group(1), mu.group(2), "0", "2", "", root_x]) + "\n")
        for p in paths:
            e = entries[p]
            e = dict(e, path="/system" + p)
            f.write("\t".join(e[c] for c in COLS) + "\n")
    print(f"{out_tsv}: {len(paths) + 1} entradas")


def load_inv(tsv):
    rows = {}
    with open(tsv) as f:
        hdr = f.readline().rstrip("\n").split("\t")
        for l in f:
            r = dict(zip(hdr, l.rstrip("\n").split("\t")))
            rows[r["path"]] = r
    return rows


def selinux_of(xattrs):
    m = re.search(r'security\.selinux \(\d+\) = "([^"\\]*)(\\000)?"', xattrs)
    return m.group(1) if m else None


class FileContexts:
    """Mesma semântica do label_file.c do libselinux do Android 4.4: specs com metacaractere de
    regex primeiro, caminhos literais depois; procura de trás pra frente; 1a que casa vence."""

    META = set(".^$?*+|[({")

    def __init__(self, path):
        specs = []
        for l in open(path):
            l = l.split("#", 1)[0].strip()
            if not l:
                continue
            parts = l.split()
            if len(parts) == 2:
                regex, ftype_, ctx = parts[0], None, parts[1]
            else:
                regex, ftype_, ctx = parts[0], parts[1], parts[2]
            meta = any(c in self.META for c in regex.replace("\\.", ""))
            specs.append((meta, re.compile("^" + regex + "$"), ftype_, ctx))
        self.specs = [s for s in specs if s[0]] + [s for s in specs if not s[0]]

    def lookup(self, path, t):
        tmap = {"f": "--", "d": "-d", "l": "-l"}
        for meta, rx, ft, ctx in reversed(self.specs):
            if ft and ft != tmap.get(t):
                continue
            if rx.match(path):
                return None if ctx == "<<none>>" else ctx
        return None


def labelcheck(inv_tsv, fc_path):
    fc = FileContexts(fc_path)
    inv = load_inv(inv_tsv)
    bad = 0
    for p, r in sorted(inv.items()):
        want = fc.lookup(p, r["type"])
        have = selinux_of(r["xattrs"])
        if want != have:
            bad += 1
            if bad <= 20:
                print(f"DIVERGE {p}: imagem={have} file_contexts={want}")
    print(f"labelcheck: {len(inv)} entradas, {bad} divergências")
    return 1 if bad else 0


def parse_plan(path):
    ops = []
    for n, l in enumerate(open(path), 1):
        l = l.split("#", 1)[0].strip()
        if not l:
            continue
        a = l.split()
        ops.append((n, a))
    return ops


def plan(inv_tsv, fc_path, plan_path, workdir, out_script):
    fc = FileContexts(fc_path)
    inv = load_inv(inv_tsv)
    os.makedirs(os.path.join(workdir, "xattr"), exist_ok=True)
    cmds, live = [], dict(inv)
    epoch = int(os.environ["SOURCE_DATE_EPOCH"])

    def label_file(ctx):
        fn = os.path.join(workdir, "xattr", re.sub(r"[^A-Za-z0-9_]", "_", ctx) + ".bin")
        with open(fn, "wb") as f:
            f.write(ctx.encode() + b"\0")  # make_ext4fs grava o rótulo com NUL final
        return fn

    def set_meta(p, mode, uid, gid, t):
        tbits = {"f": 0o100000, "d": 0o040000}[t]
        cmds.extend([
            f"sif {q(fs(p))} mode 0{tbits | int(mode, 8):o}",
            f"sif {q(fs(p))} uid {uid}", f"sif {q(fs(p))} gid {gid}",
            f"sif {q(fs(p))} uid_high 0", f"sif {q(fs(p))} gid_high 0",
        ])
        for fld in ("atime", "mtime", "ctime", "crtime"):
            cmds.append(f"sif {q(fs(p))} {fld} {epoch}")

    def set_xattrs_from(p, src_path):
        # copia todos os xattrs do original (rótulo + capabilities) a partir da imagem original
        x = inv[src_path]["xattrs"]
        for name in re.findall(r"(security\.[a-z]+) \(\d+\)", x):
            fn = os.path.join(workdir, "xattr", "orig_" + re.sub(r"[^A-Za-z0-9]", "_", src_path + name) + ".bin")
            cmds.append(f"#XATTR_FROM_ORIG {src_path} {name} {fn}")
            cmds.append(f"ea_set -f {fn} {q(fs(p))} {name}")

    def ensure_parent(p):
        parent = os.path.dirname(p)
        if parent not in live:
            sys.exit(f"diretório {parent} não existe (adicione 'mkdir' no plano)")

    for n, a in parse_plan(plan_path):
        op = a[0]
        if op == "rm":
            p = a[1]
            if p not in live:
                sys.exit(f"plano:{n}: rm de algo inexistente {p}")
            if live[p]["type"] == "d":
                sys.exit(f"plano:{n}: {p} é diretório (use rmdir)")
            cmds.append(f"rm {q(fs(p))}")
            del live[p]
        elif op == "rmdir":
            p = a[1]
            kids = sorted((k for k in live if k.startswith(p + "/")), key=lambda k: -k.count("/"))
            for k in kids:
                cmds.append(f"rmdir {q(fs(k))}" if live[k]["type"] == "d" else f"rm {q(fs(k))}")
                del live[k]
            cmds.append(f"rmdir {q(fs(p))}")
            del live[p]
        elif op == "mkdir":
            p, mode, uid, gid = a[1:5]
            ensure_parent(p)
            if p in live:
                continue
            cmds.append(f"mkdir {q(fs(p))}")
            set_meta(p, mode, uid, gid, "d")
            ctx = fc.lookup(p, "d")
            cmds.append(f"ea_set -f {label_file(ctx)} {q(fs(p))} security.selinux")
            live[p] = dict(path=p, type="d")
        elif op == "put":
            src, p = a[1], a[2]
            if not os.path.isfile(src):
                sys.exit(f"plano:{n}: origem inexistente {src}")
            ensure_parent(p)
            orig = inv.get(p) if p in live else None
            if p in live:
                if live[p]["type"] != "f":
                    sys.exit(f"plano:{n}: {p} existe e não é arquivo regular")
                cmds.append(f"rm {q(fs(p))}")
            cmds.append(f"write {q(os.path.abspath(src))} {q(fs(p))}")
            if len(a) >= 6:
                mode, uid, gid = a[3:6]
            elif orig:
                mode, uid, gid = orig["mode"], orig["uid"], orig["gid"]
            else:
                sys.exit(f"plano:{n}: arquivo novo {p} precisa de MODO UID GID")
            set_meta(p, mode, uid, gid, "f")
            if orig and orig.get("xattrs"):
                set_xattrs_from(p, p)
            else:
                ctx = fc.lookup(p, "f")
                cmds.append(f"ea_set -f {label_file(ctx)} {q(fs(p))} security.selinux")
            live[p] = dict(path=p, type="f")
        else:
            sys.exit(f"plano:{n}: operação desconhecida {op}")
    with open(out_script, "w") as f:
        f.write("\n".join(cmds) + "\n")
    print(f"{out_script}: {len(cmds)} comandos")


def extract_orig_xattrs(orig_img, script):
    """Resolve as linhas #XATTR_FROM_ORIG gravando o valor bruto do xattr original em arquivo."""
    need = [l.split()[1:] for l in open(script) if l.startswith("#XATTR_FROM_ORIG ")]
    if need:
        run_debugfs(orig_img, [f"ea_get -f {fn} {q(fs(p))} {name}" for p, name, fn in need])
        for p, name, fn in need:
            if not os.path.exists(fn):
                sys.exit(f"falhou ao ler xattr {name} de {p}")


def verify(img, plan_path):
    ops = parse_plan(plan_path)
    puts = [(a[1], a[2]) for _, a in ops if a[0] == "put"]
    rms = [a[1] for _, a in ops if a[0] in ("rm", "rmdir")]
    tmpd = os.environ.get("TMPDIR_VERIFY", "/tmp")
    cmds = []
    for i, (src, p) in enumerate(puts):
        cmds.append(f"dump {q(fs(p))} {tmpd}/v{i}")
    run_debugfs(img, cmds)
    bad = 0
    for i, (src, p) in enumerate(puts):
        h1 = hashlib.sha256(open(src, "rb").read()).hexdigest()
        h2 = hashlib.sha256(open(f"{tmpd}/v{i}", "rb").read()).hexdigest() if os.path.exists(f"{tmpd}/v{i}") else "AUSENTE"
        os.path.exists(f"{tmpd}/v{i}") and os.unlink(f"{tmpd}/v{i}")
        if h1 != h2:
            bad += 1
            print(f"CONTEÚDO DIVERGE {p}")
    out, _ = run_debugfs(img, [f"stat {q(fs(p))}" for p in rms])
    for cmd, lines in split_by_cmd(out):
        if not any("File not found" in l for l in lines) and lines:
            # stat imprime o inode se ainda existir
            if any(l.startswith("Inode:") for l in lines):
                bad += 1
                print(f"AINDA EXISTE: {cmd}")
    print(f"verify: {len(puts)} gravados conferidos por sha256, {len(rms)} remoções, {bad} problemas")
    return 1 if bad else 0


def diff(old_tsv, new_tsv):
    a, b = load_inv(old_tsv), load_inv(new_tsv)
    keys = ["type", "mode", "uid", "gid", "size", "inode", "link", "xattrs"]
    for p in sorted(set(a) | set(b)):
        if p not in b:
            print(f"-\t{p}\t{a[p]['size']}")
        elif p not in a:
            r = b[p]
            print(f"+\t{p}\t{r['size']}\t{r['mode']} {r['uid']}:{r['gid']}\t{selinux_of(r['xattrs'])}")
        else:
            ch = [k for k in keys if a[p][k] != b[p][k] and not (k == "size" and a[p]["type"] == "d")]
            if ch and ch != ["inode"]:
                r = b[p]
                print(f"M\t{p}\t{r['size']}\t{r['mode']} {r['uid']}:{r['gid']}\t{selinux_of(r['xattrs'])}\t({','.join(ch)})")
            elif ch == ["inode"]:
                print(f"M\t{p}\t{b[p]['size']}\t(substituído, mesmo metadado)")


if __name__ == "__main__":
    a = sys.argv
    if len(a) < 2:
        sys.exit(__doc__)
    c = a[1]
    if c == "inventory":
        inventory(a[2], a[3])
    elif c == "labelcheck":
        sys.exit(labelcheck(a[2], a[3]))
    elif c == "plan":
        plan(a[2], a[3], a[4], a[5], a[6])
    elif c == "xattrs":
        extract_orig_xattrs(a[2], a[3])
    elif c == "verify":
        sys.exit(verify(a[2], a[3]))
    elif c == "diff":
        diff(a[2], a[3])
    else:
        sys.exit(__doc__)
