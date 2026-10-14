from uuma.honc.life_context import allowed_operations


def test_current_body_report_and_future_habit_plan_keep_separate_grants():
    assert allowed_operations("今天手腕酸，计划明天运动") == ("record_body",)
    assert allowed_operations("今天锻体tod做了20", ("锻体tod",)) == ("record_habit",)
    assert allowed_operations("锻体tod做了吗？", ("锻体tod",)) == ()
    assert allowed_operations("他说，今天锻体tod做了20", ("锻体tod",)) == ()
