"""
pool_screener 离线单测 — 预设条件解析 + 自定义条件解析 + 白名单校验

不依赖数据库（mock screen_pool 的 SQL 执行），只测纯逻辑：
  - _parse_custom 解析各种条件格式
  - 非法字段/运算符拒绝
  - PRESETS 结构完整性
"""
import pytest

from pool_screener import _parse_custom, PRESETS, Preset


# ---------- PRESETS 结构 ----------

class TestPresets:
    def test_all_presets_have_required_fields(self):
        """每个预设必须有 name/label/desc/where/order"""
        for key, p in PRESETS.items():
            assert p.name == key, f"预设 {key} 的 name 不匹配"
            assert p.label, f"预设 {key} 缺 label"
            assert p.desc, f"预设 {key} 缺 desc"
            assert p.where, f"预设 {key} 缺 where"
            assert p.order, f"预设 {key} 缺 order"
            assert isinstance(p.tags, list), f"预设 {key} tags 应为 list"

    def test_presets_count(self):
        """至少 5 个预设"""
        assert len(PRESETS) >= 5

    def test_value_preset_conditions(self):
        """价值蓝筹条件：大市值 + 低PE + 低PB"""
        w = PRESETS["value"].where
        assert "total_mv > 200" in w
        assert "pe BETWEEN 5 AND 20" in w
        assert "pb < 3" in w

    def test_growth_preset_conditions(self):
        """成长活跃条件：中等市值 + 合理PE + 活跃换手"""
        w = PRESETS["growth"].where
        assert "total_mv BETWEEN 50 AND 500" in w
        assert "turnover BETWEEN 2 AND 10" in w

    def test_dividend_preset_conditions(self):
        """高股息防御条件：超大市值 + 极低PE + 低PB"""
        w = PRESETS["dividend"].where
        assert "total_mv > 300" in w
        assert "pe < 15" in w
        assert "pb < 1.5" in w


# ---------- _parse_custom 条件解析 ----------

class TestParseCustom:
    def test_single_condition(self):
        """单个条件"""
        assert _parse_custom("total_mv>100") == "total_mv > 100"

    def test_multiple_conditions(self):
        """多个条件 AND 连接"""
        result = _parse_custom("total_mv>100,pe>0,turnover>1")
        assert "total_mv > 100" in result
        assert "pe > 0" in result
        assert "turnover > 1" in result
        assert " AND " in result

    def test_operators(self):
        """支持 >= <= != > < ="""
        for op in [">=", "<=", "!=", ">", "<"]:
            sql = _parse_custom(f"pe{op}10")
            assert f"pe {op} 10" in sql

    def test_decimal_value(self):
        """小数值"""
        assert _parse_custom("pb<1.5") == "pb < 1.5"

    def test_negative_value(self):
        """负值（涨跌幅）"""
        assert _parse_custom("pct_change<-5") == "pct_change < -5"

    def test_whitespace_tolerant(self):
        """容忍空格"""
        assert _parse_custom(" total_mv > 100 , pe > 0 ") == "total_mv > 100 AND pe > 0"

    def test_invalid_field_rejected(self):
        """非法字段名拒绝（防 SQL 注入）"""
        with pytest.raises(ValueError, match="不支持的字段"):
            _parse_custom("password>0")

    def test_invalid_operator_rejected(self):
        """非法运算符拒绝"""
        with pytest.raises(ValueError, match="无法解析"):
            _parse_custom("total_mv~100")

    def test_empty_string_rejected(self):
        """空字符串拒绝"""
        with pytest.raises(ValueError, match="为空"):
            _parse_custom("")

    def test_garbage_rejected(self):
        """乱码拒绝"""
        with pytest.raises(ValueError, match="无法解析"):
            _parse_custom("hello world")


# ---------- list_codes 接口（仅验签名，不查库）----------

class TestListCodesSignature:
    def test_function_exists(self):
        """list_codes 可导入且可调用"""
        from pool_screener import list_codes
        assert callable(list_codes)
