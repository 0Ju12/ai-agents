from domain.catalog import load_catalog, nutrient_totals
from domain.menu_variations import combinations


def test_combination_recipes_have_distinct_portions_and_complete_guides():
    meals, references = load_catalog(":memory:")
    variants = list(combinations())
    assert len(meals) >= 500
    assert len({title for title, *_ in variants}) == len(variants)
    assert len({tuple(sorted(parts.items())) for _, _, parts, _ in variants}) == len(variants)
    for title, minutes, parts, steps in variants:
        assert meals[title]["grams"] == parts
        assert minutes > 0 and min(parts.values()) > 0
        assert len(steps) >= 3 and nutrient_totals(parts, references)["kcal"] > 0
