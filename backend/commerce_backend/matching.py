from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

CONCEPTS = {
    "storage": ["storage", "organizer", "收纳", "整理"],
    "box": ["box", "bin", "盒", "箱"],
    "drawer": ["drawer", "抽屉"],
    "bowl": ["bowl", "碗"],
    "leash": ["leash", "牵引", "狗绳"],
    "toy": ["toy", "玩具"],
    "silicone": ["silicone", "硅胶"],
    "steel": ["steel", "stainless", "不锈钢"],
    "knife": ["knife", "刀"],
    "board": ["board", "砧板", "案板"],
    "bottle": ["bottle", "水壶", "水瓶"],
    "tent": ["tent", "帐篷"],
    "chair": ["chair", "椅"],
    "light": ["light", "lantern", "灯"],
    "foldable": ["foldable", "folding", "折叠"],
    "waterproof": ["waterproof", "防水"],
    "pet": ["pet", "dog", "cat", "宠物", "猫", "狗"],
    "kitchen": ["kitchen", "cooking", "厨房", "烹饪"],
}


def normalize(text: str | None) -> str:
    value = unicodedata.normalize("NFKC", text or "").lower()
    value = re.sub(r"(\d+(?:\.\d+)?)\s*(centimeters?|cm|厘米)", r"\1cm", value)
    value = re.sub(r"(\d+(?:\.\d+)?)\s*(millimeters?|mm|毫米)", r"\1mm", value)
    return re.sub(r"[^\w\u4e00-\u9fff.]+", " ", value).strip()


def concept_tokens(text: str | None) -> set[str]:
    normalized = normalize(text)
    tokens = set(normalized.split())
    for concept, aliases in CONCEPTS.items():
        if any(alias in normalized for alias in aliases):
            tokens.add(concept)
    return tokens


def jaccard(left: set[str], right: set[str]) -> float:
    return len(left & right) / len(left | right) if left and right else 0.0


def conflict_penalty(left: str | None, right: str | None) -> tuple[float, list[str]]:
    lvalue, rvalue = normalize(left), normalize(right)
    reasons: list[str] = []
    penalty = 0.0
    material_groups = [("silicone", "steel"), ("plastic", "steel"), ("wood", "plastic")]
    for one, other in material_groups:
        if (one in lvalue and other in rvalue) or (other in lvalue and one in rvalue):
            penalty += 0.08
            reasons.append("材料关键词存在差异")
            break
    left_sizes = set(re.findall(r"\d+(?:\.\d+)?(?:cm|mm)", lvalue))
    right_sizes = set(re.findall(r"\d+(?:\.\d+)?(?:cm|mm)", rvalue))
    if left_sizes and right_sizes and left_sizes.isdisjoint(right_sizes):
        penalty += 0.06
        reasons.append("尺寸关键词存在差异")
    return penalty, reasons


@dataclass(frozen=True)
class MatchResult:
    score: float
    reason: str


def match_product_supplier(product, supplier) -> MatchResult:
    category_score = 1.0 if product.category == supplier.category else 0.0
    title_score = jaccard(concept_tokens(product.title), concept_tokens(supplier.title))
    specification_score = jaccard(
        concept_tokens(product.specification), concept_tokens(supplier.specification)
    )
    penalty, conflicts = conflict_penalty(product.specification, supplier.specification)
    score = max(0.0, min(1.0, 0.35 * category_score + 0.45 * title_score + 0.20 * specification_score - penalty))
    parts = [
        f"类别匹配 {category_score:.2f}",
        f"标题概念相似度 {title_score:.2f}",
        f"规格相似度 {specification_score:.2f}",
    ]
    parts.extend(conflicts)
    return MatchResult(round(score, 4), "；".join(parts))
