from core.workflow import build_variant_matrix


def test_ablation_matrix_has_seven_expected_variants():
    matrix = build_variant_matrix()
    assert [item.name for item in matrix] == [
        "full",
        "-critique",
        "-revise",
        "-vote",
        "cot@1",
        "sc@3",
        "sc@5",
    ]


def test_each_ablation_removes_the_correct_component():
    specs = {item.name: item for item in build_variant_matrix()}
    assert specs["full"].components == ("generate", "critique", "revise", "vote")
    assert specs["-critique"].components == ("generate", "revise", "vote")
    assert specs["-revise"].components == ("generate", "critique", "vote")
    assert specs["-vote"].components == ("generate", "critique", "revise")
    assert specs["-vote"].samples == 1
    assert specs["cot@1"].samples == 1
    assert specs["sc@3"].samples == 3
    assert specs["sc@5"].samples == 5
