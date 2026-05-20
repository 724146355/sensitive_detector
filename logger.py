import logging
import sys
import time
from datetime import datetime


class ConsoleFilter(logging.Filter):
    """控制台日志过滤器：拦截标记为 file_only 的日志，不在控制台显示

    当程序处理上万文件时，安全文件的逐条详情输出量巨大，
    导致 Windows 控制台渲染线程跟不上，表现为"卡住不动"。
    通过 file_only 标记，安全文件详情只写文件日志，控制台仅显示关键信息。
    """
    def filter(self, record):
        return not getattr(record, 'file_only', False)


class SmartFlushStreamHandler(logging.StreamHandler):
    """智能刷新 StreamHandler：平衡实时性和性能

    刷新策略：
    - WARNING/ERROR 级别：立即刷新（关键信息需要及时显示）
    - INFO 级别：增量刷新（每 FLUSH_INTERVAL_SEC 秒或每 FLUSH_MESSAGE_COUNT 条消息）
    - 当检测到用户输入等待时（如 input()），自动刷新缓冲区
    """
    FLUSH_INTERVAL_SEC = 0.5  # 刷新时间间隔
    FLUSH_MESSAGE_COUNT = 10  # 消息计数阈值

    def __init__(self, stream=None):
        super().__init__(stream)
        self._flush_counter = 0
        self._last_flush_time = time.monotonic()

    def emit(self, record):
        super().emit(record)
        
        # WARNING/ERROR 级别立即刷新
        if record.levelno >= logging.WARNING:
            self.flush()
            self._flush_counter = 0
            self._last_flush_time = time.monotonic()
            return

        # INFO 级别：增量刷新
        self._flush_counter += 1
        now = time.monotonic()
        
        # 满足任一条件则刷新
        if (self._flush_counter >= self.FLUSH_MESSAGE_COUNT or 
            now - self._last_flush_time >= self.FLUSH_INTERVAL_SEC):
            self.flush()
            self._flush_counter = 0
            self._last_flush_time = now

    def force_flush(self):
        """强制刷新缓冲区（用于用户输入前）"""
        if self._flush_counter > 0:
            self.flush()
            self._flush_counter = 0
            self._last_flush_time = time.monotonic()


class Logger:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._initialized = True

        self.logger = logging.getLogger("SensitiveDetector")
        self.logger.setLevel(logging.DEBUG)
        self.logger.propagate = False

        formatter = logging.Formatter(
            "[%(asctime)s] [%(levelname)s] %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S"
        )

        self.console_handler = SmartFlushStreamHandler(sys.stdout)
        self.console_handler.setLevel(logging.INFO)
        self.console_handler.setFormatter(formatter)
        self.console_handler.addFilter(ConsoleFilter())

        file_handler = logging.FileHandler(
            f"sensitive_detector_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log",
            encoding="utf-8"
        )
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(formatter)

        self.logger.addHandler(self.console_handler)
        self.logger.addHandler(file_handler)

    def debug(self, message):
        self.logger.debug(message)

    def info(self, message):
        self.logger.info(message)

    def warning(self, message):
        self.logger.warning(message)

    def error(self, message):
        self.logger.error(message)

    def info_file_only(self, message):
        """仅写入文件日志，不在控制台输出

        用于安全文件/跳过文件等高频但低价值的详情输出，
        减少控制台输出量，避免 Windows 控制台因渲染不过来而假死。
        """
        self.logger.info(message, extra={'file_only': True})

    def exception(self, message):
        self.logger.exception(message)

    def flush(self):
        """强制刷新控制台输出缓冲区

        在等待用户输入前调用，确保所有日志已显示到终端
        """
        if hasattr(self, 'console_handler'):
            self.console_handler.force_flush()
        sys.stdout.flush()
        sys.stderr.flush()
