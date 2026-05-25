#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
清理 Windows "打开方式" 中无效/重复的程序条目
扫描注册表，找出指向不存在 exe 的打开方式，支持预览后清理
"""

import os
import shutil
import sys
import winreg
from collections import defaultdict


def get_executable_path(command):
    """从 command 字符串中提取 exe 路径，正确处理空格和环境变量"""
    if not command:
        return None
    cmd = command.strip()
    # 处理带参数的情况，如: "C:\Program Files\exe.exe" "%1"
    if cmd.startswith('"'):
        end = cmd.find('"', 1)
        if end > 0:
            exe = cmd[1:end]
        else:
            exe = cmd.strip('"')
    else:
        parts = cmd.split()
        exe = parts[0] if parts else cmd
    # 展开环境变量如 %SystemRoot%
    return os.path.expandvars(exe).strip('"')


def list_invalid_applications():
    r"""扫描 HKEY_CLASSES_ROOT\Applications 下的无效程序"""
    invalid = []
    valid = []
    try:
        with winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, r"Applications") as apps_key:
            idx = 0
            while True:
                try:
                    app_name = winreg.EnumKey(apps_key, idx)
                    idx += 1
                    # 读取 shell\open\command
                    try:
                        with winreg.OpenKey(apps_key, f"{app_name}\\shell\\open\\command") as cmd_key:
                            command, _ = winreg.QueryValueEx(cmd_key, None)
                    except FileNotFoundError:
                        continue

                    exe_path = get_executable_path(command)
                    if exe_path and os.path.exists(exe_path):
                        valid.append((app_name, exe_path))
                    else:
                        invalid.append((app_name, exe_path or command))
                except OSError:
                    break
    except Exception as e:
        print(f"扫描 Applications 出错: {e}")
    return invalid, valid


def list_invalid_openwithProgids():
    r"""扫描 HKEY_CURRENT_USER\Software\Microsoft\Windows\CurrentVersion\Explorer\FileExts 下的无效关联"""
    invalid_exts = defaultdict(list)
    base_path = r"Software\Microsoft\Windows\CurrentVersion\Explorer\FileExts"
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, base_path) as ext_key:
            idx = 0
            while True:
                try:
                    ext_name = winreg.EnumKey(ext_key, idx)
                    idx += 1
                    # 读取 OpenWithList
                    try:
                        with winreg.OpenKey(ext_key, f"{ext_name}\\OpenWithList") as ow_key:
                            j = 0
                            while True:
                                try:
                                    _, prog_id, _ = winreg.EnumValue(ow_key, j)
                                    j += 1
                                    # 检查 ProgID 或 exe 是否存在
                                    if prog_id.endswith('.exe'):
                                        # 尝试在 PATH 或常见路径中找到
                                        found = shutil.which(prog_id) is not None
                                        if not found and not os.path.exists(prog_id):
                                            invalid_exts[ext_name].append(prog_id)
                                except OSError:
                                    break
                    except FileNotFoundError:
                        pass
                except OSError:
                    break
    except Exception as e:
        print(f"扫描 FileExts 出错: {e}")
    return invalid_exts


def delete_application_key(app_name):
    """删除 Applications 下的指定键（需要递归删除）"""
    import ctypes
    if not ctypes.windll.shell32.IsUserAnAdmin():
        print("  [!] 需要管理员权限才能删除注册表项")
        return False

    def delete_tree(hkey, subpath):
        try:
            with winreg.OpenKey(hkey, subpath, 0, winreg.KEY_ALL_ACCESS) as key:
                # 先删除子键
                while True:
                    try:
                        sub = winreg.EnumKey(key, 0)
                        delete_tree(hkey, f"{subpath}\\{sub}")
                    except OSError:
                        break
            winreg.DeleteKey(hkey, subpath)
            return True
        except Exception as e:
            print(f"  删除失败 {subpath}: {e}")
            return False

    return delete_tree(winreg.HKEY_CLASSES_ROOT, f"Applications\\{app_name}")


def main():
    print("=" * 60)
    print('  Windows "打开方式" 清理工具')
    print("=" * 60)
    print()

    # 1. 扫描 Applications
    print("[扫描] 正在扫描 HKEY_CLASSES_ROOT\\Applications ...")
    invalid_apps, valid_apps = list_invalid_applications()

    print(f"   发现有效条目: {len(valid_apps)} 个")
    if invalid_apps:
        print(f"   发现无效条目: {len(invalid_apps)} 个")
        print()
        print("-" * 60)
        print("[无效] 以下打开方式指向不存在的程序，建议清理：")
        print("-" * 60)
        for i, (name, path) in enumerate(invalid_apps, 1):
            print(f"  {i}. {name}")
            print(f"     路径: {path}")
    else:
        print("   未发现无效 Applications 条目，很好！")

    print()

    # 2. 扫描 FileExts
    print("[扫描] 正在扫描文件扩展名关联 ...")
    invalid_exts = list_invalid_openwithProgids()
    if invalid_exts:
        total = sum(len(v) for v in invalid_exts.values())
        print(f"   发现无效关联: {total} 个 (涉及 {len(invalid_exts)} 种扩展名)")
        print()
        print("-" * 60)
        print('[无效] 以下扩展名的 "打开方式" 列表包含无效程序：')
        print("-" * 60)
        for ext, progs in invalid_exts.items():
            print(f"  .{ext}: {', '.join(progs)}")
    else:
        print("   未发现无效文件扩展名关联！")

    print()
    print("=" * 60)

    if not invalid_apps and not invalid_exts:
        print("[完成] 没有需要清理的内容，你的系统很干净！")
        return

    # 非交互式终端直接跳过清理（如 CI/CD、自动化工具）
    if not sys.stdin.isatty():
        print("\n[提示] 检测到非交互式终端，仅执行扫描。")
        print("       如需清理，请在交互式终端中以管理员身份运行此脚本。")
        return

    # 询问是否清理
    ans = input("\n是否删除无效的 Applications 条目? (yes/no): ").strip().lower()
    if ans in ('yes', 'y'):
        import ctypes
        if not ctypes.windll.shell32.IsUserAnAdmin():
            print("\n[!] 当前没有管理员权限，请以管理员身份运行此脚本后再试。")
            print("   方法: 右键 -> 使用 PowerShell/终端 管理员运行")
            return

        deleted = 0
        for name, path in invalid_apps:
            print(f"\n  正在删除: {name} ...", end="")
            if delete_application_key(name):
                print(" [已删除]")
                deleted += 1
            else:
                print(" [失败]")
        print(f"\n共删除 {deleted} 个无效条目")
    else:
        print("已取消操作，没有做任何更改。")


if __name__ == "__main__":
    main()
    input("\n按回车键退出...")

