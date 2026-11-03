"""Website-aware layer around the existing tenant-scoped operational assistant."""

import re

from app.services.assistant import AssistantService
from app.services.website_knowledge import FEATURES, feature_for_route, find_feature, overview


class WebsiteAssistantService:
    """Answers safe product questions before falling back to live business queries."""

    def __init__(self, session):
        self.session = session

    async def answer(self, business_id, question: str, route: str | None = None, history: list[str] | None = None) -> dict:
        normalized = " ".join(question.lower().split())
        previous = " ".join((history or [])[-3:]).lower()
        navigation = self._navigation(normalized)
        if navigation:
            feature = feature_for_route(navigation)
            return self._result(
                "navigate",
                f"I can take you to {feature.name if feature else navigation}.",
                ["validated application navigation"],
                navigation,
            )
        if any(phrase in normalized for phrase in ("what is this website", "explain this website", "entire website", "major features", "what can this website do")):
            return self._result("website_overview", overview(), ["verified application knowledge"])
        if any(phrase in normalized for phrase in ("owner permission", "manager permission", "difference between manager and owner", "roles and permissions")):
            return self._result(
                "roles", "Owners and managers currently have the full backend permission set. Staff can work with catalog, inventory, and sales but cannot access finance, procurement, users, or insights. Analysts can read business, catalog, inventory, sales, finance, procurement, and insights, but cannot write records. Owner-only purchasing approval is still enforced in the provision workflow.",
                ["role permission policy", "provision approval workflow"],
            )
        if "after approval" in normalized and ("procurement" in previous or "order" in previous or "provision" in previous):
            return self._result(
                "procurement_follow_up", "After an owner authorizes supplier contact, managers can provide replenishment quantities. Conflicts are escalated for resolution. A supplier quotation is collected next, and a separate explicit owner approval is required before a purchase can be created. Nothing is purchased or called automatically; telephone calls remain disabled in test mode.",
                ["provision workflow"],
            )
        if any(term in normalized for term in ("procurement", "provision", "supplier contact", "how does inventory connect")):
            return self._result(
                "procurement_explanation", "Inventory records use thresholds to identify shortages. Pending orders and recipes can contribute demand where configured. The Provision agent then records an owner decision for supplier contact, collects manager quantities, resolves conflicts, captures supplier quotations, and requires a separate owner approval before creating a purchase. It never contacts suppliers, places an order, or makes a call automatically in the current test configuration.",
                ["inventory", "provision workflow", "supplier and purchase controls"],
            )
        feature = find_feature(question, route)
        if feature:
            return self._feature_result(feature, detailed=any(term in normalized for term in ("how", "step", "detail", "explain", "works")))
        if normalized in {"what can i do", "what can i do here", "help"} and route:
            feature = feature_for_route(route)
            if feature:
                return self._feature_result(feature, detailed=True)
        return await AssistantService(self.session).answer(business_id, question)

    @staticmethod
    def _navigation(question: str) -> str | None:
        if not re.search(r"\b(open|go to|take me to|show me)\b", question):
            return None
        candidates = sorted(FEATURES, key=lambda item: len(item.name), reverse=True)
        for feature in candidates:
            if feature.name.lower() in question or (
                feature.route != "/" and feature.route.lstrip("/") in question
            ):
                return feature.route
        if "pending order" in question:
            return "/orders"
        if "procurement" in question:
            return "/provision"
        return None

    @staticmethod
    def _feature_result(feature, detailed: bool) -> dict:
        text = f"{feature.name} is available at {feature.route}. {feature.purpose} Access: {feature.access}. You can: {feature.actions}."
        if detailed:
            text += f" How it works: {feature.workflow} Related areas: {', '.join(feature.related) or 'none listed'}."
            text += f" It depends on: {', '.join(feature.dependencies) or 'no additional dependency is listed'}."
            text += f" Common limitation: {feature.common_errors[0] if feature.common_errors else 'none listed for this workspace'}"
        text += " This is currently an implemented workflow." if feature.status == "implemented" else " This page is currently a design-preview workspace; do not treat its controls as a completed backend workflow."
        return WebsiteAssistantService._result("website_feature", text, ["verified application knowledge"], feature.route)

    @staticmethod
    def _result(intent: str, answer: str, sources: list[str], navigation_path: str | None = None) -> dict:
        from datetime import UTC, datetime
        return {"intent": intent, "answer": answer, "sources": sources, "navigation_path": navigation_path, "generated_at": datetime.now(UTC), "grounded": True}
