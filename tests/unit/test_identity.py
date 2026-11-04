from parse.identity import identify_report

SZSE_COVER = "科大讯飞股份有限公司 2024 年年度报告全文\n2024 年年度报告\n"
SZSE_INFO = "科大讯飞股份有限公司 2024 年年度报告全文\n股票简称 科大讯飞 股票代码 002230\n"
SSE_COVER = "北京金山办公软件股份有限公司 2025 年年度报告\n公司代码：688111 公司简称：金山办公\n2025 年年度报告\n"


def test_szse_identity_from_info_page():
    identity = identify_report([SZSE_COVER, "", SZSE_INFO])
    assert (identity.stock_code, identity.short_name, identity.year, identity.report_type) == (
        "002230",
        "科大讯飞",
        "2024",
        "annual",
    )


def test_sse_identity_from_cover():
    identity = identify_report([SSE_COVER])
    assert (identity.stock_code, identity.short_name, identity.year) == ("688111", "金山办公", "2025")


def test_header_row_without_values_is_not_a_name():
    # 「股票种类 股票上市交易所及板块 股票简称 股票代码 变更前股票简称」是表头，不是简称
    identity = identify_report(["股票种类 股票上市交易所及板块 股票简称 股票代码 变更前股票简称\n"] + [SSE_COVER])
    assert identity.short_name == "金山办公"


def test_semi_annual_report_is_detected():
    pages = ["示例股份有限公司 2025 年半年度报告\n2025 年半年度报告\n"] * 3
    identity = identify_report(pages)
    assert (identity.year, identity.report_type) == ("2025", "semi")


def test_boilerplate_mention_of_semi_report_does_not_flip_type():
    body = "上述财务指标或其加总数是否与公司已披露季度报告、半年度报告相关财务指标存在重大差异\n"
    identity = identify_report([SZSE_COVER, body, body, SZSE_INFO])
    assert identity.report_type == "annual"


def test_unknown_text_returns_none_fields():
    identity = identify_report(["合同编号：HT-2026-001\n甲方：示例公司\n"])
    assert identity == type(identity)(None, None, None, None)
