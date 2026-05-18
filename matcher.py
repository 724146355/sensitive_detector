from logger import Logger


class Matcher:
    def __init__(self, compiled_rules, threshold):
        self.compiled_rules = compiled_rules
        self.threshold = threshold
        self.logger = Logger()

    def scan_text(self, text, file_path=""):
        if not text:
            return False, []

        if not self.compiled_rules:
            self.logger.warning(f"未配置任何正则规则，跳过检测: {file_path}")
            return False, []

        matched_details = []
        for rule in self.compiled_rules:
            name = rule["name"]
            pattern = rule["pattern"]
            matches = pattern.findall(text)
            match_count = len(matches)

            if match_count > 0:
                match_info = {
                    "rule_name": name,
                    "match_count": match_count
                }
                matched_details.append(match_info)
                self.logger.debug(f"  规则 '{name}' 匹配 {match_count} 次 - {file_path}")

                if match_count >= self.threshold:
                    self.logger.debug(f"  规则 '{name}' 命中次数 {match_count} >= 阈值 {self.threshold}，终止检测")
                    return True, matched_details

        return False, matched_details
