# Name: 还原重复文件 (通过索引文件)
# Description: 扫描目录下的 .link.txt 索引文件，解析相对路径并将其对应的源文件复制回原处，恢复被清理的重复文件。
# Usage: python restore_dupes.py

import os
import sys
import shutil


def parse_link_file(filepath: str):
    """
    解析索引文件，提取相对路径 (Target) 和原始文件名 (Original)
    """
    target_rel = None
    original_name = None
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            for line in f:
                if line.startswith("Target: "):
                    target_rel = line.strip().split("Target: ", 1)[1]
                elif line.startswith("Original: "):
                    original_name = line.strip().split("Original: ", 1)[1]
    except Exception as e:
        print(f"  [Error] 读取索引文件失败 {filepath}: {e}")
    
    return target_rel, original_name


def restore_from_links(root_folder: str):
    """
    遍历目录查找索引文件并执行还原操作
    """
    print(f"\n开始扫描并还原目录: {root_folder}")
    print("-" * 60)
    
    restored_count = 0
    failed_count = 0

    for dirpath, _, filenames in os.walk(root_folder):
        for filename in filenames:
            if filename.endswith(".link.txt"):
                link_path = os.path.join(dirpath, filename)
                target_rel, original_name = parse_link_file(link_path)

                if not target_rel or not original_name:
                    print(f"  [Skip] 格式无效的索引文件: {link_path}")
                    failed_count += 1
                    continue

                # 计算目标文件的绝对路径
                target_abs_path = os.path.normpath(os.path.join(dirpath, target_rel))
                restore_dest_path = os.path.join(dirpath, original_name)

                # 检查所指向的保留文件是否存在
                if not os.path.exists(target_abs_path):
                    print(f"  [Error] 目标源文件不存在，无法还原: {target_abs_path} (来源索引: {filename})")
                    failed_count += 1
                    continue
                
                # 检查还原位置是否已经存在同名文件
                if os.path.exists(restore_dest_path):
                    print(f"  [Skip] 还原位置已存在同名文件: {restore_dest_path}")
                    failed_count += 1
                    continue

                try:
                    # 将文件复制回原位以完成还原
                    shutil.copy2(target_abs_path, restore_dest_path)
                    # 还原成功后删除索引文件
                    os.remove(link_path)
                    print(f"  [OK] 已还原: {restore_dest_path}")
                    restored_count += 1
                except Exception as e:
                    print(f"  [Error] 还原过程发生异常 {link_path}: {e}")
                    failed_count += 1
    
    print("\n" + "=" * 60)
    print("还原操作结束。")
    print(f"成功还原文件数: {restored_count}")
    print(f"失败或跳过文件数: {failed_count}")
    print("=" * 60)


def clean_input_path(p: str) -> str:
    if p is None:
        return ""
    return p.strip().replace('"', "").replace("'", "")


def main():
    try:
        target_path = input("请输入要扫描并还原的文件夹路径: ").strip()
        target_path = clean_input_path(target_path)

        if not (os.path.exists(target_path) and os.path.isdir(target_path)):
            print("\n错误: 路径不存在或不是一个有效的文件夹。")
            input("按 Enter 退出...")
            return

        restore_from_links(target_path)
        input("按 Enter 键退出...")

    except KeyboardInterrupt:
        print("\n\n用户强制停止。")
        sys.exit(0)


if __name__ == "__main__":
    main()