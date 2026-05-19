import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
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


def process_single_file(file_path, scanner, matcher, skip_size_check):
    """处理单个文件：提取文本 + 敏感检测

    使用增量提取+匹配模式，边提取边检测，达到阈值立即停止。

    Args:
        file_path: 文件路径
        scanner: FileScanner 实例
        matcher: Matcher 实例
        skip_size_check: 是否跳过大小检查（Everything 已过滤时为 True）

    Returns:
        (file_path, is_sensitive, details, size_mb, elapsed_ms)
    """
    start = time.monotonic()
    try:
        # 使用增量提取+匹配（核心优化：边提取边检测，达到阈值立即停止）
        is_sensitive, details, size_mb = scanner.extract_and_match(file_path, matcher)
        elapsed_ms = (time.monotonic() - start) * 1000
        return file_path, is_sensitive, details, size_mb, elapsed_ms
    except Exception as e:
        elapsed_ms = (time.monotonic() - start) * 1000
        logger = Logger()
        logger.warning(f"文件处理异常: {file_path} - {e}")
        return file_path, False, [], -1, elapsed_ms


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
    everything_filtered_size = False  # 标记 Everything 是否已按大小过滤

    if everything.available:
        everything_files = everything.find_files(
            target_paths, SUPPORTED_EXTENSIONS, max_size_bytes
        )
        if everything_files is not None:
            target_files = everything_files
            everything_filtered_size = everything._has_get_size_func  # 有大小过滤功能时跳过重复检查

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

    # ----------------------------------------------------------
    # 并发检测：使用线程池并行处理文件
    # 文本提取是 I/O 密集型（读文件）+ CPU 密集型（解析文档）
    # 线程池可以让 I/O 等待和 CPU 计算重叠，大幅提升吞吐
    # ----------------------------------------------------------
    num_workers = min(os.cpu_count() or 4, 8)  # 最多 8 线程，避免过多竞争
    total_files = len(target_files)

    logger.info("-" * 60)
    logger.info("开始文件敏感检测（并发模式）")
    logger.info(f"并发线程数: {num_workers}")

    completed_count = 0
    skipped_count = 0     # 快速通过的安全文件计数（<=200ms）
    SILENT_THRESHOLD_MS = 200  # 200ms 以内的安全文件不打详情
    last_progress_pct = -1  # 上次打印进度条时的百分比

    with ThreadPoolExecutor(max_workers=num_workers) as executor:
        # 提交所有文件处理任务
        future_to_file = {
            executor.submit(
                process_single_file, fp, scanner, matcher, everything_filtered_size
            ): fp
            for fp in target_files
        }

        # 按完成顺序收集结果
        for future in as_completed(future_to_file):
            file_path, is_sensitive, details, size_mb, elapsed_ms = future.result()
            completed_count += 1

            # --- 敏感文件：始终完整打印 ---
            if is_sensitive:
                sensitive_files.append(file_path)
                logger.info(f"[{completed_count}/{total_files}] {file_path}")
                logger.info(f"  判定结果: [敏感文件] ({elapsed_ms:.0f}ms)")
                for d in details:
                    logger.info(f"    匹配规则: {d['rule_name']} (匹配 {d['match_count']} 次)")
                continue

            # --- 异常/超限文件：简要打印 ---
            if size_mb < 0:
                logger.info(f"[{completed_count}/{total_files}] 跳过（无法获取大小）: {file_path}")
                continue
            if size_mb > effective_max_size and not everything_filtered_size:
                logger.info(f"[{completed_count}/{total_files}] 跳过（超出大小阈值 {size_mb:.2f}MB）: {file_path}")
                continue

            # --- 安全文件：快速通过的不打详情，只显示进度条 ---
            if elapsed_ms <= SILENT_THRESHOLD_MS:
                skipped_count += 1
            else:
                # 慢文件打印详情，方便排查性能瓶颈
                logger.info(f"[{completed_count}/{total_files}] {file_path}")
                logger.info(f"  判定结果: [安全文件] ({elapsed_ms:.0f}ms, {size_mb:.2f}MB)")

            # 进度条：每增加 5% 打印一次
            pct = completed_count * 100 // total_files
            if pct >= last_progress_pct + 5:
                last_progress_pct = pct
                logger.info(f"进度: {pct}% ({completed_count}/{total_files})")

    if skipped_count > 0:
        logger.info(f"其中 {skipped_count} 个文件快速通过（<{SILENT_THRESHOLD_MS}ms）")

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
