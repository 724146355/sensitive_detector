import os
import zipfile
from datetime import datetime
from logger import Logger


class Archiver:
    def __init__(self):
        self.logger = Logger()

    def create_archive(self, file_paths, output_dir, password=None):
        if not file_paths:
            self.logger.warning("没有文件需要压缩")
            return None

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        archive_name = f"sensitive_files_{timestamp}.zip"
        archive_path = os.path.join(output_dir, archive_name)

        try:
            if password:
                self._create_encrypted_zip(file_paths, archive_path, password)
            else:
                self._create_plain_zip(file_paths, archive_path)

            self.logger.info(f"压缩包已创建: {archive_path}")
            return archive_path
        except Exception as e:
            self.logger.error(f"压缩失败: {e}")
            return None

    def _create_plain_zip(self, file_paths, archive_path):
        with zipfile.ZipFile(archive_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for file_path in file_paths:
                if os.path.exists(file_path):
                    arcname = os.path.basename(file_path)
                    zf.write(file_path, arcname)
                    self.logger.debug(f"  添加到压缩包: {arcname}")

    def _create_encrypted_zip(self, file_paths, archive_path, password):
        if isinstance(password, str):
            password = password.encode("utf-8")

        try:
            import pyzipper
            with pyzipper.AESZipFile(archive_path, "w", compression=pyzipper.ZIP_DEFLATED, encryption=pyzipper.WZ_AES) as zf:
                zf.setpassword(password)
                for file_path in file_paths:
                    if os.path.exists(file_path):
                        arcname = os.path.basename(file_path)
                        zf.write(file_path, arcname)
                        self.logger.debug(f"  加密添加到压缩包: {arcname}")
        except ImportError:
            self.logger.warning("pyzipper 库不可用，回退到标准 zipfile 加密模式")
            with zipfile.ZipFile(archive_path, "w", zipfile.ZIP_DEFLATED) as zf:
                for file_path in file_paths:
                    if os.path.exists(file_path):
                        arcname = os.path.basename(file_path)
                        zf.write(file_path, arcname)
                        self.logger.debug(f"  添加到压缩包(无加密): {arcname}")

    def create_password_file(self, output_dir, password):
        try:
            file_path = os.path.join(output_dir, "压缩包密码说明.txt")
            with open(file_path, "w", encoding="utf-8") as f:
                f.write("敏感文件加密压缩包密码说明\n")
                f.write("=" * 40 + "\n\n")
                f.write(f"生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write(f"加密密码: {password}\n\n")
                f.write("请妥善保管此密码，解压时需要输入此密码。\n")
            self.logger.info(f"密码说明文件已创建: {file_path}")
            return file_path
        except (IOError, PermissionError) as e:
            self.logger.error(f"密码文件创建失败: {e}")
            return None
