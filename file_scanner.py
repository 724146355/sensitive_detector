import os
import csv
import io
from logger import Logger

SUPPORTED_EXTENSIONS = {
    ".doc", ".docx",
    ".xls", ".xlsx", ".csv",
    ".ppt", ".pptx",
    ".txt", ".md", ".log",
    ".pdf",
    ".wps", ".et", ".dps"
}


class FileScanner:
    def __init__(self, max_file_size_bytes):
        self.max_file_size_bytes = max_file_size_bytes
        self.logger = Logger()

    def scan_directory(self, root_dir):
        if not os.path.exists(root_dir):
            self.logger.error(f"扫描目录不存在: {root_dir}")
            return []

        target_files = []
        for dirpath, _, filenames in os.walk(root_dir):
            for filename in filenames:
                ext = os.path.splitext(filename)[1].lower()
                if ext in SUPPORTED_EXTENSIONS:
                    full_path = os.path.join(dirpath, filename)
                    target_files.append(full_path)
                else:
                    self.logger.debug(f"跳过不支持的文件类型: {os.path.join(dirpath, filename)}")

        self.logger.info(f"扫描到 {len(target_files)} 个待检测文件")
        for f in target_files:
            self.logger.info(f"  待检测: {f}")
        return target_files

    def get_file_size_mb(self, file_path):
        try:
            size_bytes = os.path.getsize(file_path)
            return size_bytes / (1024 * 1024)
        except OSError:
            return -1

    def is_oversized(self, file_path):
        size_mb = self.get_file_size_mb(file_path)
        if size_mb < 0:
            self.logger.warning(f"无法获取文件大小: {file_path}")
            return True, -1
        is_over = size_mb > self.max_file_size_bytes
        if is_over:
            self.logger.info(f"文件超过大小阈值 ({size_mb:.2f}MB > {self.max_file_size_bytes}MB)，跳过: {file_path}")
        return is_over, size_mb

    def extract_text(self, file_path):
        ext = os.path.splitext(file_path)[1].lower()
        try:
            if ext in (".txt", ".md", ".log"):
                return self._read_plain_text(file_path)
            elif ext == ".docx":
                return self._read_docx(file_path)
            elif ext == ".doc":
                return self._read_doc(file_path)
            elif ext == ".xlsx":
                return self._read_xlsx(file_path)
            elif ext == ".xls":
                return self._read_xls(file_path)
            elif ext == ".csv":
                return self._read_csv(file_path)
            elif ext == ".pptx":
                return self._read_pptx(file_path)
            elif ext == ".ppt":
                return self._read_ppt(file_path)
            elif ext == ".pdf":
                return self._read_pdf(file_path)
            elif ext == ".wps":
                return self._read_wps(file_path)
            elif ext == ".et":
                return self._read_xls(file_path)
            elif ext == ".dps":
                return self._read_ppt(file_path)
            else:
                return ""
        except Exception as e:
            self.logger.warning(f"文件解析失败 ({ext}): {file_path} - {e}")
            return ""

    def _read_plain_text(self, file_path):
        content = []
        try:
            with open(file_path, "r", encoding="utf-8", errors="replace") as f:
                for i, line in enumerate(f):
                    if i >= 10000:
                        break
                    content.append(line)
        except (IOError, PermissionError) as e:
            self.logger.warning(f"文本文件读取失败: {file_path} - {e}")
            return ""
        return "".join(content)

    def _read_docx(self, file_path):
        try:
            from docx import Document
            doc = Document(file_path)
            content = []
            line_count = 0
            for para in doc.paragraphs:
                if line_count >= 10000:
                    break
                content.append(para.text)
                line_count += 1
            for table in doc.tables:
                if line_count >= 10000:
                    break
                for row in table.rows:
                    if line_count >= 10000:
                        break
                    row_text = " ".join(cell.text for cell in row.cells)
                    content.append(row_text)
                    line_count += 1
            return "\n".join(content)
        except ImportError:
            self.logger.error("缺少 python-docx 库，无法解析 .docx 文件")
            return ""
        except Exception as e:
            self.logger.warning(f"docx 解析失败: {file_path} - {e}")
            return ""

    def _read_doc(self, file_path):
        try:
            import olefile
            if not olefile.isOleFile(file_path):
                self.logger.warning(f"不是有效的 OLE 文件: {file_path}")
                return ""
            ole = olefile.OleFileIO(file_path)
            try:
                word_stream = ole.openstream("WordDocument")
                data = word_stream.read()
                word_stream.close()

                text_parts = []
                text_mode = False
                for i in range(0, len(data) - 1, 2):
                    if i >= 20000:
                        break
                    char_code = data[i] | (data[i + 1] << 8)
                    if char_code == 0x0D:
                        text_parts.append("\n")
                        text_mode = False
                    elif 0x20 <= char_code <= 0xFFFF and char_code != 0xFEFF:
                        if char_code <= 0xFFFF:
                            text_parts.append(chr(char_code))
                            text_mode = True

                return "".join(text_parts)
            finally:
                ole.close()
        except ImportError:
            self.logger.error("缺少 olefile 库，无法解析 .doc 文件")
            return ""
        except Exception as e:
            self.logger.warning(f"doc 解析失败: {file_path} - {e}")
            return ""

    def _read_xlsx(self, file_path):
        try:
            import openpyxl
            wb = openpyxl.load_workbook(file_path, read_only=True, data_only=True)
            content = []
            line_count = 0
            for sheet in wb.worksheets:
                if line_count >= 10000:
                    break
                for row in sheet.iter_rows(values_only=True):
                    if line_count >= 10000:
                        break
                    row_text = " ".join(str(cell) for cell in row if cell is not None)
                    if row_text.strip():
                        content.append(row_text)
                        line_count += 1
            wb.close()
            return "\n".join(content)
        except ImportError:
            self.logger.error("缺少 openpyxl 库，无法解析 .xlsx 文件")
            return ""
        except Exception as e:
            self.logger.warning(f"xlsx 解析失败: {file_path} - {e}")
            return ""

    def _read_xls(self, file_path):
        try:
            import xlrd
            wb = xlrd.open_workbook(file_path)
            content = []
            line_count = 0
            for sheet_idx in range(wb.nsheets):
                if line_count >= 10000:
                    break
                sheet = wb.sheet_by_index(sheet_idx)
                for row_idx in range(sheet.nrows):
                    if line_count >= 10000:
                        break
                    row_values = sheet.row_values(row_idx)
                    row_text = " ".join(str(v) for v in row_values if v != "")
                    if row_text.strip():
                        content.append(row_text)
                        line_count += 1
            return "\n".join(content)
        except ImportError:
            self.logger.error("缺少 xlrd 库，无法解析 .xls/.et 文件")
            return ""
        except Exception as e:
            self.logger.warning(f"xls 解析失败: {file_path} - {e}")
            return ""

    def _read_csv(self, file_path):
        content = []
        try:
            with open(file_path, "r", encoding="utf-8", errors="replace") as f:
                reader = csv.reader(f)
                for i, row in enumerate(reader):
                    if i >= 10000:
                        break
                    row_text = " ".join(row)
                    if row_text.strip():
                        content.append(row_text)
        except (IOError, PermissionError) as e:
            self.logger.warning(f"CSV 文件读取失败: {file_path} - {e}")
            return ""
        return "\n".join(content)

    def _read_pptx(self, file_path):
        try:
            from pptx import Presentation
            prs = Presentation(file_path)
            content = []
            line_count = 0
            for slide in prs.slides:
                if line_count >= 10000:
                    break
                for shape in slide.shapes:
                    if line_count >= 10000:
                        break
                    if shape.has_text_frame:
                        for para in shape.text_frame.paragraphs:
                            if line_count >= 10000:
                                break
                            text = para.text.strip()
                            if text:
                                content.append(text)
                                line_count += 1
                    if shape.has_table:
                        table = shape.table
                        for row in table.rows:
                            if line_count >= 10000:
                                break
                            row_text = " ".join(cell.text for cell in row.cells)
                            if row_text.strip():
                                content.append(row_text)
                                line_count += 1
            return "\n".join(content)
        except ImportError:
            self.logger.error("缺少 python-pptx 库，无法解析 .pptx 文件")
            return ""
        except Exception as e:
            self.logger.warning(f"pptx 解析失败: {file_path} - {e}")
            return ""

    def _read_ppt(self, file_path):
        try:
            import olefile
            if not olefile.isOleFile(file_path):
                self.logger.warning(f"不是有效的 OLE 文件: {file_path}")
                return ""
            ole = olefile.OleFileIO(file_path)
            try:
                content = []
                line_count = 0
                for stream_name in ole.listdir():
                    if line_count >= 10000:
                        break
                    name = "/".join(stream_name).lower()
                    if "text" in name or "word" in name:
                        try:
                            stream = ole.openstream("/".join(stream_name))
                            data = stream.read()
                            stream.close()
                            text = data.decode("utf-8", errors="replace")
                            for line in text.split("\n"):
                                if line_count >= 10000:
                                    break
                                if line.strip():
                                    content.append(line.strip())
                                    line_count += 1
                        except Exception:
                            continue
                return "\n".join(content)
            finally:
                ole.close()
        except ImportError:
            self.logger.error("缺少 olefile 库，无法解析 .ppt/.dps 文件")
            return ""
        except Exception as e:
            self.logger.warning(f"ppt 解析失败: {file_path} - {e}")
            return ""

    def _read_pdf(self, file_path):
        try:
            import pdfplumber
            content = []
            line_count = 0
            with pdfplumber.open(file_path) as pdf:
                for page in pdf.pages:
                    if line_count >= 10000:
                        break
                    text = page.extract_text()
                    if text:
                        for line in text.split("\n"):
                            if line_count >= 10000:
                                break
                            if line.strip():
                                content.append(line.strip())
                                line_count += 1
            return "\n".join(content)
        except ImportError:
            self.logger.error("缺少 pdfplumber 库，无法解析 .pdf 文件")
            return ""
        except Exception as e:
            self.logger.warning(f"PDF 解析失败: {file_path} - {e}")
            return ""

    def _read_wps(self, file_path):
        try:
            import olefile
            if not olefile.isOleFile(file_path):
                self.logger.warning(f"不是有效的 OLE 文件 (wps): {file_path}")
                return ""
            ole = olefile.OleFileIO(file_path)
            try:
                text_parts = []
                line_count = 0
                for stream_name in ole.listdir():
                    if line_count >= 10000:
                        break
                    name = "/".join(stream_name).lower()
                    if "text" in name or "content" in name or "worddocument" in name:
                        try:
                            stream = ole.openstream("/".join(stream_name))
                            data = stream.read()
                            stream.close()
                            text = data.decode("utf-8", errors="replace")
                            for line in text.split("\n"):
                                if line_count >= 10000:
                                    break
                                if line.strip():
                                    text_parts.append(line.strip())
                                    line_count += 1
                        except Exception:
                            continue
                if not text_parts:
                    stream = ole.openstream("WordDocument")
                    data = stream.read()
                    stream.close()
                    for i in range(0, min(len(data), 20000), 2):
                        char_code = data[i] | (data[i + 1] << 8)
                        if 0x20 <= char_code <= 0xFFFF and char_code != 0xFEFF:
                            text_parts.append(chr(char_code))
                            if char_code in (0x0D, 0x0A):
                                line_count += 1
                return "".join(text_parts)
            finally:
                ole.close()
        except ImportError:
            self.logger.error("缺少 olefile 库，无法解析 .wps 文件")
            return ""
        except Exception as e:
            self.logger.warning(f"wps 解析失败: {file_path} - {e}")
            return ""
