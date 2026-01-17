import re
import shlex
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import List, Tuple

# -------------------- Metadata parsing (English only) --------------------

KEYVAL_RE = re.compile(
    r"^\s*#\s*(Name|Description|Usage)\s*:\s*(.+?)\s*$", re.IGNORECASE
)
SHEBANG_RE = re.compile(r"^\s*#!")
ENCODING_RE = re.compile(r"^\s*#.*coding[:=]\s*[-\w.]+", re.IGNORECASE)


@dataclass
class ScriptInfo:
    index: int
    path: Path
    filename: str
    name: str
    desc: str
    usage: str  # raw value after "Usage:" (may be args-only, or full command-ish)


def read_head_comment_block(script_path: Path, max_lines: int = 80) -> List[str]:
    """
    Read the initial comment block:
    - allow shebang and encoding line
    - allow blank lines
    - stop at first non-comment code line
    """
    lines: List[str] = []
    try:
        with script_path.open("r", encoding="utf-8", errors="ignore") as f:
            raw = []
            for _ in range(max_lines):
                line = f.readline()
                if not line:
                    break
                raw.append(line.rstrip("\n"))

        started = False
        for line in raw:
            if not started and (
                SHEBANG_RE.match(line) or ENCODING_RE.match(line) or line.strip() == ""
            ):
                lines.append(line)
                continue

            if line.strip().startswith("#") or line.strip() == "":
                started = True
                lines.append(line)
                continue

            # first real code line -> stop
            break
    except Exception:
        pass

    return lines


def parse_metadata(lines: List[str], fallback_name: str) -> Tuple[str, str, str]:
    """
    Support:
    A) Key-value style:
       # Name: ...
       # Description: ...
       # Usage: -r -n
       # Usage: python something.py -r -n
       # Usage: something.py -r -n

    B) Simple 3-line style:
       # <name>
       # <desc>
       # Usage: -r -n
    """
    name = ""
    desc = ""
    usage = ""

    # 1) parse key-value lines
    for line in lines:
        m = KEYVAL_RE.match(line)
        if not m:
            continue
        key = m.group(1).strip().lower()
        val = m.group(2).strip().replace("\ufeff", "")  # strip BOM if present
        if key == "name" and not name:
            name = val
        elif key == "description" and not desc:
            desc = val
        elif key == "usage" and not usage:
            usage = val

    # 2) fallback: take first two meaningful comment lines as name/desc
    if not name or not desc:
        pure: List[str] = []
        for line in lines:
            s = line.strip()
            if s.startswith("#"):
                txt = s.lstrip("#").strip()
                if not txt:
                    continue
                if KEYVAL_RE.match(line):
                    continue
                pure.append(txt)

        if not name and pure:
            name = pure[0]
        if not desc and len(pure) >= 2:
            desc = pure[1]

    if not name:
        name = fallback_name

    return name, desc, usage


# -------------------- Discovery --------------------


def discover_scripts(base_dir: Path, manager_filename: str) -> List[ScriptInfo]:
    """
    Non-recursive scan. Sort by filename ascending.
    Filter:
    - exclude manager itself
    - exclude __init__.py
    - exclude files starting with '_' (convention)
    """
    candidates = sorted(base_dir.glob("*.py"), key=lambda p: p.name.lower())

    items: List[ScriptInfo] = []
    for p in candidates:
        if p.name == manager_filename:
            continue
        if p.name == "__init__.py":
            continue
        if p.name.startswith("_"):
            continue

        head = read_head_comment_block(p)
        name, desc, usage = parse_metadata(head, fallback_name=p.stem)

        items.append(
            ScriptInfo(
                index=0,
                path=p.resolve(),
                filename=p.name,
                name=name,
                desc=desc,
                usage=usage,
            )
        )

    for i, s in enumerate(items, start=1):
        s.index = i

    return items


# -------------------- Command building (Usage as args source) --------------------


def _shlex_split_compat(s: str) -> List[str]:
    """
    Split usage text into tokens with shlex.
    On Windows, posix=False behaves better for quotes.
    """
    s = (s or "").strip().replace("\ufeff", "")
    if not s:
        return []
    return shlex.split(s, posix=(sys.platform != "win32"))


def build_command(script: ScriptInfo) -> List[str]:
    """
    Robust command builder:
    - ALWAYS run the selected script by absolute path (rename-safe)
    - Usage line is treated primarily as an argument source.
    - Supported Usage forms:
        Usage: -r -n
        Usage: python any_name.py -r -n
        Usage: any_name.py -r -n
        Usage: C:\\path\\any_name.py -r -n
    The "python"/"py" prefix and the first ".py" token (if present) are ignored.
    """
    tokens = _shlex_split_compat(script.usage)

    # Drop leading python launcher if present
    if tokens and tokens[0].lower() in ("python", "python3", "py"):
        tokens = tokens[1:]

    # If the first token looks like a python script path, drop it
    if tokens:
        t0 = tokens[0].strip().strip('"').strip("'")
        if t0.lower().endswith(".py"):
            tokens = tokens[1:]

    # Now tokens are args only
    return [sys.executable, str(script.path), *tokens]


# -------------------- UI --------------------


def _shorten(text: str, width: int = 92) -> str:
    text = (text or "").strip()
    if len(text) <= width:
        return text
    return text[: width - 1] + "…"


def print_menu(scripts: List[ScriptInfo], base_dir: Path):
    print("\n" + "=" * 72)
    print(f"Portable Script Manager | Dir: {base_dir}")
    print("=" * 72)

    if not scripts:
        print("No scripts found in this directory.")
        print("Tip: files starting with '_' are ignored.")
        print("-" * 72)
        print("Commands: r = rescan, q = quit")
        print("=" * 72)
        return

    for s in scripts:
        # first line: index + filename + name
        print(f"{s.index:>2}. {s.filename}  -  {s.name}")

        # second line: description if exists
        if s.desc.strip():
            print(f"    {_shorten(s.desc, 110)}")

    print("-" * 72)
    print("Enter number to run | r = rescan | q = quit")
    print("=" * 72)


def run_script(script: ScriptInfo):
    cmd = build_command(script)

    print(f"\n[RUN] {script.filename}")
    if script.usage.strip():
        print(f"Usage: {script.usage}")
    print(f"CWD:  {script.path.parent}")
    print(f"Cmd:  {' '.join(cmd)}")
    print("-" * 72)

    try:
        # Use script directory as CWD for relative file access
        subprocess.run(cmd, check=False, cwd=str(script.path.parent))
    except KeyboardInterrupt:
        print("\n[INTERRUPTED]")
    except Exception as e:
        print(f"\n[ERROR] {e}")
    finally:
        print("-" * 72)
        input("Press Enter to return to menu...")


# -------------------- Main loop --------------------


def main():
    base_dir = Path(__file__).resolve().parent
    manager_filename = Path(__file__).name

    scripts = discover_scripts(base_dir, manager_filename)

    while True:
        print_menu(scripts, base_dir)
        cmd = input("> ").strip()

        if cmd.lower() == "q":
            return

        if cmd.lower() == "r":
            scripts = discover_scripts(base_dir, manager_filename)
            continue

        if cmd.isdigit():
            idx = int(cmd)
            selected = next((s for s in scripts if s.index == idx), None)
            if not selected:
                print("Invalid number.")
                continue
            run_script(selected)
            continue

        print("Invalid input. Use a number, 'r', or 'q'.")


if __name__ == "__main__":
    main()
