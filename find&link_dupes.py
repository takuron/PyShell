# Name: 交互式重复文件清理工具
# Description: 1. 扫描目录(大小+SHA256) 2. 交互式询问用户保留哪一个文件 3. 删除其余副本并生成相对路径的唯一索引文件
# Usage: python find&link_dupes.py

import hashlib
import os
import sys
import uuid
from datetime import datetime
from collections import defaultdict


def calculate_sha256(filepath: str):
    """
    计算文件的 SHA256 哈希值 (分块读取)
    """
    sha256_hash = hashlib.sha256()
    try:
        with open(filepath, "rb") as f:
            for byte_block in iter(lambda: f.read(65536), b""):
                sha256_hash.update(byte_block)
        return sha256_hash.hexdigest()
    except (PermissionError, OSError):
        return None


def find_duplicates(root_folder: str):
    """
    两阶段查找重复文件：
    1. 按文件大小分组。
    2. 对大小相同的组计算 SHA256，返回重复文件字典。
    """
    # --- 阶段 1: 按大小分组 ---
    files_by_size = defaultdict(list)
    total_files_scanned = 0

    print(f"\n[1/2] 正在扫描文件结构: {root_folder}")
    print("-" * 60)

    for dirpath, _, filenames in os.walk(root_folder):
        for filename in filenames:
            full_path = os.path.join(dirpath, filename)
            try:
                file_size = os.path.getsize(full_path)
                files_by_size[file_size].append(full_path)
                total_files_scanned += 1
            except (OSError, PermissionError):
                continue

            # 简单的进度显示
            if total_files_scanned % 1000 == 0:
                print(f"\r已扫描 {total_files_scanned} 个文件...", end="", flush=True)

    print(f"\n扫描结束。共发现 {total_files_scanned} 个文件。")

    # 筛选出潜在重复（大小相同的文件数 > 1）
    potential_groups = {
        s: paths for s, paths in files_by_size.items() if len(paths) > 1
    }
    total_potential_groups = len(potential_groups)

    if total_potential_groups == 0:
        return {}

    # --- 阶段 2: 计算哈希并比对 ---
    print(f"\n[2/2] 正在深度比对 {total_potential_groups} 组大小相同的文件...")

    dupes = {}  # { hash: [path1, path2, ...] }

    processed_groups = 0
    for _, paths in potential_groups.items():
        processed_groups += 1
        # 显示进度
        if processed_groups % 10 == 0:
            print(
                f"\r正在处理第 {processed_groups}/{total_potential_groups} 组...",
                end="",
                flush=True,
            )

        hashes_in_current_size = defaultdict(list)
        for path in paths:
            file_hash = calculate_sha256(path)
            if file_hash:
                hashes_in_current_size[file_hash].append(path)

        for file_hash, file_list in hashes_in_current_size.items():
            if len(file_list) > 1:
                dupes[file_hash] = file_list

    print(f"\n\n比对完成！共发现 {len(dupes)} 组内容完全一样的重复文件。")
    return dupes


def resolve_duplicates(dupes: dict):
    """
    遍历重复列表，让用户选择处理
    """
    if not dupes:
        print("没有发现重复文件，程序退出。")
        return

    print("\n" + "=" * 60)
    print("进入清理模式")
    print("请根据提示输入数字选择【保留】的文件，其余副本将被【删除】。")
    print("输入 's' 或 'skip' 可跳过当前组。")
    print("=" * 60)

    deleted_count = 0
    reclaimed_space = 0

    # 遍历每一组重复文件
    for i, (file_hash, paths) in enumerate(dupes.items(), 1):
        print(f"\n>>> 第 {i}/{len(dupes)} 组 (SHA256: {file_hash[:8]}...)")

        # 打印选项
        for idx, path in enumerate(paths, 1):
            print(f"  [{idx}] {path}")

        # 循环获取有效输入
        while True:
            choice = (
                input("\n请输入要【保留】的文件编号 (输入 's' 跳过): ").strip().lower()
            )

            if choice in ["s", "skip"]:
                print("已跳过此组。")
                break

            if choice.isdigit():
                choice_idx = int(choice) - 1  # 转换为 0-based 索引
                if 0 <= choice_idx < len(paths):
                    # 执行删除逻辑
                    file_to_keep = paths[choice_idx]
                    files_to_delete = [
                        p for j, p in enumerate(paths) if j != choice_idx
                    ]

                    print(f"保留: {file_to_keep}")
                    for f_del in files_to_delete:
                        try:
                            file_size = os.path.getsize(f_del)
                            os.remove(f_del)  # 删除文件
                            
                            # 获取删除文件所在目录和目标保留文件的相对路径
                            del_dir = os.path.dirname(f_del)
                            rel_path = os.path.relpath(file_to_keep, start=del_dir)
                            
                            # 创建索引文件
                            index_file_path = f"{f_del}.link.txt"
                            with open(index_file_path, "w", encoding="utf-8") as link_f:
                                link_f.write(f"Target: {rel_path}\n")
                                link_f.write(f"Original: {os.path.basename(f_del)}\n")
                                link_f.write(f"Timestamp: {datetime.now().isoformat()}\n")
                                # 强制混入 UUID，保证任意两个索引文件的内容永远不相同
                                link_f.write(f"UUID: {uuid.uuid4().hex}\n")

                            print(f"  [X] 已删除并创建相对路径索引: {f_del}")
                            deleted_count += 1
                            reclaimed_space += file_size
                        except Exception as e:
                            print(f"  [Error] 处理失败 {f_del}: {e}")
                    break  # 跳出 while，处理下一组
                else:
                    print("错误: 编号超出范围，请重新输入。")
            else:
                print("错误: 请输入数字或 's'。")

    # 总结
    mb_saved = reclaimed_space / (1024 * 1024)
    print("\n" + "=" * 60)
    print("清理完成！")
    print(f"共删除文件数: {deleted_count}")
    print(f"释放磁盘空间: {mb_saved:.2f} MB")
    input("按 Enter 键退出...")


def clean_input_path(p: str) -> str:
    if p is None:
        return ""
    return p.strip().replace('"', "").replace("'", "")


def main():
    try:
        target_path = input("请输入要扫描的文件夹路径: ").strip()
        target_path = clean_input_path(target_path)

        if not (os.path.exists(target_path) and os.path.isdir(target_path)):
            print("\n错误: 路径不存在或不是一个有效的文件夹。")
            input("按 Enter 退出...")
            return

        # 1. 扫描
        dupes_dict = find_duplicates(target_path)

        # 2. 清理
        if dupes_dict:
            resolve_duplicates(dupes_dict)
        else:
            print("\n恭喜，未发现重复文件。")
            input("按 Enter 退出...")

    except KeyboardInterrupt:
        print("\n\n用户强制停止。")
        sys.exit(0)


if __name__ == "__main__":
    main()