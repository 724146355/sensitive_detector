"""
Everything SDK 集成模块
通过 Everything 搜索引擎实现毫秒级文件查找替代 os.walk

依赖: Everything 软件需已安装并运行（下载: https://www.voidtools.com）
工作原理: 通过 ctypes 加载 Everything DLL，利用其索引数据库快速搜索文件
回退方案: 当 Everything 不可用时自动返回 None，由调用方决定后续处理
"""
import ctypes
import os
import sys
import platform
from ctypes import wintypes
from logger import Logger


# ============================================================
# Everything SDK 常量定义
# ============================================================

# 请求标志位
EVERYTHING_REQUEST_FILE_NAME = 0x00000001
EVERYTHING_REQUEST_PATH = 0x00000002
EVERYTHING_REQUEST_FULL_PATH_AND_FILE_NAME = 0x00000004
EVERYTHING_REQUEST_SIZE = 0x00000010

# 错误码
EVERYTHING_ERROR_NO_ERROR = 0
EVERYTHING_ERROR_MEMORY = 1
EVERYTHING_ERROR_IPC = 2
EVERYTHING_ERROR_REGISTERCLASS = 3
EVERYTHING_ERROR_CREATEWINDOW = 4
EVERYTHING_ERROR_CREATETHREAD = 5
EVERYTHING_ERROR_INVALIDINDEX = 6
EVERYTHING_ERROR_INVALIDCALL = 7

ERROR_MESSAGES = {
    EVERYTHING_ERROR_NO_ERROR: "正常",
    EVERYTHING_ERROR_MEMORY: "内存不足",
    EVERYTHING_ERROR_IPC: "Everything 服务未运行（未启动或未安装）",
    EVERYTHING_ERROR_REGISTERCLASS: "窗口类注册失败",
    EVERYTHING_ERROR_CREATEWINDOW: "窗口创建失败",
    EVERYTHING_ERROR_CREATETHREAD: "线程创建失败",
    EVERYTHING_ERROR_INVALIDINDEX: "无效索引",
    EVERYTHING_ERROR_INVALIDCALL: "无效调用",
}


class EverythingScanner:
    """封装 Everything SDK 的文件搜索功能

    使用示例:
        scanner = EverythingScanner()
        if scanner.available:
            files = scanner.find_files(
                paths=["C:\\\\", "D:\\\\"],
                extensions={".doc", ".docx", ".xlsx"},
                max_size_bytes=100 * 1024 * 1024
            )
    """

    def __init__(self):
        self.logger = Logger()
        self._dll = None
        self._available = False
        self._has_is_folder_func = False  # 标记是否有 Everything_IsFolderResult 函数
        self._has_is_file_func = False    # 标记是否有 Everything_IsFileResult 函数
        self._has_get_size_func = False   # 标记是否有 Everything_GetResultSize 函数
        self._has_match_path_func = False # 标记是否有 Everything_SetMatchPath 函数
        self._load_dll()

    # ----------------------------------------------------------
    #  DLL 加载与初始化
    # ----------------------------------------------------------

    def _load_dll(self):
        """加载 Everything SDK DLL（增强版）"""
        if platform.system() != "Windows":
            self.logger.debug("EverythingScanner: 非 Windows 系统，不可用")
            return

        dll_name = "Everything.dll"
        
        # 检测 Python 位数
        is_64bit = sys.maxsize > 2**32
        bitness_str = "64位" if is_64bit else "32位"
        
        # 调试信息
        self.logger.debug(f"=== Everything DLL 加载诊断 ===")
        self.logger.debug(f"系统: {platform.system()} {platform.release()}")
        self.logger.debug(f"Python: {sys.version.split()[0]} ({bitness_str})")
        self.logger.debug(f"DLL 文件名: {dll_name}")

        search_dirs = self._get_search_dirs()
        self.logger.debug(f"搜索路径数: {len(search_dirs)}")

        # 常见 Windows 错误码映射
        error_codes = {
            126: "找不到指定的模块（DLL文件缺失或依赖缺失）",
            127: "找不到指定的程序入口点（DLL版本不兼容）",
            193: "不是有效的 Win32 应用程序（位数不匹配）",
            5: "拒绝访问（权限不足）",
        }

        for dir_path in search_dirs:
            dll_path = os.path.join(dir_path, dll_name) if dir_path else dll_name
            
            # 确保路径规范化
            if dir_path:
                dll_path = os.path.abspath(dll_path)
                if not os.path.exists(dll_path):
                    self.logger.debug(f"  跳过: {dll_path}（文件不存在）")
                    continue
            
            self.logger.debug(f"  尝试加载: {dll_path}")
            
            try:
                # 尝试 WinDLL（stdcall 调用约定）
                self._dll = ctypes.WinDLL(dll_path)
                self._setup_funcs()
                self._available = True
                self.logger.info(f"Everything 引擎已加载 ({dll_path})")
                return
                
            except OSError as e:
                err_code = e.winerror
                err_msg = error_codes.get(err_code, str(e))
                self.logger.warning(f"DLL 加载失败 [{err_code}]: {err_msg}")
                self.logger.warning(f"  路径: {dll_path}")
                
                # 位数不匹配的特殊提示
                if err_code == 193:
                    self.logger.warning(f"  提示: 当前 Python 是 {bitness_str}，请确保 DLL 位数匹配")
                    
            except Exception as e:
                self.logger.warning(f"DLL 加载异常: {type(e).__name__}: {e}")
                self.logger.warning(f"  路径: {dll_path}")

        self.logger.info("Everything 未安装或 SDK DLL 未找到，将使用 Python os.walk 回退方案")

    def _get_search_dirs(self):
        """获取 DLL 搜索路径列表"""
        dirs = []

        # 1) PyInstaller 打包后的临时解压目录（优先级最高）
        if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
            dirs.append(sys._MEIPASS)

        # 2) 与 EXE/脚本同目录
        if getattr(sys, 'frozen', False):
            dirs.append(os.path.dirname(sys.executable))
        else:
            dirs.append(os.path.dirname(os.path.abspath(__file__)))

        # 3) Everything 标准安装目录
        for env_var in ["ProgramFiles", "ProgramFiles(x86)"]:
            pf = os.environ.get(env_var, "")
            if pf:
                everything_dir = os.path.join(pf, "Everything")
                if os.path.exists(everything_dir):
                    dirs.append(everything_dir)

        # 4) 系统 PATH（让 WinDLL 自动搜索）
        dirs.append("")

        return dirs

    def _setup_funcs(self):
        """配置 DLL 函数签名（显式声明参数和返回类型）

        重要：函数名必须与 Everything SDK 官方文档一致！
        - Everything_IsFolderResult（不是 Everything_IsFolder）
        - Everything_IsFileResult
        - Everything_GetResultSize 需要传指针参数
        """
        dll = self._dll

        # void Everything_SetSearchW(LPCWSTR lpSearchString)
        dll.Everything_SetSearchW.argtypes = [wintypes.LPCWSTR]
        dll.Everything_SetSearchW.restype = None

        # void Everything_SetRequestFlags(DWORD dwRequestFlags)
        dll.Everything_SetRequestFlags.argtypes = [wintypes.DWORD]
        dll.Everything_SetRequestFlags.restype = None

        # void Everything_SetMatchPath(BOOL bEnable)
        # 重要：默认 Match Path = OFF，路径搜索词只匹配文件名不匹配路径
        # 必须启用才能让 "C:\\" 这样的路径过滤生效
        if hasattr(dll, 'Everything_SetMatchPath'):
            dll.Everything_SetMatchPath.argtypes = [wintypes.BOOL]
            dll.Everything_SetMatchPath.restype = None
            self._has_match_path_func = True
            self.logger.debug("DLL 支持 Everything_SetMatchPath 函数")
        else:
            self._has_match_path_func = False
            self.logger.warning("DLL 不支持 Everything_SetMatchPath，将使用 path: 修饰符替代")

        # BOOL Everything_QueryW(BOOL bWait)
        dll.Everything_QueryW.argtypes = [wintypes.BOOL]
        dll.Everything_QueryW.restype = wintypes.BOOL

        # DWORD Everything_GetNumResults(void)
        dll.Everything_GetNumResults.argtypes = []
        dll.Everything_GetNumResults.restype = wintypes.DWORD

        # DWORD Everything_GetResultFullPathNameW(DWORD nIndex, LPWSTR lpString, DWORD nMaxCount)
        dll.Everything_GetResultFullPathNameW.argtypes = [
            wintypes.DWORD,
            wintypes.LPWSTR,
            wintypes.DWORD,
        ]
        dll.Everything_GetResultFullPathNameW.restype = wintypes.DWORD

        # BOOL Everything_GetResultSize(DWORD dwIndex, LARGE_INTEGER *lpSize)
        # 重要：此函数通过指针参数返回大小值，而不是通过返回值！
        # 签名: BOOL Everything_GetResultSize(DWORD index, LARGE_INTEGER *lpSize)
        if hasattr(dll, 'Everything_GetResultSize'):
            dll.Everything_GetResultSize.argtypes = [
                wintypes.DWORD,
                ctypes.POINTER(ctypes.c_ulonglong)
            ]
            dll.Everything_GetResultSize.restype = wintypes.BOOL
            self._has_get_size_func = True
            self.logger.debug("DLL 支持 Everything_GetResultSize 函数")
        else:
            self._has_get_size_func = False
            self.logger.warning("DLL 版本较旧，不支持 Everything_GetResultSize 函数，将跳过大小过滤")

        # BOOL Everything_IsFolderResult(DWORD index)
        # 重要：正确函数名是 Everything_IsFolderResult，不是 Everything_IsFolder！
        if hasattr(dll, 'Everything_IsFolderResult'):
            dll.Everything_IsFolderResult.argtypes = [wintypes.DWORD]
            dll.Everything_IsFolderResult.restype = wintypes.BOOL
            self._has_is_folder_func = True
            self.logger.debug("DLL 支持 Everything_IsFolderResult 函数")
        else:
            self._has_is_folder_func = False
            self.logger.warning("DLL 版本较旧，不支持 Everything_IsFolderResult 函数，将使用路径判断方式")

        # BOOL Everything_IsFileResult(DWORD index)
        if hasattr(dll, 'Everything_IsFileResult'):
            dll.Everything_IsFileResult.argtypes = [wintypes.DWORD]
            dll.Everything_IsFileResult.restype = wintypes.BOOL
            self._has_is_file_func = True
            self.logger.debug("DLL 支持 Everything_IsFileResult 函数")
        else:
            self._has_is_file_func = False
            self.logger.debug("DLL 不支持 Everything_IsFileResult 函数，将使用 IsFolderResult 替代")

        # void Everything_Reset(void)
        if hasattr(dll, 'Everything_Reset'):
            dll.Everything_Reset.argtypes = []
            dll.Everything_Reset.restype = None

        # DWORD Everything_GetLastError(void)
        dll.Everything_GetLastError.argtypes = []
        dll.Everything_GetLastError.restype = wintypes.DWORD

    # ----------------------------------------------------------
    #  公共属性
    # ----------------------------------------------------------

    @property
    def available(self):
        """Everything 是否可用"""
        return self._available

    # ----------------------------------------------------------
    #  核心搜索方法
    # ----------------------------------------------------------

    def find_files(self, paths, extensions, max_size_bytes=None):
        """使用 Everything 引擎搜索文件

        Args:
            paths: 搜索路径列表，例如 ['C:\\', 'D:\\Users\\']
                   传入 [] 或 ['ALL'] 则搜索所有已索引的路径
            extensions: 文件扩展名集合，例如 {'.doc', '.docx', '.xlsx'}
                       注意扩展名中的点号会被自动处理
            max_size_bytes: 最大文件大小（字节），超过此大小的文件会被过滤
                           None 表示不限制

        Returns:
            list[str]: 匹配文件的完整路径列表
            None: Everything 不可用或查询失败（调用方应回退到 os.walk）
                  返回 None 而非空列表以区分"Everything 不可用"和"没有匹配文件"
        """
        if not self._available:
            return None

        self.logger.info("-" * 60)
        self.logger.info("使用 Everything 高速搜索引擎进行文件扫描...")
        self.logger.info("  Everything 利用 NTFS 索引数据库，扫描速度极快")

        # 构建扩展名查询 (ext:doc;docx;xlsx)
        ext_parts = [ext.lstrip(".").lower() for ext in extensions]
        ext_str = ";".join(ext_parts)
        self.logger.info(f"  目标扩展名: {', '.join('.' + e for e in ext_parts)}")

        # 判断是否为全盘扫描
        scan_all = self._is_all_drives(paths)

        all_results = []
        total_query = 1 if scan_all else len(paths)
        all_failed = True

        for idx, path in enumerate(paths, 1):
            try:
                self.logger.info(f"  [{idx}/{total_query}] Everything 搜索: {path or '<所有路径>'}")
                results = self._execute_query(path, ext_str, max_size_bytes)
                if results is not None:
                    all_failed = False
                    if results:
                        all_results.extend(results)
                        self.logger.info(f"    → 找到 {len(results)} 个文件")
                    else:
                        self.logger.info(f"    → 未找到匹配文件")
                else:
                    self.logger.warning(f"    → 查询失败，将回退到 Python 扫描")
            except Exception as e:
                self.logger.error(f"  Everything 搜索出错 ({path}): {e}")

        if scan_all and len(all_results) > 0:
            self.logger.info(f"  去重中...")
            # 使用 dict.fromkeys 保持顺序并去重
            all_results = list(dict.fromkeys(all_results))

        final_count = len(all_results)

        if all_failed:
            self.logger.warning("Everything 扫描：所有查询均失败")
            return None

        self.logger.info(f"Everything 扫描完成，共发现 {final_count} 个待检测文件")
        for f in all_results:
            self.logger.info(f"  待检测: {f}")
        self.logger.info("-" * 60)

        return all_results

    # ----------------------------------------------------------
    #  内部搜索逻辑
    # ----------------------------------------------------------

    def _is_all_drives(self, paths):
        """判断是否为全盘扫描模式（多个路径视为全盘）"""
        if len(paths) > 1:
            return True
        if len(paths) == 1:
            p = paths[0].rstrip(":\\/").upper()
            # 单个驱动器字母也视为全盘
            if len(p) == 1 and p.isalpha():
                return True  # 形式上单驱动器，但实际上也可能是全盘搜索
        return False

    def _normalize_path(self, path):
        """标准化路径为 Everything 可识别的格式

        - C: → C:\\
        - C:/Users → C:\\Users\\
        - 空 → 空（搜索全部）
        """
        if not path:
            return ""

        normalized = path.replace("/", "\\")

        # 如果是驱动器根目录（如 C: 或 C:\\）
        if len(normalized.rstrip("\\")) <= 2 and normalized.rstrip("\\").endswith(":"):
            return normalized.rstrip("\\") + "\\"

        # 普通路径，确保末尾有反斜杠
        normalized = normalized.rstrip("\\") + "\\"
        return normalized

    def _execute_query(self, path, ext_str, max_size_bytes):
        """执行单次 Everything 查询
    
        Returns:
            list[str]: 文件路径列表
            None: 查询失败（Everything 服务未运行等），应由调用方触发回退
        """
        dll = self._dll
    
        # 重置查询状态（防止上一次查询的设置影响本次）
        if hasattr(dll, 'Everything_Reset'):
            dll.Everything_Reset()
    
        # 构建查询字符串
        # Everything 语法: "C:\\Path\\" ext:doc;docx;xlsx
        # 当 Everything_SetMatchPath 不可用时，使用 path: 修饰符强制路径匹配
        normalized_path = self._normalize_path(path)
        query_parts = [f"ext:{ext_str}"]
        if normalized_path:
            if self._has_match_path_func:
                # SetMatchPath 可用：路径过滤通过全局路径匹配生效
                query_parts.insert(0, f'"{normalized_path}"')
            else:
                # SetMatchPath 不可用：使用 path: 修饰符强制该搜索词匹配路径
                query_parts.insert(0, f'path:"{normalized_path}"')
        query = " ".join(query_parts)
    
        self.logger.debug(f"  Everything 查询: {query}")
    
        # --- 执行查询 ---
        try:
            dll.Everything_SetSearchW(query)
    
            # 关键：启用路径匹配！
            # SDK 默认 Match Path = OFF，搜索词只匹配文件名
            # 必须启用才能让 "C:\\" 这样的路径过滤生效，否则所有路径搜索返回0结果
            if self._has_match_path_func:
                dll.Everything_SetMatchPath(True)
    
            # 根据 DLL 支持的功能动态设置请求标志
            request_flags = EVERYTHING_REQUEST_FULL_PATH_AND_FILE_NAME
            if self._has_get_size_func:
                request_flags |= EVERYTHING_REQUEST_SIZE
    
            dll.Everything_SetRequestFlags(request_flags)
    
            if not dll.Everything_QueryW(True):
                error_code = dll.Everything_GetLastError()
                error_msg = ERROR_MESSAGES.get(error_code, f"未知错误 ({error_code})")
                self.logger.warning(f"  Everything 查询失败: {error_msg}")
                return None  # 返回 None 表示查询失败，应由调用方触发回退
        except Exception as e:
            self.logger.error(f"  Everything 查询异常: {type(e).__name__}: {e}")
            self.logger.warning(f"  可能原因: DLL 版本不兼容或函数签名不匹配")
            return None
    
        num_results = dll.Everything_GetNumResults()
        self.logger.debug(f"  Everything 原始结果数: {num_results}")
    
        if num_results == 0:
            return []
    
        # --- 收集结果 ---
        results = []
        # 每处理 N 个文件打一次进度日志（避免刷屏）
        progress_interval = max(10000, num_results // 5) if num_results > 10000 else 0
        oversized_count = 0
    
        # 预分配 buffer，循环内复用，避免每个结果都重新分配内存
        buf = ctypes.create_unicode_buffer(4096)  # 远大于 MAX_PATH，支持长路径
    
        for i in range(num_results):
            try:
                # 获取完整路径 (UTF-16)，复用 buffer
                dll.Everything_GetResultFullPathNameW(i, buf, 4096)
                full_path = buf.value
    
                if not full_path:
                    continue
    
                # 跳过目录：优先使用 IsFileResult/IsFolderResult
                if self._has_is_file_func:
                    # 最可靠的方式：只保留文件结果
                    if not dll.Everything_IsFileResult(i):
                        continue
                elif self._has_is_folder_func:
                    # 使用 IsFolderResult 排除文件夹
                    if dll.Everything_IsFolderResult(i):
                        continue
                else:
                    # 旧版本 DLL：通过路径末尾是否有反斜杠判断是否为文件夹
                    if full_path.endswith('\\'):
                        continue
    
                # 大小过滤（可选，向后兼容）
                if max_size_bytes is not None and self._has_get_size_func:
                    file_size = ctypes.c_ulonglong(0)
                    if dll.Everything_GetResultSize(i, ctypes.byref(file_size)):
                        if file_size.value > max_size_bytes:
                            oversized_count += 1
                            continue
                    else:
                        # 获取大小失败，跳过大小过滤，保留该文件
                        self.logger.debug(f"  获取文件大小失败，跳过大小过滤: {full_path}")
    
                results.append(full_path)
            except Exception as e:
                self.logger.debug(f"  处理第 {i} 个结果时异常: {type(e).__name__}: {e}")
                continue
    
            # 进度日志
            if progress_interval > 0 and (i + 1) % progress_interval == 0:
                pct = min((i + 1) * 100 // num_results, 100)
                self.logger.info(f"  Everything 扫描进度: {pct}% ({i + 1}/{num_results})")
    
        # 统计信息
        if oversized_count > 0:
            self.logger.debug(f"  Everything 过滤了 {oversized_count} 个超大文件")
    
        return results
