#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
清理 Qt Creator 和 HBuilderX 的无效打开方式条目
直接扫描注册表中指向已删除程序的路径，支持预览后清理
"""

import ctypes
import os
import sys
import winreg


# 已知无效的路径关键词（用于匹配）
INVALID_PATHS = [
    r"D:\soft\qt\Tools\QtCreator\bin\qtcreator.exe",
    r"HBuilderX\HBuilderX.exe",
]


def is_invalid_command(command):
    """判断 command 是否指向已知无效程序"""
    if not command:
        return False
    cmd_lower = command.lower()
    for invalid in INVALID_PATHS:
        if invalid.lower() in cmd_lower:
            return True
    return False


def delete_registry_tree(hkey, subpath):
    """递归删除注册表子键"""
    try:
        with winreg.OpenKey(hkey, subpath, 0, winreg.KEY_ALL_ACCESS) as key:
            while True:
                try:
                    sub = winreg.EnumKey(key, 0)
                    delete_registry_tree(hkey, f"{subpath}\\{sub}")
                except OSError:
                    break
        winreg.DeleteKey(hkey, subpath)
        return True
    except Exception as e:
        print(f"    删除失败 {subpath}: {e}")
        return False


def scan_and_clean_applications():
    """扫描并清理 Applications 下的无效条目"""
    to_delete = []

    try:
        with winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, r"Applications") as apps_key:
            idx = 0
            while True:
                try:
                    app_name = winreg.EnumKey(apps_key, idx)
                    idx += 1
                    try:
                        with winreg.OpenKey(apps_key, f"{app_name}\\shell\\open\\command") as cmd_key:
                            command, _ = winreg.QueryValueEx(cmd_key, None)
                    except FileNotFoundError:
                        continue

                    if is_invalid_command(command):
                        to_delete.append((app_name, command))
                except OSError:
                    break
    except Exception as e:
        print(f"扫描 Applications 出错: {e}")

    return to_delete


def scan_and_clean_ext_associations():
    """扫描文件扩展名默认关联中的无效条目"""
    # 只扫描常见的 Qt Creator / HBuilderX 扩展名
    target_exts = [
        # Qt Creator 常用扩展名
        '.c', '.cpp', '.cc', '.cp', '.cxx', '.h', '.hpp', '.hh', '.hxx',
        '.pri', '.pro', '.qbs', '.qml', '.qs', '.ui',
        # HBuilderX 常用扩展名
        '.nvue', '.vue',
    ]
    to_fix = []

    for ext in target_exts:
        try:
            with winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, ext) as ext_key:
                try:
                    default_assoc, _ = winreg.QueryValueEx(ext_key, None)
                    if default_assoc and isinstance(default_assoc, str):
                        # 检查关联的 ProgID 下是否指向无效程序
                        try:
                            with winreg.OpenKey(winreg.HKEY_CLASSES_ROOT,
                                                f"{default_assoc}\\shell\\open\\command") as cmd_key:
                                command, _ = winreg.QueryValueEx(cmd_key, None)
                                if is_invalid_command(command):
                                    to_fix.append((ext, default_assoc, command))
                        except FileNotFoundError:
                            pass
                except FileNotFoundError:
                    pass
        except FileNotFoundError:
            pass

    return to_fix


def main():
    print("=" * 60)
    print("  Qt Creator / HBuilderX 无效打开方式清理工具")
    print("=" * 60)
    print()

    # 检查管理员权限
    if not ctypes.windll.shell32.IsUserAnAdmin():
        print("[!] 需要管理员权限才能清理注册表！")
        print("    请右键 -> 以管理员身份运行此脚本。")
        return 1

    # 扫描 Applications
    print("[扫描] 正在扫描 Applications 下的无效条目...")
    invalid_apps = scan_and_clean_applications()

    if invalid_apps:
        print(f"    发现 {len(invalid_apps)} 个无效条目：")
        print()
        for i, (name, cmd) in enumerate(invalid_apps, 1):
            print(f"  {i}. {name}")
            print(f"     命令: {cmd}")
        print()
    else:
        print("    未发现无效 Applications 条目。")

    # 扫描文件扩展名关联
    print("[扫描] 正在扫描文件扩展名关联...")
    invalid_exts = scan_and_clean_ext_associations()

    if invalid_exts:
        print(f"    发现 {len(invalid_exts)} 个无效扩展名关联：")
        print()
        for ext, assoc, cmd in invalid_exts:
            print(f"  {ext} -> {assoc}")
            print(f"     命令: {cmd}")
        print()
    else:
        print("    未发现无效扩展名关联。")

    if not invalid_apps and not invalid_exts:
        print()
        print("[完成] 没有需要清理的内容！")
        return 0

    # 执行清理
    print()
    print("-" * 60)
    print("正在执行清理...")
    print("-" * 60)
    print()

    deleted_apps = 0
    for name, cmd in invalid_apps:
        print(f"  删除 Applications\\{name} ... ", end="")
        if delete_registry_tree(winreg.HKEY_CLASSES_ROOT, f"Applications\\{name}"):
            print("[已删除]")
            deleted_apps += 1
        else:
            print("[失败]")

    fixed_exts = 0
    for ext, assoc, cmd in invalid_exts:
        print(f"  重置 {ext} 默认关联 ... ", end="")
        try:
            # 删除该扩展名的默认值，让系统重新选择
            with winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, ext, 0, winreg.KEY_ALL_ACCESS) as key:
                try:
                    winreg.DeleteValue(key, None)
                    print("[已重置]")
                    fixed_exts += 1
                except OSError:
                    print("[无需处理]")
        except Exception as e:
            print(f"[失败: {e}]")

    print()
    print("=" * 60)
    print(f"  清理完成：删除 {deleted_apps} 个 Applications 条目，")
    print(f"            重置 {fixed_exts} 个扩展名关联。")
    print("=" * 60)

    return 0


if __name__ == "__main__":
    import io
    log_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "clean_result.log")
    with open(log_path, "w", encoding="utf-8") as log_f:
        # Tee: 同时输出到控制台和日志文件
        class Tee:
            def __init__(self, *streams): self.streams = streams
            def write(self, data):
                for s in self.streams: s.write(data)
            def flush(self):
                for s in self.streams: s.flush()
        sys.stdout = Tee(sys.__stdout__, log_f)
        sys.stderr = Tee(sys.__stderr__, log_f)
        ret = main()
        sys.stdout = sys.__stdout__
        sys.stderr = sys.__stderr__
    sys.exit(ret)
