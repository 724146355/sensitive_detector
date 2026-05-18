import json
import os
import re


CONFIG_DEFAULT = {
    "rules": [],
    "max_file_size_mb": 100,
    "match_threshold": 3,
    "backup_base_path": ""
}


class ConfigLoader:
    def __init__(self, config_path="config.json"):
        self.config_path = config_path
        self.config = dict(CONFIG_DEFAULT)
        self.compiled_rules = []

    def load(self):
        if not os.path.exists(self.config_path):
            self._write_default_config()
            return self.config, self.compiled_rules

        try:
            with open(self.config_path, "r", encoding="utf-8") as f:
                self.config = json.load(f)
        except (json.JSONDecodeError, IOError) as e:
            raise RuntimeError(f"配置文件读取失败: {e}")

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

    def _write_default_config(self):
        try:
            with open(self.config_path, "w", encoding="utf-8") as f:
                json.dump(CONFIG_DEFAULT, f, ensure_ascii=False, indent=4)
        except IOError:
            pass
