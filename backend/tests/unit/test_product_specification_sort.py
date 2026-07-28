from app.knowledge.tools.product import _specification_length_mm


def test_specification_length_prefers_width_dimension():
    assert _specification_length_mm("W4800*D1600*H750 mm") == 4800


def test_specification_length_falls_back_to_first_number():
    assert _specification_length_mm("2400 x 1100 x 750 mm") == 2400
