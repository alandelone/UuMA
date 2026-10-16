import pytest

from uuma.honc.life_context import allowed_operations


def test_current_body_report_and_future_habit_plan_keep_separate_grants():
    assert allowed_operations("今天手腕酸，计划明天运动") == ("record_body",)
    assert allowed_operations("今天锻体tod做了20", ("锻体tod",)) == ("record_habit",)
    assert allowed_operations("锻体tod做了吗？", ("锻体tod",)) == ()
    assert allowed_operations("他说，今天锻体tod做了20", ("锻体tod",)) == ()


def test_authenticated_voice_wrapper_and_spacing_preserve_domain_admission():
    spoken = '"早上 吃 了 早餐，精神 一点 累，鼻子 流 鼻涕"'
    assert allowed_operations(spoken) == ()
    assert allowed_operations(spoken, input_kind="voice_transcript") == (
        "record_body",
        "record_habit",
    )
    exercise = '"我 八 段 锦 已 经 打 完，打卡一下"'
    assert allowed_operations(exercise, ("八段锦",), input_kind="voice_transcript") == (
        "record_habit",
    )


@pytest.mark.parametrize(
    "text",
    [
        '"他说，今天肚子痛"',
        '"明天计划运动"',
        '"不要记录今天鼻塞"',
        '""今天肚子痛""',
        '"查看身体历史"',
        '"如果今天肚子痛"',
    ],
)
def test_voice_provenance_never_authorizes_quoted_or_non_report_content(text):
    assert allowed_operations(text, input_kind="voice_transcript") == ()
