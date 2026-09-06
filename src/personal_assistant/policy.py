from dataclasses import dataclass

from .models import ActionDecision, ActionKind, ProposedAction


@dataclass(frozen=True)
class SafetyPolicy:
    auto_action_threshold: float = 0.85
    confirmation_threshold: float = 0.55

    def decide(self, action: ProposedAction) -> ActionDecision:
        if action.kind is ActionKind.NONE:
            return ActionDecision.IGNORE

        # Calendar writes and permanent memories always remain human-controlled.
        high_impact = {ActionKind.CREATE_EVENT, ActionKind.STORE_MEMORY}
        if action.kind in high_impact:
            return ActionDecision.PROPOSE

        if action.confidence >= self.auto_action_threshold:
            return ActionDecision.EXECUTE
        if action.confidence >= self.confirmation_threshold:
            return ActionDecision.PROPOSE
        return ActionDecision.IGNORE

