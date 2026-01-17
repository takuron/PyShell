# Name: 批量加文件夹前缀
# Description: 为文件名添加 [当前文件夹名] 前缀
# Usage: python add_folder_prefix.py

import argparse
import re
from collections import defaultdict
from pathlib import Path

BRACKET_PREFIX_RE = re.compile(r"^\[[^\]]+\]")


def prompt_yes_no(question: str, default: bool = False) -> bool:
    """
    交互式 y/n 提问
    default=False => (y/N)
    default=True  => (Y/n)
    """
    suffix = " (Y/n): " if default else " (y/N): "
    while True:
        ans = input(question + suffix).strip().lower()
        if ans == "":
            return default
        if ans in ("y", "yes"):
            return True
        if ans in ("n", "no"):
            return False
        print("请输入 y 或 n（或直接回车使用默认值）。")


def normalize_folder_input(raw: str) -> Path:
    raw = raw.strip().strip('"').strip("'")
    return Path(raw).expanduser().resolve()


def ask_folder_interactively() -> Path:
    """
    交互式获取文件夹路径：
    - 直接回车 = 当前路径
    - 支持拖拽文件夹到终端
    """
    while True:
        raw = input(
            "请输入要处理的文件夹路径（直接回车=当前路径，可拖拽文件夹到窗口）：\n> "
        ).strip()
        folder = Path.cwd().resolve() if raw == "" else normalize_folder_input(raw)

        if folder.exists() and folder.is_dir():
            return folder
        print(f"无效路径或不是文件夹：{folder}\n请重新输入。\n")


def iter_files(folder: Path, recursive: bool):
    if recursive:
        for p in folder.rglob("*"):
            if p.is_file():
                yield p
    else:
        for p in folder.iterdir():
            if p.is_file():
                yield p


def make_target_name(src: Path, replace_any_bracket_prefix: bool) -> str:
    """
    生成目标文件名：
    - 前缀为 [当前所在文件夹名]（不带空格）
    - replace_any_bracket_prefix=True 时：若源文件名以 [xxx] 开头，则替换成当前目录的 [dir]
      否则：直接在前面追加（但会由 skip 逻辑或冲突逻辑处理）
    """
    prefix = f"[{src.parent.name}]"
    name = src.name

    if replace_any_bracket_prefix:
        # 如果有 [xxx] 前缀，替换掉它
        if BRACKET_PREFIX_RE.match(name):
            name = BRACKET_PREFIX_RE.sub(prefix, name, count=1)
        else:
            name = prefix + name
    else:
        name = prefix + name

    return name


def build_rename_plan(
    folder: Path,
    recursive: bool,
    skip_if_prefixed: bool,
    replace_any_bracket_prefix: bool,
):
    """
    构建重命名计划（不执行），返回 (plan, stats)
    - plan: list[(src, dst)]
    - stats: dict 统计
    处理同目录下冲突：会在目标名后加 (1)(2)...
    """
    files = list(iter_files(folder, recursive))

    by_parent = defaultdict(list)
    for p in files:
        by_parent[p.parent].append(p)

    plan = []
    skipped = 0

    for parent, plist in by_parent.items():
        existing_names = {p.name for p in parent.iterdir() if p.is_file()}

        candidates = []
        for src in plist:
            current_prefix = f"[{src.parent.name}]"
            # 只有当“已经是当前目录前缀”才算“已加前缀”
            if skip_if_prefixed and src.name.startswith(current_prefix):
                skipped += 1
            else:
                candidates.append(src)

        source_names = {p.name for p in candidates}
        occupied = set(existing_names) - set(source_names)  # 源名会被迁走，视为释放
        allocated = set()

        for src in candidates:
            base_target_name = make_target_name(src, replace_any_bracket_prefix)

            target_name = base_target_name
            if target_name in occupied or target_name in allocated:
                # 冲突避让：在 stem 后追加 (1)(2)...
                tmp = Path(target_name)
                stem, suffix = tmp.stem, tmp.suffix
                i = 1
                while True:
                    candidate = f"{stem} ({i}){suffix}"
                    if candidate not in occupied and candidate not in allocated:
                        target_name = candidate
                        break
                    i += 1

            dst = src.with_name(target_name)
            plan.append((src, dst))
            allocated.add(target_name)
            occupied.add(target_name)

    stats = {"total_files": len(files), "skipped": skipped, "to_rename": len(plan)}
    return plan, stats


def print_preview(plan, stats, limit: int = 200):
    print("\n====== 预览（将要执行的重命名）======")
    print(f"扫描文件数：{stats['total_files']}")
    print(f"将重命名：  {stats['to_rename']}")
    print(f"将跳过：    {stats['skipped']}")
    print("====================================\n")

    if stats["to_rename"] == 0:
        print("没有需要重命名的文件。")
        return

    show_count = min(limit, len(plan))
    for i in range(show_count):
        src, dst = plan[i]
        print(f"{i + 1:>4}. {src}  ->  {dst}")

    if len(plan) > limit:
        print(f"\n（仅显示前 {limit} 条，共 {len(plan)} 条）")


def execute_plan(plan):
    for src, dst in plan:
        src.rename(dst)


# -------------------- 两种运行模式 --------------------


def run_batch_mode(args):
    """
    批处理模式：
    - 提供 folder => 全自动执行
    - 参数全部按命令行生效
    """
    folder = Path(args.folder).expanduser().resolve()
    if not (folder.exists() and folder.is_dir()):
        raise SystemExit(f"参数路径无效或不是文件夹：{folder}")

    plan, stats = build_rename_plan(
        folder=folder,
        recursive=args.recursive,
        skip_if_prefixed=not args.no_skip,
        replace_any_bracket_prefix=args.replace_bracket_prefix,
    )

    # 批处理：只有用户要求预览时才输出预览（或 dry-run）
    if args.preview or args.dry_run:
        print_preview(plan, stats, limit=args.preview_limit)

    if args.dry_run:
        print("\n[DRY-RUN] 仅预览：未执行任何重命名。")
        return

    if stats["to_rename"] == 0:
        print("\n[OK] 没有需要重命名的文件。")
        return

    execute_plan(plan)
    print(
        f"\n[OK] 已完成重命名：{stats['to_rename']} 个文件（跳过 {stats['skipped']} 个）。"
    )


def run_interactive_mode():
    """
    交互模式：
    - 未提供 folder => 忽略所有参数
    - 交互提问并在执行前强制预览 + 确认
    """
    print("进入交互模式：将忽略所有命令行参数，改为逐步提问。\n")

    folder = ask_folder_interactively()
    recursive = prompt_yes_no("是否递归处理子文件夹？", default=False)
    skip_prefixed = prompt_yes_no("是否跳过已带“当前目录前缀”的文件？", default=True)

    # 你提到建议很好：这里加一个可选项——如果文件名已存在 [xxx] 前缀，是否替换成当前目录名
    replace_any_bracket_prefix = prompt_yes_no(
        "若文件名已存在类似 [xxx] 的前缀，是否替换为当前文件夹名？", default=False
    )

    plan, stats = build_rename_plan(
        folder=folder,
        recursive=recursive,
        skip_if_prefixed=skip_prefixed,
        replace_any_bracket_prefix=replace_any_bracket_prefix,
    )

    # 交互模式：必须预览
    print_preview(plan, stats, limit=200)

    if stats["to_rename"] == 0:
        print("\n没有需要执行的重命名。")
        return

    if len(plan) > 200:
        if prompt_yes_no("预览条目较多，是否显示全部？", default=False):
            print_preview(plan, stats, limit=len(plan))

    if not prompt_yes_no("确认执行以上重命名操作？", default=False):
        print("\n已取消：未执行任何重命名。")
        return

    execute_plan(plan)
    print(
        f"\n[OK] 已完成重命名：{stats['to_rename']} 个文件（跳过 {stats['skipped']} 个）。"
    )


def main():
    parser = argparse.ArgumentParser(
        description="为文件名添加 [文件当前所处文件夹名] 前缀：提供路径=批处理；不提供路径=交互（忽略参数、预览确认后执行）"
    )

    # folder 可选：提供 => 批处理；不提供 => 交互
    parser.add_argument(
        "folder", nargs="?", help="可选：要处理的文件夹路径。提供=批处理；不提供=交互。"
    )

    # 批处理参数（交互模式会忽略）
    parser.add_argument(
        "-r",
        "--recursive",
        action="store_true",
        help="递归处理子文件夹（批处理模式有效）",
    )
    parser.add_argument(
        "-n", "--dry-run", action="store_true", help="仅预览不执行（批处理模式有效）"
    )
    parser.add_argument(
        "--no-skip",
        action="store_true",
        help="不跳过已带当前目录前缀的文件（批处理模式有效）",
    )
    parser.add_argument(
        "--preview", action="store_true", help="执行前输出预览（批处理模式有效）"
    )
    parser.add_argument(
        "--preview-limit", type=int, default=200, help="预览最多显示多少条（默认 200）"
    )

    # 可选增强：替换任意 [xxx] 前缀（批处理模式可用；交互模式会询问）
    parser.add_argument(
        "--replace-bracket-prefix",
        action="store_true",
        help="若文件名已有 [xxx] 前缀则替换成当前文件夹名（批处理模式有效）",
    )

    args = parser.parse_args()

    if args.folder:
        run_batch_mode(args)
    else:
        run_interactive_mode()


if __name__ == "__main__":
    main()
