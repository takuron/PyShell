# Name: 寻找重复文件 (优化版)
# Description: 递归扫描目录，先按文件大小筛选，再按SHA256查找重复文件。
# Usage: python find_dumpes.py

import argparse
import hashlib
import os
import sys
from collections import defaultdict
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
    两阶段查找重复文件：
    1. 遍历所有文件，按【文件大小】分组。
    2. 仅对【大小相同】的文件组计算 SHA256，确认是否内容重复。
    """
    # 阶段 1: 按大小分组
    # 结构: { size_in_bytes: [path1, path2, ...] }
    files_by_size = defaultdict(list)
    total_files_scanned = 0

    print(f"\n[阶段 1/2] 正在构建文件列表: {root_folder}")
    print("-" * 60)

    # os.walk 遍历
    for dirpath, _, filenames in os.walk(root_folder):
        for filename in filenames:
            full_path = os.path.join(dirpath, filename)
            try:
                # 获取文件大小
                file_size = os.path.getsize(full_path)
                files_by_size[file_size].append(full_path)
                total_files_scanned += 1
            except (OSError, PermissionError):
                continue

        # 非递归模式：只处理第一层
        if not recursive:
            break

    print(f"扫描结束。共发现 {total_files_scanned} 个文件。")
    print(f"正在筛选可能重复的文件（相同大小）...")

    # 阶段 2: 计算哈希并比对
    # dupes 结构: { hash: [path1, path2, ...] }
    dupes = {}
    dupe_groups_count = 0  # 记录发现的重复组数

    # 筛选出潜在的重复者：只有当某个大小的文件数量 > 1 时，才需要计算哈希
    potential_groups = {
        s: paths for s, paths in files_by_size.items() if len(paths) > 1
    }
    total_potential_groups = len(potential_groups)

    if total_potential_groups == 0:
        print("\n没有发现大小相同的文件，因此没有重复文件。")
        return total_files_scanned, 0, {}

    print(f"\n[阶段 2/2] 正在深度比对 {total_potential_groups} 组大小相同的文件...")
    print("-" * 60)

    for file_size, paths in potential_groups.items():
        # 在当前这个大小组内，按哈希分组
        # { hash: [path1, path2...] }
        hashes_in_current_size = defaultdict(list)

        for path in paths:
            file_hash = calculate_sha256(path)
            if file_hash:
                hashes_in_current_size[file_hash].append(path)

        # 检查该大小组内，是否有哈希碰撞
        for file_hash, file_list in hashes_in_current_size.items():
            if len(file_list) > 1:
                # 确认发现重复！
                dupe_groups_count += 1
                dupes[file_hash] = file_list

                # 实时输出
                print(
                    f"\n[!] 发现重复组 #{dupe_groups_count} (文件大小: {file_size} bytes):"
                )
                print(f"    SHA256: {file_hash}")
                for i, p in enumerate(file_list, 1):
                    print(f"    文件 {i}: {p}")
                print("-" * 30)

    print("\n" + "=" * 60)
    print("扫描完成。")
    print(f"总文件数: {total_files_scanned}")
    print(f"需要哈希计算的大小组: {total_potential_groups}")
    print(f"确认重复的哈希组数: {len(dupes)}")
    print("=" * 60)

    return total_files_scanned, dupe_groups_count, dupes


def write_report(
    report_path: str, root_folder: str, files_count: int, dupe_groups: int, dupes: dict
):
    """
    将重复文件列表写入文本文件（UTF-8）
    """
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    lines = []
    lines.append("Duplicate Files Report (Size + SHA256)")
    lines.append(f"Generated: {now}")
    lines.append(f"Root folder: {root_folder}")
    lines.append(f"Total files scanned: {files_count}")
    lines.append(f"Duplicate groups found: {len(dupes)}")
    lines.append("=" * 80)

    for h, paths in dupes.items():
        lines.append(f"\nSHA256: {h}")
        lines.append(f"Count: {len(paths)}")
        for i, p in enumerate(paths, start=1):
            lines.append(f"  {i}. {p}")

    out_dir = os.path.dirname(report_path)
    if out_dir and not os.path.exists(out_dir):
        os.makedirs(out_dir, exist_ok=True)

    with open(report_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    print(f"\n[OK] 已写入重复文件报告: {report_path}")


def clean_input_path(p: str) -> str:
    """处理路径引号"""
    if p is None:
        return ""
    return p.strip().replace('"', "").replace("'", "")


def interactive_main():
    """交互模式"""
    target_path = input("请输入要扫描的文件夹路径: ").strip()
    target_path = clean_input_path(target_path)

    if os.path.exists(target_path) and os.path.isdir(target_path):
        try:
            find_duplicates(target_path, recursive=True)
            # 注意：在交互模式下，如果需要生成报告，需要在此处添加逻辑，
            # 或者仅依靠命令行输出。这里为了简化逻辑保持原样，只在命令行模式强制写报告。
        except KeyboardInterrupt:
            print("\n\n用户强制停止扫描。")
    else:
        print("\n错误: 路径不存在或不是一个有效的文件夹。")

    input("\n按 Enter (回车) 键退出程序...")


def automation_main(argv: list):
    """自动化/命令行模式"""
    parser = argparse.ArgumentParser(
        description="Find duplicate files by Size then SHA256."
    )
    parser.add_argument("folder", help="Target folder to scan.")
    parser.add_argument(
        "--non-recursive",
        action="store_true",
        help="Only scan the top-level folder.",
    )
    parser.add_argument(
        "--no-report",
        action="store_true",
        help="Do not write report file.",
    )
    parser.add_argument(
        "--report",
        default="duplicate_report.txt",
        help="Report file path.",
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

    if dupes and not args.no_report:
        report = args.report
        if not os.path.isabs(report):
            report_path = os.path.join(folder, report)
        else:
            report_path = report

        try:
            write_report(report_path, folder, files_count, dupe_groups, dupes)
        except Exception as e:
            print(f"\n[WARN] 写入报告失败：{e}")


if __name__ == "__main__":
    if len(sys.argv) == 1:
        interactive_main()
    else:
        automation_main(sys.argv[1:])
