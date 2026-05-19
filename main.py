import os
import sys
from logger import Logger
from config_loader import ConfigLoader
from file_scanner import FileScanner, SUPPORTED_EXTENSIONS
from matcher import Matcher
from file_mover import FileMover
from archiver import Archiver
from everything_scanner import EverythingScanner


def get_user_input():
    work_key = input("请输入工号Key（可为空，直接回车跳过）: ").strip()

    size_input = input("请输入大文件过滤阈值（单位MB，直接回车使用默认值100MB）: ").strip()
    if size_input == "":
        user_max_size = None
    else:
        try:
            user_max_size = float(size_input)
            if user_max_size <= 0:
                print("阈值必须为正数，将使用默认值")
                user_max_size = None
        except ValueError:
            print("输入无效，将使用默认值")
            user_max_size = None

    return work_key, user_max_size


def get_all_drives():
    drives = []
    try:
        if hasattr(os, "listdrives"):
            for drive in os.listdrives():
                drives.append(drive.rstrip("\\"))
        else:
            import string
            for letter in string.ascii_uppercase:
                drive = f"{letter}:\\"
                if os.path.exists(drive):
                    drives.append(f"{letter}:")
    except Exception:
        pass
    return drives


def resolve_target_paths():
    if len(sys.argv) > 1:
        target = sys.argv[1]
        if os.path.exists(target):
            return [os.path.abspath(target)]
        else:
            print(f"警告: 指定的路径不存在: {target}")
            print("检测无指定参数，将扫描所有硬盘")
            return get_all_drives()
    else:
        target = input("请输入要扫描的目录路径（直接回车则扫描所有硬盘）: ").strip()
        if not target:
            print("未指定路径，将扫描所有硬盘")
            return get_all_drives()
        if not os.path.exists(target):
            print(f"路径不存在: {target}")
            print("将扫描所有硬盘")
            return get_all_drives()
        return [os.path.abspath(target)]


def main():
    logger = Logger()
    logger.info("=" * 60)
    logger.info("多格式文件敏感检测工具启动")
    logger.info("=" * 60)

    if getattr(sys, 'frozen', False):
        exe_dir = os.path.dirname(sys.executable)
        user_config = os.path.join(exe_dir, "config.json")
        bundled_path = os.path.join(sys._MEIPASS, "config.json") if hasattr(sys, '_MEIPASS') else None
        if not os.path.exists(user_config) and bundled_path and os.path.exists(bundled_path):
            try:
                import shutil
                shutil.copy2(bundled_path, user_config)
                logger.info(f"已导出默认配置文件到: {user_config}")
                logger.info(f"用户可编辑此文件自定义检测规则")
            except Exception as e:
                logger.warning(f"导出配置文件失败: {e}")
        config_path = user_config
    else:
        base_path = os.path.dirname(os.path.abspath(__file__))
        config_path = os.path.join(base_path, "config.json")
    config_loader = ConfigLoader(config_path)

    try:
        config, compiled_rules = config_loader.load()
    except RuntimeError as e:
        logger.error(f"配置加载失败: {e}")
        input("按回车键退出...")
        sys.exit(1)

    logger.info(f"已加载 {len(compiled_rules)} 条检测规则")
    for rule in compiled_rules:
        logger.info(f"  规则: {rule['name']}")

    default_max_size = config_loader.get_max_file_size()
    match_threshold = config_loader.get_match_threshold()
    backup_base_path = config_loader.get_backup_base_path()

    logger.info(f"默认文件大小阈值: {default_max_size}MB")
    logger.info(f"正则匹配阈值: {match_threshold}次")
    logger.info(f"备份基路径: {backup_base_path or '(未配置)'}")

    logger.info("-" * 60)
    logger.info("请输入启动参数")
    work_key, user_max_size = get_user_input()

    effective_max_size = user_max_size if user_max_size is not None else default_max_size
    logger.info(f"工号Key: {'[已设置]' if work_key else '[为空]'}")
    logger.info(f"大文件阈值: {effective_max_size}MB")

    logger.info("-" * 60)
    target_paths = resolve_target_paths()
    for p in target_paths:
        logger.info(f"目标扫描路径: {p}")

    max_size_bytes = effective_max_size * 1024 * 1024
    scanner = FileScanner(max_size_bytes)
    matcher = Matcher(compiled_rules, match_threshold)
    mover = FileMover(backup_base_path)
    archiver = Archiver()

    target_files = []
    everything = EverythingScanner()

    if everything.available:
        everything_files = everything.find_files(
            target_paths, SUPPORTED_EXTENSIONS, max_size_bytes
        )
        if everything_files is not None:
            target_files = everything_files

    # 回退方案：当 Everything 不可用或查询全部失败时，使用 Python os.walk
    if not everything.available or (everything.available and everything_files is None):
        if not everything.available:
            logger.info("使用 Python 标准扫描（os.walk）作为回退方案...")
        else:
            logger.info("Everything 查询失败，使用 Python 标准扫描（os.walk）作为回退方案...")
        for path in target_paths:
            target_files.extend(scanner.scan_directory(path))
    elif not target_files:
        # Everything 成功执行但未找到任何文件（可靠结果，不再回退）
        pass

    if not target_files:
        logger.warning(f"未发现支持的文件类型 (支持: {', '.join(sorted(SUPPORTED_EXTENSIONS))})")
        logger.info("扫描结束，未发现可供检测的文件")
        input("按回车键退出...")
        return

    sensitive_files = []

    logger.info("-" * 60)
    logger.info("开始文件敏感检测")
    for idx, file_path in enumerate(target_files, 1):
        logger.info(f"[{idx}/{len(target_files)}] 检测文件: {file_path}")

        is_over, size_mb = scanner.is_oversized(file_path)
        if is_over:
            logger.info(f"  跳过（超出大小阈值）")
            continue

        logger.info(f"  文件大小: {size_mb:.2f}MB")

        text = scanner.extract_text(file_path)
        if not text:
            logger.info(f"  文件为空或解析无内容")
            continue

        is_sensitive, details = matcher.scan_text(text, file_path)

        if is_sensitive:
            sensitive_files.append(file_path)
            logger.info(f"  判定结果: [敏感文件]")
            for d in details:
                logger.info(f"    匹配规则: {d['rule_name']} (匹配 {d['match_count']} 次)")
        else:
            logger.info(f"  判定结果: [安全文件]")

    logger.info("-" * 60)
    logger.info(f"检测完成，共发现 {len(sensitive_files)} 个敏感文件")

    if not sensitive_files:
        logger.info("无需进行后续处理")
        input("按回车键退出...")
        return

    logger.info("-" * 60)
    logger.info("开始处理敏感文件")

    date_folder = mover.create_date_folder()
    logger.info(f"备份目录: {date_folder}")

    moved_files = mover.move_files(sensitive_files, date_folder)

    if not moved_files:
        logger.error("文件迁移失败，无法进行压缩处理")
        input("按回车键退出...")
        return

    if work_key:
        logger.info("工号Key已设置，执行加密压缩")
        archive_path = archiver.create_archive(moved_files, date_folder, password=work_key)
        if archive_path:
            archiver.create_password_file(date_folder, work_key)
        else:
            logger.error("加密压缩失败")
    else:
        logger.info("工号Key为空，执行普通无加密压缩")
        archive_path = archiver.create_archive(moved_files, date_folder)

    logger.info("=" * 60)
    logger.info("全部处理完成")
    logger.info(f"扫描路径数: {len(target_paths)}")
    for p in target_paths:
        logger.info(f"  扫描路径: {p}")
    logger.info(f"敏感文件数: {len(sensitive_files)}")
    logger.info(f"备份位置: {date_folder}")
    if archive_path:
        logger.info(f"压缩包: {archive_path}")

    input("按回车键退出...")


if __name__ == "__main__":
    main()
