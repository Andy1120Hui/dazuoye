from types import SimpleNamespace

from commerce_backend.matching import match_product_supplier


def thing(title, specification, category="pet_supplies"):
    return SimpleNamespace(title=title, specification=specification, category=category)


def test_cross_language_concepts_rank_matching_candidate_higher():
    product = thing("Stainless Steel Pet Bowl", "stainless steel 700ml")
    matching = thing("不锈钢宠物碗", "不锈钢 700ml")
    unrelated = thing("宠物牵引绳", "尼龙 1.5m")
    assert match_product_supplier(product, matching).score > match_product_supplier(product, unrelated).score


def test_specification_conflict_reduces_score_and_is_explained():
    product = thing("Pet Bowl", "stainless steel 30cm")
    same = thing("宠物碗", "不锈钢 30cm")
    conflict = thing("宠物碗", "silicone 20cm")
    same_result = match_product_supplier(product, same)
    conflict_result = match_product_supplier(product, conflict)
    assert same_result.score > conflict_result.score
    assert "差异" in conflict_result.reason


def test_empty_specification_is_supported_without_full_spec_score():
    result = match_product_supplier(thing("Dog Leash", None), thing("宠物狗牵引绳", None))
    assert 0 < result.score < 1
