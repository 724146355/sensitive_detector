import os
import shutil
import threading
from datetime import datetime
from logger import Logger


class FileMover:
    def __init__(self, backup_base_path, dev_mode=False):
        self.backup_base_path = backup_base_path
        self.dev_mode = dev_mode  # True=只复制, False=剪切(复制+删除原文件)
        self.logger = Logger()
        self.bat_file_path = None
        self.bat_lock = threading.Lock()
        self._bat_counter = 0

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

            # 生成还原批处理命令
            self._append_restore_command(src_path, dest_path)

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

    def init_restore_bat(self, date_folder):
        """初始化还原批处理文件，在日期文件夹中创建 restore.bat"""
        self.bat_file_path = os.path.join(date_folder, "restore.bat")
        self._bat_counter = 0
        try:
            with open(self.bat_file_path, "w", encoding="utf-8") as f:
                f.write("@echo off\n")
                f.write("chcp 65001 >nul\n")
                f.write("echo ============================================\n")
                f.write("echo   敏感文件还原批处理\n")
                f.write("echo ============================================\n")
                f.write("echo.\n")
                if self.dev_mode:
                    f.write("echo 运行模式: 开发模式(原文件仍保留在原位置)\n")
                else:
                    f.write("echo 运行模式: 正式模式(原文件已被剪切)\n")
                f.write("echo.\n")
                f.write("echo 开始还原敏感文件到原始路径...\n")
                f.write("echo.\n")
            self.logger.info(f"已创建还原批处理文件: {self.bat_file_path}")
        except (IOError, OSError) as e:
            self.logger.warning(f"批处理文件创建失败: {e}")
            self.bat_file_path = None

    def _append_restore_command(self, src_path, dest_path):
        """向批处理文件追加一条还原命令

        Args:
            src_path: 文件原始路径（还原目标，文件名保持原样）
            dest_path: 文件在备份目录中的路径（还原来源，可能含_1/_2编号）
        """
        if not self.bat_file_path:
            return

        original_dir = os.path.dirname(src_path).replace("/", "\\")
        dest_win = dest_path.replace("/", "\\")
        src_win = src_path.replace("/", "\\")
        original_name = os.path.basename(src_path)
        backup_name = os.path.basename(dest_path)

        with self.bat_lock:
            self._bat_counter += 1
            try:
                with open(self.bat_file_path, "a", encoding="utf-8") as f:
                    f.write(f'if not exist "{original_dir}" mkdir "{original_dir}"\n')
                    f.write(f'move /Y "{dest_win}" "{src_win}"\n')
                    if backup_name != original_name:
                        f.write(f'echo   [{self._bat_counter}] {backup_name} -^> {original_name} ({src_win})\n')
                    else:
                        f.write(f'echo   [{self._bat_counter}] {original_name} -^> {src_win}\n')
            except (IOError, OSError) as e:
                self.logger.warning(f"批处理文件写入失败: {e}")

    def finalize_restore_bat(self):
        """完成还原批处理文件（添加结尾信息）"""
        if not self.bat_file_path:
            return

        try:
            with self.bat_lock:
                with open(self.bat_file_path, "a", encoding="utf-8") as f:
                    f.write("echo.\n")
                    f.write(f"echo 还原完成! 共 {self._bat_counter} 个文件\n")
                    f.write("echo.\n")
                    f.write("pause\n")
        except (IOError, OSError) as e:
            self.logger.warning(f"批处理文件结尾写入失败: {e}")

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
