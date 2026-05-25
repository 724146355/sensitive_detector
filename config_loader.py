import json
import os
import re
import shutil


CONFIG_DEFAULT = {
    "rules": [
        {
            "name": "身份证号码",
            "pattern": "[1-9]\\d{5}(?:19|20)\\d{2}(?:0[1-9]|1[0-2])(?:0[1-9]|[12]\\d|3[01])\\d{3}[\\dXx]"
        },
        {
            "name": "手机号码",
            "pattern": "1[3-9]\\d{9}"
        },
        {
            "name": "电子邮箱",
            "pattern": "[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\\.[a-zA-Z]{2,}"
        }
    ],
    "max_file_size_mb": 100,
    "match_threshold": 3,
    "backup_base_path": ".\\sensitive_backup",
    "dev": False,
    "file_timeout_sec": 30,
    "thread_idle_timeout_sec": 60
}


class ConfigLoader:
    def __init__(self, config_path="config.json"):
        self.config_path = config_path
        self.config = dict(CONFIG_DEFAULT)
        self.compiled_rules = []

    def load(self):
        # 如果配置文件已存在，读取；否则创建默认配置文件
        if os.path.exists(self.config_path):
            try:
                with open(self.config_path, "r", encoding="utf-8") as f:
                    self.config = json.load(f)
            except (json.JSONDecodeError, IOError) as e:
                raise RuntimeError(f"配置文件读取失败: {e}")
        else:
            # 配置文件不存在，输出默认配置
            self._write_default_config()

        # 用默认值补齐缺失字段（兼容旧版配置文件）
        for key in CONFIG_DEFAULT:
            if key not in self.config:
                self.config[key] = CONFIG_DEFAULT[key]

        raw_rules = self.config.get("rules", [])
        if not isinstance(raw_rules, list):
            raise RuntimeError("配置文件格式错误: rules 字段必须为数组")

        self.compiled_rules = []
        for idx, rule in enumerate(raw_rules):
            if not isinstance(rule, dict) or "pattern" not in rule:
                raise RuntimeError(f"配置文件格式错误: rules[{idx}] 缺少 pattern 字段")
            try:
                compiled = re.compile(rule["pattern"])
                self.compiled_rules.append({
                    "name": rule.get("name", f"规则{idx + 1}"),
                    "pattern": compiled
                })
            except re.error as e:
                raise RuntimeError(f"正则表达式编译错误 (规则 '{rule.get('name', f'规则{idx + 1}')}'): {e}")

        return self.config, self.compiled_rules

    def get_max_file_size(self):
        return int(self.config.get("max_file_size_mb", CONFIG_DEFAULT["max_file_size_mb"]))

    def get_match_threshold(self):
        return int(self.config.get("match_threshold", CONFIG_DEFAULT["match_threshold"]))

    def get_backup_base_path(self):
        return self.config.get("backup_base_path", CONFIG_DEFAULT["backup_base_path"])

    def get_dev_mode(self):
        """获取开发模式：dev=true 只复制文件，dev=false 剪切文件"""
        return bool(self.config.get("dev", CONFIG_DEFAULT["dev"]))

    def get_file_timeout(self):
        """获取单文件处理超时时间（秒），超过此时间跳过该文件"""
        return int(self.config.get("file_timeout_sec", CONFIG_DEFAULT["file_timeout_sec"]))

    def get_thread_idle_timeout(self):
        """获取线程空闲超时时间（秒），超过此时间终止线程并重新创建"""
        return int(self.config.get("thread_idle_timeout_sec", CONFIG_DEFAULT["thread_idle_timeout_sec"]))

    def _write_default_config(self):
        try:
            with open(self.config_path, "w", encoding="utf-8") as f:
                json.dump(CONFIG_DEFAULT, f, ensure_ascii=False, indent=4)
        except IOError:
            pass
