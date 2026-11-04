from dashboard.summary import build_summary
from export.guard import find_banned

# 摘要只陈述数值与比较关系（PRD R3）；这些词带评价色彩，不得出现
JUDGEMENT_WORDS = ("关注", "偏低", "支撑", "明显", "质量")


def test_receivable_growth_line_appears(dashboard_session):
    # 夹具：应收 150 → 300（+100%），营收 800 → 1000（+25%）
    texts = [item["text"] for item in build_summary(dashboard_session.latest)]
    line = next(text for text in texts if text.startswith("应收账款增速"))
    assert "100.0%" in line
    assert "75.0 个百分点" in line


def test_summary_wording_is_neutral(dashboard_session):
    for item in build_summary(dashboard_session.latest):
        assert not find_banned(item["text"])
        assert not any(word in item["text"] for word in JUDGEMENT_WORDS), item["text"]


def test_summary_keeps_debt_ratio_line(dashboard_session):
    texts = [item["text"] for item in build_summary(dashboard_session.latest)]
    assert any(text.startswith("资产负债率") for text in texts)
