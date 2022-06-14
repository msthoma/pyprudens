import re
from dataclasses import dataclass
from functools import cache
from typing import Union

from pydantic import BaseModel


class PrudensLiteral(BaseModel):
    name: str
    sign: bool
    isJS: bool
    isEquality: bool
    isInequality: bool
    isAction: bool
    # args: list
    arity: int

    def to_string(self) -> str:
        # when sign is True -> positive literal, and the reverse
        return f"{'-' if not self.sign else ''}{self.name}"


@cache
def to_prudens_literal(lit: str) -> dict[str, Union[bool, int, str]]:
    """
    Converts the provided literal to a dict object used to communicate with Prudens.

    Note: Only the fields name and sign are implemented.
    """
    return PrudensLiteral(
        name=lit.lstrip("-"),
        sign="-" not in lit,
        isJS=False,
        isEquality=False,
        isInequality=False,
        isAction=False,
        arity=0,
    ).dict()


@dataclass(frozen=True)
class PrudensRule:
    """A class to represent a Prudens rule and its components."""

    body: tuple[str, ...]
    head: str
    added_as: str = ""
    active: bool = True

    @classmethod
    def from_string(cls, rule_string: str, added_as: str = "", active: bool = True):
        assert all([p in rule_string for p in [" :: ", " implies "]])
        ctx, head = rule_string.strip().rstrip(";").split(" :: ")[1].split(" implies ")
        return cls(
            body=tuple(ctx.split(", ")),
            head=head.strip(),
            added_as=added_as,
            active=active,
        )

    @classmethod
    def from_prudens_rule_json_object(
        cls, prudens_rule_json_object: dict[str, Union[str, list, dict]]
    ):
        """
        Parses a Prudens rule from JSON as described here https://github.com/VMarkos/prudens-js#rules. The `name` field
        is ignored.
        """
        assert all(k in prudens_rule_json_object for k in ["name", "body", "head"])
        return cls(
            body=tuple(
                PrudensLiteral.parse_obj(lit).to_string()
                for lit in prudens_rule_json_object["body"]
            ),
            head=PrudensLiteral.parse_obj(prudens_rule_json_object["head"]).to_string(),
        )

    def to_string(self, rule_name=None) -> str:
        if rule_name is None:
            rule_name = "R"
        elif isinstance(rule_name, int):
            rule_name = f"R{rule_name}"

        return " ".join(
            [
                rule_name,
                "::",
                ", ".join(self.body),
                "implies",
                f"{self.head};",
            ]
        )

    def __str__(self) -> str:
        return self.to_string()

    def __eq__(self, obj: object) -> bool:
        """
        Checks equality between two PrudensRule instances. NOTE that two rules with a body of the same literals, but
        in a different order, ARE considered equal, e.g.:

        `PrudensRule(body=("a", "b"), head="c") == PrudensRule(body=("b", "a"), head="c")`
        """
        return (
            isinstance(obj, PrudensRule)
            and set(self.body) == set(obj.body)
            and self.head == obj.head
        )


@dataclass(frozen=True)
class PrudensKnowledgeBase:
    rules: tuple[PrudensRule, ...]

    def is_empty(self) -> bool:
        return len(self.rules) == 0

    def is_not_empty(self) -> bool:
        return not self.is_empty()

    def number_of_active_rules(self) -> int:
        return len([r for r in self.rules if r.active])

    def get_full_context(self) -> list[str]:
        def natural_sort_key(s, _nsre=re.compile(r"(\d+)")):
            """
            Can be used to sort strings in natural order (taking into account numbers in strings). Copied from
            https://stackoverflow.com/a/16090640/.
            """
            return [int(t) if t.isdigit() else t.lower() for t in _nsre.split(s)]

        full_context = set()
        for rule in self.rules:
            for literal in rule.body:
                if literal not in ["true", "empty"]:
                    full_context.add(literal.replace("-", ""))
        return sorted(full_context, key=natural_sort_key)

    def copy(self) -> "PrudensKnowledgeBase":
        """
        Creates a copy of an instance of this class.
        """
        return PrudensKnowledgeBase(rules=tuple(self.rules))

    def to_string(self, sep: str = "\n") -> str:
        return sep.join(
            [
                "@KnowledgeBase",
                *[
                    rule.to_string(i)
                    for i, rule in enumerate(self.rules, start=1)
                    if rule.active
                ],
            ]
        )

    @classmethod
    def from_string(cls, kb_string: str):
        assert kb_string.strip().startswith(
            "@KnowledgeBase"
        ), "KB string must begin with '@KnowledgeBase'!"

        rules_str = (
            kb_string.strip()
            .replace("\n", " ")
            .lstrip("@KnowledgeBase")
            .strip()
            .split(";")
        )

        rules_str = [r.strip() for r in rules_str if r]

        return cls(rules=tuple(map(PrudensRule.from_string, rules_str)))

    def to_prudens_kb_json_object(self):
        rules_converted = [
            {
                "name": f"R{i}",
                "body": [to_prudens_literal(lit) for lit in rule.body],
                "head": to_prudens_literal(rule.head),
            }
            for i, rule in enumerate(self.rules)
            if rule.active
        ]

        return {
            "type": "output",
            "kb": rules_converted,
            # "code": "",
            "imports": "",
            "warnings": [],
            # "constraints": "",
        }

    def __str__(self) -> str:
        return self.to_string()

    def __eq__(self, obj: object) -> bool:
        return isinstance(obj, PrudensKnowledgeBase) and self.rules == obj.rules
