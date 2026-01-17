# Name: 寻找重复文件
# Description: 递归扫描整个目录，输出其中的重复文件。
# Usage: python find_dumpes.py

import argparse
import hashlib
import os
import sys
from datetime import datetime


def calculate_sha256(filepath: str):
    """
    计算文件的 SHA256 哈希值。
    使用分块读取，防止大文件占用过多内存。
    """
    sha256_hash = hashlib.sha256()
    try:
        with open(filepath, "rb") as f:
            # 每次读取 64KB 数据块
            for byte_block in iter(lambda: f.read(65536), b""):
                sha256_hash.update(byte_block)
        return sha256_hash.hexdigest()
    except (PermissionError, OSError):
        # 如果没有权限读取文件，返回 None
        return None


def find_duplicates(root_folder: str, recursive: bool = True):
    """
    遍历文件夹并查找重复文件（SHA256）
    - recursive=True: 递归扫描（默认）
    - recursive=False: 只扫描当前目录，不进入子目录

    返回:
      (files_count, dupe_print_groups, dupes_dict)
        files_count: 实际参与hash计算的文件数量
        dupe_print_groups: 与原逻辑一致的“发现重复组数”（每发现一次重复就+1）
        dupes_dict: {hash: [path1, path2, ...]} 仅包含出现重复的hash
    """
    # 用于存储已扫描文件的哈希值和路径 {hash: first_path}
    seen_hashes = {}
    # 用于收集重复文件的完整列表（写报告用）{hash: [all_paths]}
    dupes = {}

    print(f"\n正在扫描文件夹: {root_folder}")
    print("-" * 60)

    files_count = 0
    dupe_groups = 0

    # os.walk 自动处理递归子目录
    for dirpath, _, filenames in os.walk(root_folder):
        for filename in filenames:
            full_path = os.path.join(dirpath, filename)

            file_hash = calculate_sha256(full_path)

            if file_hash:
                if file_hash in seen_hashes:
                    # 发现重复！（保持原脚本的即时输出风格）
                    original_file = seen_hashes[file_hash]
                    dupe_groups += 1
                    print(f"\n[!] 发现重复文件组 #{dupe_groups}:")
                    print(f"    文件 1 (已存在): {original_file}")
                    print(f"    文件 2 (新发现): {full_path}")
                    print(f"    SHA256: {file_hash}")
                    print("-" * 30)

                    # 收集到 dupes（用于写报告）
                    if file_hash not in dupes:
                        dupes[file_hash] = [original_file, full_path]
                    else:
                        dupes[file_hash].append(full_path)
                else:
                    # 记录新文件的哈希和路径
                    seen_hashes[file_hash] = full_path

                files_count += 1

        # 非递归模式：只处理第一层目录
        if not recursive:
            break

    print("\n" + "=" * 60)
    print("扫描完成。")
    print(f"总共扫描文件数: {files_count}")
    print(f"发现重复组数: {dupe_groups}")
    print("=" * 60)

    return files_count, dupe_groups, dupes


def write_report(
    report_path: str, root_folder: str, files_count: int, dupe_groups: int, dupes: dict
):
    """
    将重复文件列表写入文本文件（UTF-8）
    """
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    unique_duplicate_hashes = len(dupes)

    lines = []
    lines.append("Duplicate Files Report (SHA256)")
    lines.append(f"Generated: {now}")
    lines.append(f"Root folder: {root_folder}")
    lines.append(f"Scanned files: {files_count}")
    lines.append(f"Duplicate prints (legacy counter): {dupe_groups}")
    lines.append(f"Duplicate hash groups: {unique_duplicate_hashes}")
    lines.append("=" * 80)

    for h, paths in dupes.items():
        # 去重并保持顺序（防止极端情况下重复加入同一路径）
        seen = set()
        unique_paths = []
        for p in paths:
            if p not in seen:
                unique_paths.append(p)
                seen.add(p)

        lines.append(f"\nSHA256: {h}")
        lines.append(f"Count: {len(unique_paths)}")
        for i, p in enumerate(unique_paths, start=1):
            lines.append(f"  {i}. {p}")

    # 确保输出目录存在（通常 report_path 在 root_folder 下）
    out_dir = os.path.dirname(report_path)
    if out_dir and not os.path.exists(out_dir):
        os.makedirs(out_dir, exist_ok=True)

    with open(report_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    print(f"\n[OK] 已写入重复文件报告: {report_path}")


def clean_input_path(p: str) -> str:
    """
    处理拖拽路径可能带引号的情况
    """
    if p is None:
        return ""
    return p.strip().replace('"', "").replace("'", "")


def interactive_main():
    """
    交互模式：与原脚本尽量保持一致
    """
    target_path = input("请输入要扫描的文件夹路径: ").strip()
    target_path = clean_input_path(target_path)

    if os.path.exists(target_path) and os.path.isdir(target_path):
        try:
            # 交互模式：逻辑不变（原本就是递归 os.walk，这里保持默认递归）
            find_duplicates(target_path, recursive=True)
        except KeyboardInterrupt:
            print("\n\n用户强制停止扫描。")
    else:
        print("\n错误: 路径不存在或不是一个有效的文件夹。")

    input("\n按 Enter (回车) 键退出程序...")


def automation_main(argv: list):
    """
    自动化模式：用于你的脚本调用体系（管理器/命令行传参）
    - 若发现重复：在输入目录根目录写报告（默认）
    """
    parser = argparse.ArgumentParser(
        description="Find duplicate files by SHA256. (interactive when no args)"
    )
    parser.add_argument("folder", help="Target folder to scan (default recursive).")
    parser.add_argument(
        "--non-recursive",
        action="store_true",
        help="Only scan the top-level folder (no subfolders).",
    )
    parser.add_argument(
        "--no-report",
        action="store_true",
        help="Do not write report file even if duplicates are found.",
    )
    parser.add_argument(
        "--report",
        default="duplicate_sha256_report.txt",
        help="Report file name or path. If relative, it will be created under the target folder.",
    )

    args = parser.parse_args(argv)

    folder = clean_input_path(args.folder)
    if not (os.path.exists(folder) and os.path.isdir(folder)):
        print("错误: 路径不存在或不是一个有效的文件夹。")
        sys.exit(2)

    recursive = not args.non_recursive

    try:
        files_count, dupe_groups, dupes = find_duplicates(folder, recursive=recursive)
    except KeyboardInterrupt:
        print("\n\n用户强制停止扫描。")
        sys.exit(130)

    # 若发现重复且允许写报告：写到输入目录根目录（或用户指定路径）
    if dupes and not args.no_report:
        report = args.report
        # 相对路径 -> 放到输入目录根目录
        if not os.path.isabs(report):
            report_path = os.path.join(folder, report)
        else:
            report_path = report

        try:
            write_report(report_path, folder, files_count, dupe_groups, dupes)
        except Exception as e:
            print(f"\n[WARN] 写入报告失败：{e}")
            # 自动化模式下写报告失败不强制退出，可按需要改为 sys.exit(1)


if __name__ == "__main__":
    # 无参数 -> 交互模式（逻辑保持原样）
    if len(sys.argv) == 1:
        interactive_main()
    else:
        # 有参数 -> 自动化模式（默认递归）
        automation_main(sys.argv[1:])
