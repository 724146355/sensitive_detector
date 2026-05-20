import os
import sys
import json
import time
import gc
import traceback
import threading
import ctypes
import faulthandler
import concurrent.futures
from concurrent.futures import ThreadPoolExecutor
from logger import Logger
from config_loader import ConfigLoader
from file_scanner import FileScanner, SUPPORTED_EXTENSIONS
from matcher import Matcher
from file_mover import FileMover
from archiver import Archiver
from everything_scanner import EverythingScanner


class ThreadKillError(Exception):
    """自定义异常：用于线程空闲超时时中断工作线程的当前处理

    继承自 Exception（而非 BaseException），确保 ThreadPoolExecutor 能正确捕获
    并存储为 future 的异常结果，避免 SystemExit 导致程序退出或线程异常终止。
    """
    pass


def _kill_thread(thread_ident):
    """中断指定线程的当前处理（通过在线程中异步抛出 ThreadKillError 异常）

    注意：
    - 如果线程正在执行 C 扩展代码（如 PyMuPDF），异常将在 C 代码返回后生效
    - 使用 ThreadKillError(Exception) 而非 SystemExit，确保 ThreadPoolExecutor 能正确处理
    - 线程不会死亡，而是中断当前文件处理，继续执行队列中的下一个任务
    - 返回 True 表示成功设置异常，False 表示线程已不存在或操作失败
    """
    try:
        tid = ctypes.c_long(thread_ident)
        exc = ctypes.py_object(ThreadKillError)
        res = ctypes.pythonapi.PyThreadState_SetAsyncExc(tid, exc)
        if res == 0:
            return False  # 线程已不存在
        elif res > 1:
            # 异常被设置到多个线程，重置
            ctypes.pythonapi.PyThreadState_SetAsyncExc(tid, None)
            return False
        return True
    except Exception:
        return False


def get_user_input():
    work_key = input("请输入密码Key（可为空，直接回车跳过）: ").strip()

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


def process_single_file(file_path, scanner, matcher, skip_size_check, start_times, start_lock, file_thread_map, file_thread_lock):
    """处理单个文件：提取文本 + 敏感检测

    Args:
        file_path: 文件路径
        scanner: FileScanner 实例
        matcher: Matcher 实例
        skip_size_check: 是否跳过大小检查（Everything 已过滤时为 True）
        start_times: 共享字典，记录实际开始处理时间
        start_lock: 线程安全锁
        file_thread_map: 共享字典，记录文件对应的线程ID（用于线程空闲超时终止）
        file_thread_lock: file_thread_map 的线程安全锁

    Returns:
        (file_path, is_sensitive, details, size_mb, elapsed_ms)
    """
    thread_ident = threading.current_thread().ident
    with file_thread_lock:
        file_thread_map[file_path] = thread_ident

    start = time.monotonic()
    with start_lock:
        start_times[file_path] = start
    try:
        is_sensitive, details, size_mb = scanner.extract_and_match(file_path, matcher)
        elapsed_ms = (time.monotonic() - start) * 1000
        return file_path, is_sensitive, details, size_mb, elapsed_ms
    except ThreadKillError:
        # 线程空闲超时中断，不再处理当前文件
        raise
    except MemoryError:
        elapsed_ms = (time.monotonic() - start) * 1000
        logger = Logger()
        logger.error(f"文件处理内存不足: {file_path}")
        gc.collect()
        return file_path, False, [], -1, elapsed_ms
    except Exception as e:
        elapsed_ms = (time.monotonic() - start) * 1000
        logger = Logger()
        logger.exception(f"文件处理异常: {file_path}")
        return file_path, False, [], -1, elapsed_ms
    finally:
        with file_thread_lock:
            file_thread_map.pop(file_path, None)


def main():
    # 确保 Windows EXE 控制台输出立即可见，避免启动白屏
    # PyInstaller 打包后 stdout 默认全缓冲，logging 写入后不会立即显示
    # write_through=True: TextIOWrapper 不缓冲，直接写入底层 BufferedWriter
    # line_buffering=True: 遇到换行符时强制 flush 整个输出管道（含 BufferedWriter）
    # 两者配合才能保证每行日志立即到达控制台
    for stream in (sys.stdout, sys.stderr):
        if stream:
            try:
                stream.reconfigure(line_buffering=True, write_through=True)
            except (AttributeError, OSError):
                pass

    # 强制输出一行启动提示，唤醒控制台显示，避免用户以为程序卡死
    print("敏感检测工具启动中...", flush=True)

    faulthandler.enable()
    logger = Logger()
    logger.info("=" * 60)
    logger.info("多格式文件敏感检测工具启动")
    logger.info("=" * 60)

    # ----------------------------------------------------------
    # 配置文件处理：对比本地与程序内置属性数量
    #   - 本地属性少于内置 → 删除本地，以程序为准重新生成
    #   - 本地属性多于或等于内置 → 保留本地（用户自定义内容）
    #   - 本地不存在 → 直接生成默认配置
    # ----------------------------------------------------------
    from config_loader import CONFIG_DEFAULT

    if getattr(sys, 'frozen', False):
        exe_dir = os.path.dirname(sys.executable)
        config_path = os.path.join(exe_dir, "config.json")
    else:
        base_path = os.path.dirname(os.path.abspath(__file__))
        config_path = os.path.join(base_path, "config.json")

    if os.path.exists(config_path):
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                local_config = json.load(f)
            local_keys = set(local_config.keys())
            builtin_keys = set(CONFIG_DEFAULT.keys())

            # 本地缺少的属性
            missing_keys = builtin_keys - local_keys
            if missing_keys:
                logger.info(f"本地配置缺少属性: {', '.join(sorted(missing_keys))}")
                logger.info(f"删除本地配置，以程序内置配置为准")
                try:
                    os.remove(config_path)
                except OSError as e:
                    logger.warning(f"删除本地配置文件失败: {e}")
            else:
                logger.info(f"读取配置文件: {config_path}")
        except (json.JSONDecodeError, IOError) as e:
            logger.warning(f"本地配置文件损坏: {e}")
            logger.info(f"删除损坏的配置文件，以程序内置配置为准")
            try:
                os.remove(config_path)
            except OSError:
                pass
    else:
        logger.info(f"配置文件不存在，将创建默认配置: {config_path}")

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
    dev_mode = config_loader.get_dev_mode()
    file_timeout = config_loader.get_file_timeout()
    thread_idle_timeout = config_loader.get_thread_idle_timeout()

    # 将相对备份路径解析为绝对路径（基于 EXE/脚本所在目录）
    # 避免从不同工作目录启动时日期文件夹位置不一致，导致 scan.log 找不到
    if backup_base_path and not os.path.isabs(backup_base_path):
        if getattr(sys, 'frozen', False):
            base_dir = os.path.dirname(sys.executable)
        else:
            base_dir = os.path.dirname(os.path.abspath(__file__))
        backup_base_path = os.path.abspath(os.path.join(base_dir, backup_base_path))

    logger.info(f"默认文件大小阈值: {default_max_size}MB")
    logger.info(f"正则匹配阈值: {match_threshold}次")
    logger.info(f"备份基路径: {backup_base_path or '(未配置)'}")
    logger.info(f"运行模式: {'开发模式(仅复制)' if dev_mode else '正式模式(剪切)'}")
    logger.info(f"单文件超时: {file_timeout}秒")
    logger.info(f"线程空闲超时: {thread_idle_timeout}秒")

    logger.info("-" * 60)
    logger.info("请输入启动参数")
    sys.stdout.flush()  # 确保所有日志已刷新到控制台，避免提示被缓冲
    work_key, user_max_size = get_user_input()

    effective_max_size = user_max_size if user_max_size is not None else default_max_size
    logger.info(f"工号Key: {'[已设置]' if work_key else '[为空]'}")
    logger.info(f"大文件阈值: {effective_max_size}MB")

    logger.info("-" * 60)
    sys.stdout.flush()  # 确保提示信息已刷新到控制台
    target_paths = resolve_target_paths()
    for p in target_paths:
        logger.info(f"目标扫描路径: {p}")

    max_size_bytes = effective_max_size * 1024 * 1024
    scanner = FileScanner(max_size_bytes)
    matcher = Matcher(compiled_rules, match_threshold)
    mover = FileMover(backup_base_path, dev_mode=dev_mode)
    archiver = Archiver()

    # ----------------------------------------------------------
    # 文件扫描阶段
    # ----------------------------------------------------------
    target_files = []
    everything = EverythingScanner()
    everything_filtered_size = False

    if everything.available:
        everything_files = everything.find_files(
            target_paths, SUPPORTED_EXTENSIONS, max_size_bytes
        )
        if everything_files is not None:
            target_files = everything_files
            everything_filtered_size = everything._has_get_size_func

    if not everything.available or (everything.available and everything_files is None):
        if not everything.available:
            logger.info("使用 Python 标准扫描（os.walk）作为回退方案...")
        else:
            logger.info("Everything 查询失败，使用 Python 标准扫描（os.walk）作为回退方案...")
        for path in target_paths:
            target_files.extend(scanner.scan_directory(path))
    elif not target_files:
        pass

    if not target_files:
        logger.warning(f"未发现支持的文件类型 (支持: {', '.join(sorted(SUPPORTED_EXTENSIONS))})")
        logger.info("扫描结束，未发现可供检测的文件")
        input("按回车键退出...")
        return

    # ----------------------------------------------------------
    # 检测前：先创建日期文件夹 + 读取已扫描记录
    # ----------------------------------------------------------
    date_folder = mover.create_date_folder()
    mover.init_restore_bat(date_folder)
    logger.info(f"备份目录: {date_folder}")

    # 读取 scan.log：同日多次扫描时跳过已处理文件
    scan_log_path = os.path.join(date_folder, "scan.log")
    logger.info(f"扫描记录文件: {scan_log_path}")
    scanned_files = set()
    if os.path.exists(scan_log_path):
        try:
            with open(scan_log_path, "r", encoding="utf-8") as f:
                for line in f:
                    path = line.strip()
                    if path:
                        # 规范化路径，确保不同格式的路径也能匹配（大小写、斜杠方向）
                        scanned_files.add(os.path.normcase(os.path.normpath(path)))
            if scanned_files:
                logger.info(f"scan.log 中已有 {len(scanned_files)} 条扫描记录")
        except (IOError, OSError) as e:
            logger.warning(f"读取 scan.log 失败: {e}")
    else:
        logger.info("scan.log 不存在，首次扫描")

    # 过滤已扫描文件（路径规范化比较）
    if scanned_files:
        original_count = len(target_files)
        target_files = [fp for fp in target_files if os.path.normcase(os.path.normpath(fp)) not in scanned_files]
        skipped_scan = original_count - len(target_files)
        if skipped_scan > 0:
            logger.info(f"跳过 {skipped_scan} 个已扫描文件")
        else:
            logger.info(f"scan.log 中有 {len(scanned_files)} 条记录，但无匹配的待扫描文件")

    if not target_files:
        logger.info("所有文件均已扫描过，无需再次检测")
        mover.finalize_restore_bat()
        input("按回车键退出...")
        return

    transferred_files = []  # 已复制/剪切的文件目标路径
    transferred_lock = threading.Lock()  # 线程安全锁
    file_thread_map = {}  # file_path -> thread_ident（用于线程空闲超时终止）
    file_thread_lock = threading.Lock()
    soft_timed_out = {}  # file_path -> (start_time, thread_ident)（软超时但线程仍在运行的文件）
    zombie_futures = {}  # future -> file_path（软超时 future，需消费结果避免警告）
    thread_kill_count = 0

    # ----------------------------------------------------------
    # 并发检测 + 命中即复制/剪切（分批处理，防止内存溢出）
    # ----------------------------------------------------------
    num_workers = max((os.cpu_count() or 4) // 2, 1)
    total_files = len(target_files)

    logger.info("-" * 60)
    logger.info("开始文件敏感检测（并发模式）")
    logger.info(f"并发线程数: {num_workers}")
    logger.info(f"命中操作: {'复制' if dev_mode else '剪切'}")

    completed_count = 0
    skipped_count = 0
    timeout_count = 0
    error_count = 0
    SILENT_THRESHOLD_MS = 200
    last_progress_pct = -1
    HEARTBEAT_INTERVAL = 5  # 每 5 秒输出一次心跳日志
    CHUNK_SIZE = 1000  # 每批处理 1000 个文件

    target_subfolder = os.path.join(date_folder, "target")

    def _append_scan_log(file_path):
        """追加文件路径到 scan.log"""
        try:
            with open(scan_log_path, "a", encoding="utf-8") as f:
                f.write(file_path + "\n")
        except (IOError, OSError):
            pass

    try:
        total_chunks = (total_files + CHUNK_SIZE - 1) // CHUNK_SIZE

        for chunk_idx in range(total_chunks):
            chunk_start = chunk_idx * CHUNK_SIZE
            chunk_end = min(chunk_start + CHUNK_SIZE, total_files)
            chunk = target_files[chunk_start:chunk_end]

            if total_chunks > 1:
                logger.info(f"--- 批次 {chunk_idx + 1}/{total_chunks} (文件 {chunk_start + 1}-{chunk_end}) ---")

            file_start_times = {}
            file_start_lock = threading.Lock()

            with ThreadPoolExecutor(max_workers=num_workers) as executor:
                future_to_file = {
                    executor.submit(
                        process_single_file, fp, scanner, matcher, everything_filtered_size,
                        file_start_times, file_start_lock, file_thread_map, file_thread_lock
                    ): fp
                    for fp in chunk
                }

                pending = set(future_to_file.keys())
                last_heartbeat = time.monotonic()

                while pending or soft_timed_out:
                    if pending:
                        done, pending = concurrent.futures.wait(
                            pending, timeout=HEARTBEAT_INTERVAL,
                            return_when=concurrent.futures.FIRST_COMPLETED
                        )
                    else:
                        # 仅剩软超时线程在等待，sleep 等待心跳间隔
                        done = set()
                        time.sleep(HEARTBEAT_INTERVAL)

                    for future in done:
                        fp = future_to_file[future]
                        try:
                            file_path, is_sensitive, details, size_mb, elapsed_ms = future.result()
                        except ThreadKillError:
                            # 线程空闲超时中断，忽略结果
                            soft_timed_out.pop(fp, None)
                            continue
                        except Exception:
                            logger.exception(f"任务执行异常: {fp}")
                            error_count += 1
                            completed_count += 1
                            soft_timed_out.pop(fp, None)
                            continue

                        # 若文件已被软超时跳过，结果已过期，丢弃
                        if file_path in soft_timed_out:
                            del soft_timed_out[file_path]
                            continue

                        completed_count += 1

                        # 记录到 scan.log
                        _append_scan_log(file_path)

                        # --- 敏感文件：打印 + 立即复制/剪切 ---
                        if is_sensitive:
                            logger.info(f"[{completed_count}/{total_files}] {file_path}")
                            logger.info(f"  判定结果: [敏感文件] ({elapsed_ms:.0f}ms)")
                            for d in details:
                                logger.info(f"    匹配规则: {d['rule_name']} (匹配 {d['match_count']} 次)")
                            try:
                                dest_path = mover.transfer_file(file_path, target_subfolder)
                                if dest_path:
                                    with transferred_lock:
                                        transferred_files.append(dest_path)
                            except Exception as e:
                                logger.error(f"文件传输异常: {file_path} - {e}")
                            continue

                        # --- 异常/超限文件 ---
                        if size_mb < 0:
                            logger.info_file_only(f"[{completed_count}/{total_files}] 跳过（无法获取大小）: {file_path}")
                            continue
                        if size_mb > effective_max_size and not everything_filtered_size:
                            logger.info_file_only(f"[{completed_count}/{total_files}] 跳过（超出大小阈值 {size_mb:.2f}MB）: {file_path}")
                            continue

                        # --- 安全文件 ---
                        # 安全文件详情仅写入文件日志，减少控制台输出量
                        # 避免处理上万文件时 Windows 控制台渲染跟不上导致假死
                        if elapsed_ms <= SILENT_THRESHOLD_MS:
                            skipped_count += 1
                        else:
                            logger.info_file_only(f"[{completed_count}/{total_files}] {file_path}")
                            logger.info_file_only(f"  判定结果: [安全文件] ({elapsed_ms:.0f}ms, {size_mb:.2f}MB)")

                        pct = completed_count * 100 // total_files
                        if pct >= last_progress_pct + 5:
                            last_progress_pct = pct
                            logger.info(f"进度: {pct}% ({completed_count}/{total_files})")

                    # 检查超时的 future（基于实际开始处理时间，而非提交时间）
                    now = time.monotonic()
                    timed_out = set()
                    for f in list(pending):
                        fp = future_to_file[f]
                        if fp not in file_start_times:
                            continue
                        elapsed_sec = now - file_start_times[fp]
                        if elapsed_sec > file_timeout:
                            timed_out.add(f)
                            with file_thread_lock:
                                thread_ident = file_thread_map.get(fp)
                            soft_timed_out[fp] = (file_start_times[fp], thread_ident)
                            zombie_futures[f] = fp
                            logger.error(
                                f"文件处理超时（>{file_timeout}s），跳过: {fp}"
                            )
                            timeout_count += 1
                            completed_count += 1
                            _append_scan_log(fp)

                    # 将超时的 future 移出 pending（不再等待）
                    pending -= timed_out

                    # 检查线程空闲超时：终止卡死的线程并重新创建
                    for fp in list(soft_timed_out.keys()):
                        start_time, thread_ident = soft_timed_out[fp]
                        elapsed_sec = now - start_time
                        if elapsed_sec > thread_idle_timeout:
                            if thread_ident:
                                killed = _kill_thread(thread_ident)
                                if killed:
                                    logger.error(
                                        f"线程空闲超时（>{thread_idle_timeout}s），已发送中断信号，"
                                        f"跳过文件: {fp}"
                                    )
                                else:
                                    logger.error(
                                        f"线程空闲超时（>{thread_idle_timeout}s），线程已结束，"
                                        f"跳过文件: {fp}"
                                    )
                            else:
                                logger.error(
                                    f"线程空闲超时（>{thread_idle_timeout}s），未找到线程ID，"
                                    f"跳过文件: {fp}"
                                )
                            thread_kill_count += 1
                            del soft_timed_out[fp]

                    # 检查软超时线程是否已自然完成
                    completed_soft = []
                    for fp_check in list(soft_timed_out.keys()):
                        with file_thread_lock:
                            still_in_map = fp_check in file_thread_map
                        if not still_in_map:
                            completed_soft.append(fp_check)
                    for fp_check in completed_soft:
                        del soft_timed_out[fp_check]

                    # 清理已完成的僵尸 future（避免 "exception was never retrieved" 警告）
                    completed_zombies = {f for f in zombie_futures if f.done()}
                    for f in completed_zombies:
                        try:
                            f.result()
                        except Exception:
                            pass
                        del zombie_futures[f]

                    # 心跳日志：如果没有新完成的结果，也输出状态让用户知道程序没卡死
                    if not done and not timed_out:
                        elapsed_since_last = now - last_heartbeat
                        if elapsed_since_last >= HEARTBEAT_INTERVAL:
                            last_heartbeat = now
                            running_files = [os.path.basename(future_to_file[f]) for f in pending]
                            stuck_files = [os.path.basename(fp_hb) for fp_hb in soft_timed_out]
                            running_display = ", ".join(running_files[:3])
                            if len(running_files) > 3:
                                running_display += f" 等{len(running_files)}个"
                            parts = [f"处理中... 已完成 {completed_count}/{total_files}"]
                            if running_files:
                                parts.append(f"运行中: {running_display}")
                            if stuck_files:
                                parts.append(f"超时等待: {len(stuck_files)}个")
                            logger.info("，".join(parts))
                    else:
                        last_heartbeat = now

            # 批次结束：垃圾回收，释放内存
            gc.collect()

    except MemoryError:
        logger.error("内存不足！正在保存已完成的进度...")
    except KeyboardInterrupt:
        logger.info("用户中断，正在保存进度...")
    except Exception as e:
        logger.exception(f"检测过程异常: {e}")

    if skipped_count > 0:
        logger.info(f"其中 {skipped_count} 个文件快速通过（<{SILENT_THRESHOLD_MS}ms）")
    if timeout_count > 0:
        logger.info(f"其中 {timeout_count} 个文件处理超时（>{file_timeout}s）")
    if thread_kill_count > 0:
        logger.info(f"其中 {thread_kill_count} 个文件因线程空闲超时被中断（>{thread_idle_timeout}s）")
    if error_count > 0:
        logger.info(f"其中 {error_count} 个文件处理异常")

    # 完成还原批处理文件
    mover.finalize_restore_bat()

    logger.info("-" * 60)
    logger.info(f"检测完成，共发现 {len(transferred_files)} 个敏感文件")

    if not transferred_files:
        logger.info("无需进行后续处理")
        input("按回车键退出...")
        return

    # ----------------------------------------------------------
    # 全部检测完成后：压缩所有已复制/剪切的敏感文件
    # ----------------------------------------------------------
    logger.info("-" * 60)
    logger.info("开始压缩敏感文件")

    if work_key:
        logger.info("工号Key已设置，执行加密压缩")
        archive_path = archiver.create_archive(transferred_files, date_folder, password=work_key)
        if archive_path:
            archiver.create_password_file(date_folder, work_key)
        else:
            logger.error("加密压缩失败")
    else:
        logger.info("工号Key为空，执行普通无加密压缩")
        archive_path = archiver.create_archive(transferred_files, date_folder)

    logger.info("=" * 60)
    logger.info("全部处理完成")
    logger.info(f"扫描路径数: {len(target_paths)}")
    for p in target_paths:
        logger.info(f"  扫描路径: {p}")
    logger.info(f"敏感文件数: {len(transferred_files)}")
    logger.info(f"备份位置: {date_folder}")
    logger.info(f"运行模式: {'开发模式(仅复制)' if dev_mode else '正式模式(剪切)'}")
    if archive_path:
        logger.info(f"压缩包: {archive_path}")

    input("按回车键退出...")


if __name__ == "__main__":
    main()
