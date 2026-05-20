import logging
import sys
from datetime import datetime


class ConsoleFilter(logging.Filter):
    """控制台日志过滤器：拦截标记为 file_only 的日志，不在控制台显示

    当程序处理上万文件时，安全文件的逐条详情输出量巨大，
    导致 Windows 控制台渲染线程跟不上，表现为"卡住不动"。
    通过 file_only 标记，安全文件详情只写文件日志，控制台仅显示关键信息。
    """
    def filter(self, record):
        return not getattr(record, 'file_only', False)


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

        formatter = logging.Formatter(
            "[%(asctime)s] [%(levelname)s] %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S"
        )

        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(logging.INFO)
        console_handler.setFormatter(formatter)
        console_handler.addFilter(ConsoleFilter())

        file_handler = logging.FileHandler(
            f"sensitive_detector_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log",
            encoding="utf-8"
        )
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(formatter)

        self.logger.addHandler(console_handler)
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
