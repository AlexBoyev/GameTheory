"""`SkillRegistry`: auto-discovery plus the JSON schema export for the LLM."""

import importlib
import pkgutil
from types import ModuleType
from typing import TYPE_CHECKING, Any

from app.ai.skills.base import Skill, SkillCategory

if TYPE_CHECKING:  # pragma: no cover - import cycle avoidance
    from app.ai.skill_services import SkillServices


class SkillRegistry:
    """Holds one instance per skill class, keyed by `Skill.name`.

    The LLM may only call registered skills; anything else is rejected and
    logged (SPEC section 7.3).
    """

    __slots__ = ("_skills",)

    def __init__(self) -> None:
        self._skills: dict[str, Skill] = {}

    def __len__(self) -> int:
        return len(self._skills)

    def __contains__(self, name: object) -> bool:
        return name in self._skills

    @property
    def names(self) -> tuple[str, ...]:
        """Registered skill names, sorted for deterministic iteration."""
        return tuple(sorted(self._skills))

    def register(self, skill: Skill) -> None:
        """Register `skill`, rejecting duplicate names."""
        name = type(skill).name
        if name in self._skills:
            msg = f"duplicate skill name: {name!r}"
            raise ValueError(msg)
        self._skills[name] = skill

    def get(self, name: str) -> Skill | None:
        """Return the skill called `name`, or `None`."""
        return self._skills.get(name)

    def require(self, name: str) -> Skill:
        """Return the skill called `name`, or raise if it is not registered."""
        skill = self._skills.get(name)
        if skill is None:
            msg = f"no skill named {name!r}; registered: {', '.join(self.names)}"
            raise KeyError(msg)
        return skill

    def by_category(self, category: SkillCategory) -> list[Skill]:
        """Return registered skills in `category`, name-sorted."""
        return [
            self._skills[name]
            for name in self.names
            if type(self._skills[name]).category is category
        ]

    def all(self) -> list[Skill]:
        """Return every registered skill, name-sorted."""
        return [self._skills[name] for name in self.names]

    def schemas(self) -> list[dict[str, Any]]:
        """Return `Skill.describe()` for every skill, for LLM prompts."""
        return [type(skill).describe() for skill in self.all()]

    def discover(self, package: ModuleType | None = None) -> int:
        """Import every module in `package` and register the skills found.

        Defaults to the package this registry ships with. Abstract and base
        classes are skipped. Returns the number of skills registered.
        """
        target = package or importlib.import_module("app.ai.skills")
        before = len(self._skills)
        for module_info in pkgutil.iter_modules(getattr(target, "__path__", [])):
            if module_info.name in {"base", "registry"}:
                continue
            module = importlib.import_module(f"{target.__name__}.{module_info.name}")
            self._register_from_module(module)
        return len(self._skills) - before

    def _register_from_module(self, module: ModuleType) -> None:
        for attribute in vars(module).values():
            if not isinstance(attribute, type) or not issubclass(attribute, Skill):
                continue
            if attribute is Skill or getattr(attribute, "__abstractmethods__", None):
                continue
            if getattr(attribute, "name", None) and attribute.name not in self._skills:
                self.register(attribute())

    def bind(self, services: "SkillServices") -> None:
        """Hand every registered skill the collaborators it may need."""
        for skill in self._skills.values():
            skill.bind(services)


def build_registry(services: "SkillServices | None" = None) -> SkillRegistry:
    """Return a registry with every shipped skill discovered and bound.

    `services` is optional only so that tests which never touch a social
    skill can build a registry in one line; anything that runs the pipeline
    passes it.
    """
    registry = SkillRegistry()
    registry.discover()
    if services is not None:
        registry.bind(services)
    return registry
