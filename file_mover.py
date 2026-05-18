import os
import shutil
from datetime import datetime
from logger import Logger


class FileMover:
    def __init__(self, backup_base_path):
        self.backup_base_path = backup_base_path
        self.logger = Logger()

    def create_date_folder(self):
        date_str = datetime.now().strftime("%Y%m%d")
        target_path = os.path.join(self.backup_base_path, date_str) if self.backup_base_path else ""

        if not target_path:
            return self._fallback_to_desktop(date_str)

        try:
            os.makedirs(target_path, exist_ok=True)
            self.logger.info(f"创建备份文件夹: {target_path}")
            return target_path
        except (OSError, PermissionError) as e:
            self.logger.warning(f"目标路径创建失败 ({target_path})，降级到桌面: {e}")
            return self._fallback_to_desktop(date_str)

    def move_files(self, file_paths, dest_folder):
        if not os.path.exists(dest_folder):
            self.logger.error(f"目标文件夹不存在: {dest_folder}")
            return []

        moved_files = []
        for src_path in file_paths:
            if not os.path.exists(src_path):
                self.logger.warning(f"源文件不存在，跳过迁移: {src_path}")
                continue
            try:
                filename = os.path.basename(src_path)
                dest_path = os.path.join(dest_folder, filename)

                dest_path = self._resolve_name_conflict(dest_path)

                shutil.copy2(src_path, dest_path)
                os.remove(src_path)
                moved_files.append(dest_path)
                self.logger.info(f"文件已迁移并删除原文件: {src_path} -> {dest_path}")
            except (IOError, PermissionError, OSError) as e:
                self.logger.error(f"文件迁移失败: {src_path} - {e}")

        return moved_files

    def _resolve_name_conflict(self, dest_path):
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
        try:
            os.makedirs(target_path, exist_ok=True)
            self.logger.info(f"降级到桌面创建备份文件夹: {target_path}")
            return target_path
        except (OSError, PermissionError) as e:
            self.logger.error(f"桌面路径创建也失败: {e}")
            alt_path = os.path.join(os.getcwd(), date_str)
            os.makedirs(alt_path, exist_ok=True)
            self.logger.info(f"最终降级到当前目录: {alt_path}")
            return alt_path
