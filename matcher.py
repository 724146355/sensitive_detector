import re
from logger import Logger


class Matcher:
    def __init__(self, compiled_rules, threshold):
        self.compiled_rules = compiled_rules
        self.threshold = threshold
        self.logger = Logger()

        # 预编译合并正则：将所有规则合并为一个 alternation 模式，单次扫描全文
        self._combined_pattern = None
        self._rule_group_names = {}  # group_name -> rule_index
        self._build_combined_pattern()

    def _build_combined_pattern(self):
        """将所有规则的正则合并为一个 alternation，每个规则用命名分组包裹

        例如 3 条规则合并为: (?P<rule_0>pattern1)|(?P<rule_1>pattern2)|(?P<rule_2>pattern3)
        匹配时只需扫描一次文本，通过判断哪个命名分组命中来确定是哪条规则
        """
        if not self.compiled_rules:
            return

        parts = []
        for i, rule in enumerate(self.compiled_rules):
            group_name = f"rule_{i}"
            self._rule_group_names[group_name] = i
            # 用命名分组包裹原始模式
            parts.append(f"(?P<{group_name}>{rule['pattern'].pattern})")

        try:
            combined = "|".join(parts)
            self._combined_pattern = re.compile(combined)
            self.logger.debug(f"已合并 {len(self.compiled_rules)} 条正则为单次扫描模式")
        except re.error as e:
            self.logger.warning(f"合并正则编译失败，将回退到逐规则扫描: {e}")
            self._combined_pattern = None

    def scan_text(self, text, file_path=""):
        """扫描文本，使用合并正则单次扫描 + finditer 提前终止"""
        if not text:
            return False, []

        if not self.compiled_rules:
            self.logger.warning(f"未配置任何正则规则，跳过检测: {file_path}")
            return False, []

        # 优先使用合并正则单次扫描
        if self._combined_pattern is not None:
            return self._scan_combined(text, file_path)

        # 回退：逐规则扫描（合并正则不可用时）
        return self._scan_sequential(text, file_path)

    def _scan_combined(self, text, file_path=""):
        """使用合并后的单一正则扫描文本，只遍历一次

        通过命名分组判断哪条规则命中，达到阈值立即终止
        """
        match_counts = {}  # rule_index -> count
        total_hits = 0     # 所有规则的命中总数，用于快速判断

        for m in self._combined_pattern.finditer(text):
            # 判断哪个命名分组命中
            for group_name, rule_idx in self._rule_group_names.items():
                if m.group(group_name) is not None:
                    match_counts[rule_idx] = match_counts.get(rule_idx, 0) + 1
                    total_hits += 1
                    break

            # 检查是否有任何规则达到阈值
            for rule_idx, count in match_counts.items():
                if count >= self.threshold:
                    matched_details = []
                    for idx, cnt in match_counts.items():
                        if cnt > 0:
                            matched_details.append({
                                "rule_name": self.compiled_rules[idx]["name"],
                                "match_count": cnt
                            })
                    self.logger.debug(
                        f"  合并扫描提前终止: 规则 '{self.compiled_rules[rule_idx]['name']}' "
                        f"命中 {count} 次 >= 阈值 {self.threshold}"
                    )
                    return True, matched_details

        # 扫描完毕，整理结果
        matched_details = []
        for rule_idx, count in match_counts.items():
            if count > 0:
                matched_details.append({
                    "rule_name": self.compiled_rules[rule_idx]["name"],
                    "match_count": count
                })
                self.logger.debug(
                    f"  规则 '{self.compiled_rules[rule_idx]['name']}' 匹配 {count} 次 - {file_path}"
                )

        return False, matched_details

    def _scan_sequential(self, text, file_path=""):
        """逐规则扫描（回退方案），使用 finditer + 计数器提前终止"""
        matched_details = []
        for rule in self.compiled_rules:
            name = rule["name"]
            pattern = rule["pattern"]
            match_count = 0

            # 使用 finditer + 计数器，达到阈值立即停止该规则的扫描
            for _ in pattern.finditer(text):
                match_count += 1
                if match_count >= self.threshold:
                    break

            if match_count > 0:
                match_info = {
                    "rule_name": name,
                    "match_count": match_count
                }
                matched_details.append(match_info)
                self.logger.debug(f"  规则 '{name}' 匹配 {match_count} 次 - {file_path}")

                if match_count >= self.threshold:
                    self.logger.debug(
                        f"  规则 '{name}' 命中次数 {match_count} >= 阈值 {self.threshold}，终止检测"
                    )
                    return True, matched_details

        return False, matched_details

    def scan_text_incremental(self, text_chunk, accumulated_counts=None):
        """增量匹配：对文本片段进行匹配，累积计数

        用于边提取文本边匹配的场景，避免先提取全部文本再匹配。
        调用方在每个文本块提取后调用此方法，传入之前累积的计数。

        Args:
            text_chunk: 本轮提取的文本片段
            accumulated_counts: 之前累积的 {rule_index: count} 字典，首次传 None

        Returns:
            (should_stop, accumulated_counts):
                should_stop: 是否已达到阈值，可以停止提取
                accumulated_counts: 更新后的累积计数
        """
        if not text_chunk:
            return False, accumulated_counts or {}

        if accumulated_counts is None:
            accumulated_counts = {}

        # 优先使用合并正则
        if self._combined_pattern is not None:
            for m in self._combined_pattern.finditer(text_chunk):
                for group_name, rule_idx in self._rule_group_names.items():
                    if m.group(group_name) is not None:
                        accumulated_counts[rule_idx] = accumulated_counts.get(rule_idx, 0) + 1
                        # 检查阈值
                        if accumulated_counts[rule_idx] >= self.threshold:
                            return True, accumulated_counts
                        break
        else:
            # 回退：逐规则扫描
            for i, rule in enumerate(self.compiled_rules):
                for _ in rule["pattern"].finditer(text_chunk):
                    accumulated_counts[i] = accumulated_counts.get(i, 0) + 1
                    if accumulated_counts[i] >= self.threshold:
                        return True, accumulated_counts

        return False, accumulated_counts

    def get_match_details(self, accumulated_counts):
        """将累积计数转换为匹配详情列表"""
        matched_details = []
        any_sensitive = False
        for rule_idx, count in accumulated_counts.items():
            if count > 0:
                matched_details.append({
                    "rule_name": self.compiled_rules[rule_idx]["name"],
                    "match_count": count
                })
                if count >= self.threshold:
                    any_sensitive = True
        return any_sensitive, matched_details
