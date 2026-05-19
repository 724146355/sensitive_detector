import os
import shutil
from datetime import datetime
from logger import Logger


class FileMover:
    def __init__(self, backup_base_path, dev_mode=False):
        self.backup_base_path = backup_base_path
        self.dev_mode = dev_mode  # True=只复制, False=剪切(复制+删除原文件)
        self.logger = Logger()

    def create_date_folder(self):
        """创建日期文件夹，如果已存在则追加 _1, _2, ... 编号

        例如：
          首次: ./sensitive_backup/20260519/
          再次: ./sensitive_backup/20260519_1/
          第三: ./sensitive_backup/20260519_2/
        """
        date_str = datetime.now().strftime("%Y%m%d")

        if not self.backup_base_path:
            return self._fallback_to_desktop(date_str)

        # 尝试创建日期文件夹，若已存在则追加编号
        target_path = os.path.join(self.backup_base_path, date_str)
        if not os.path.exists(target_path):
            try:
                os.makedirs(target_path, exist_ok=True)
                self.logger.info(f"创建备份文件夹: {target_path}")
                return target_path
            except (OSError, PermissionError) as e:
                self.logger.warning(f"目标路径创建失败 ({target_path})，降级到桌面: {e}")
                return self._fallback_to_desktop(date_str)

        # 文件夹已存在，追加编号 _1, _2, ...
        counter = 1
        while True:
            numbered_path = os.path.join(self.backup_base_path, f"{date_str}_{counter}")
            if not os.path.exists(numbered_path):
                try:
                    os.makedirs(numbered_path, exist_ok=True)
                    self.logger.info(f"创建备份文件夹(编号): {numbered_path}")
                    return numbered_path
                except (OSError, PermissionError) as e:
                    self.logger.warning(f"目标路径创建失败 ({numbered_path})，降级到桌面: {e}")
                    return self._fallback_to_desktop(date_str)
            counter += 1

    def transfer_file(self, src_path, dest_folder):
        """单个文件传输：根据 dev_mode 决定是复制还是剪切

        Args:
            src_path: 源文件路径
            dest_folder: 目标文件夹

        Returns:
            str: 目标文件路径（成功时），None（失败时）
        """
        if not os.path.exists(dest_folder):
            self.logger.error(f"目标文件夹不存在: {dest_folder}")
            return None

        if not os.path.exists(src_path):
            self.logger.warning(f"源文件不存在，跳过: {src_path}")
            return None

        try:
            filename = os.path.basename(src_path)
            dest_path = os.path.join(dest_folder, filename)
            dest_path = self._resolve_name_conflict(dest_path)

            shutil.copy2(src_path, dest_path)

            if self.dev_mode:
                # dev 模式：只复制，不删除原文件
                self.logger.info(f"文件已复制(开发模式): {src_path} -> {dest_path}")
            else:
                # 正式模式：复制后删除原文件（剪切）
                try:
                    os.remove(src_path)
                    self.logger.info(f"文件已剪切: {src_path} -> {dest_path}")
                except (OSError, PermissionError) as e:
                    self.logger.warning(f"原文件删除失败(已复制): {src_path} - {e}")

            return dest_path
        except (IOError, PermissionError, OSError) as e:
            self.logger.error(f"文件传输失败: {src_path} - {e}")
            return None

    def move_files(self, file_paths, dest_folder):
        """批量文件传输（兼容旧接口）"""
        if not os.path.exists(dest_folder):
            self.logger.error(f"目标文件夹不存在: {dest_folder}")
            return []

        moved_files = []
        for src_path in file_paths:
            result = self.transfer_file(src_path, dest_folder)
            if result:
                moved_files.append(result)

        return moved_files

    def _resolve_name_conflict(self, dest_path):
        """解决目标文件名冲突，追加 _1, _2, ... 编号"""
        if not os.path.exists(dest_path):
            return dest_path
        base, ext = os.path.splitext(dest_path)
        counter = 1
        while True:
            new_path = f"{base}_{counter}{ext}"
            if not os.path.exists(new_path):
                return new_path
            counter += 1

    def _fallback_to_desktop(self, date_str):
        """降级到桌面/当前目录创建文件夹"""
        desktop = os.path.join(os.path.expanduser("~"), "Desktop")
        if not os.path.exists(desktop):
            desktop = os.path.join(os.path.expanduser("~"), "桌面")
        if not os.path.exists(desktop):
            desktop = os.environ.get("USERPROFILE", "C:\\")
            desktop = os.path.join(desktop, "Desktop")
        if not os.path.exists(desktop):
            try:
                desktop = os.environ.get("TEMP", "C:\\temp")
            except Exception:
                desktop = "C:\\"

        target_path = os.path.join(desktop, date_str)
        if os.path.exists(target_path):
            counter = 1
            while True:
                numbered_path = os.path.join(desktop, f"{date_str}_{counter}")
                if not os.path.exists(numbered_path):
                    target_path = numbered_path
                    break
                counter += 1

        try:
            os.makedirs(target_path, exist_ok=True)
            self.logger.info(f"降级创建备份文件夹: {target_path}")
            return target_path
        except (OSError, PermissionError) as e:
            self.logger.error(f"桌面路径创建也失败: {e}")
            alt_path = os.path.join(os.getcwd(), date_str)
            if os.path.exists(alt_path):
                counter = 1
                while True:
                    numbered_alt = os.path.join(os.getcwd(), f"{date_str}_{counter}")
                    if not os.path.exists(numbered_alt):
                        alt_path = numbered_alt
                        break
                    counter += 1
            os.makedirs(alt_path, exist_ok=True)
            self.logger.info(f"最终降级到当前目录: {alt_path}")
            return alt_path
