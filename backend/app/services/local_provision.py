"""Local browser procurement workflow.  It never invokes telephony providers."""

from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ConflictError, NotFoundError
from app.db.models import (
    Business,
    ProvisionCase,
    Supplier,
    VoiceContact,
    VoiceConversation,
    VoiceConversationTurn,
)
from app.schemas.procurement import PurchaseCreate, PurchaseItemCreate
from app.services.audit import add_audit_entry
from app.services.procurement import ProcurementService
from app.services.provision_voice import ProvisionVoiceService


class LocalProvisionService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.shortages = ProvisionVoiceService(session)

    async def start(
        self, business_id: UUID, actor_id: UUID, *, demo_mode: bool, idempotency_key: str | None
    ) -> ProvisionCase:
        if idempotency_key:
            existing = await self.session.scalar(
                select(ProvisionCase).where(
                    ProvisionCase.business_id == business_id,
                    ProvisionCase.idempotency_key == idempotency_key,
                )
            )
            if existing:
                return existing
        owner = await self._contact(business_id, "owner")
        snapshot = await self.shortages.shortage_snapshot(business_id)
        if not snapshot["items"]:
            if not demo_mode:
                raise ConflictError(
                    "No current rule-based shortage exists; use demo mode only "
                    "for a labeled rehearsal"
                )
            snapshot = self._demo_snapshot()
        case = ProvisionCase(
            business_id=business_id,
            owner_contact_id=owner.id,
            created_by=actor_id,
            status="awaiting_owner_authorization",
            demo_mode=demo_mode,
            shortage_snapshot=snapshot,
            manager_recommendations={},
            idempotency_key=idempotency_key,
        )
        self.session.add(case)
        await self.session.flush()
        conversation = VoiceConversation(
            business_id=business_id,
            contact_id=owner.id,
            workflow="owner_shortage_authorization",
            status="awaiting_owner_authorization",
            shortage_snapshot={
                **snapshot,
                "provision_case_id": str(case.id),
                "transport": "browser_simulation",
            },
        )
        self.session.add(conversation)
        await self.session.flush()
        self._turn(
            conversation,
            "agent",
            self.shortages.owner_opening_prompt(snapshot),
            {"transport": "browser_simulation"},
        )
        add_audit_entry(
            self.session,
            business_id=business_id,
            actor_user_id=actor_id,
            action="provision.case.started",
            entity_type="provision_case",
            entity_id=case.id,
            request_id=None,
            metadata={"demo_mode": demo_mode},
        )
        await self.session.commit()
        return case

    async def owner_decision(
        self, case: ProvisionCase, actor_id: UUID, transcript: str
    ) -> ProvisionCase:
        if case.status != "awaiting_owner_authorization":
            raise ConflictError("This provision case is not awaiting owner authorization")
        conversation = await self._conversation(
            case, "owner_shortage_authorization", case.owner_contact_id
        )
        conversation, _ = await self.shortages.record_owner_response(
            conversation.id, case.business_id, transcript
        )
        if conversation.status != "supplier_contact_authorized":
            case.status = conversation.status
            await self.session.commit()
            return case
        managers = await self._contacts(case.business_id, "manager")
        if not managers:
            raise ConflictError("No active manager contacts are configured")
        for manager in managers:
            item_text = "; ".join(
                f"{item['name']}: {item['shortage_to_minimum']} {item['unit']}"
                for item in case.shortage_snapshot["items"]
            )
            manager_conversation = VoiceConversation(
                business_id=case.business_id,
                contact_id=manager.id,
                workflow="manager_quantity_collection",
                status="awaiting_manager_quantities",
                shortage_snapshot={
                    "provision_case_id": str(case.id),
                    "items": case.shortage_snapshot["items"],
                    "transport": "browser_simulation",
                },
            )
            self.session.add(manager_conversation)
            await self.session.flush()
            self._turn(
                manager_conversation,
                "agent",
                f"Local browser simulation for {manager.full_name}. "
                f"Please confirm replenishment quantities: {item_text}.",
                {"transport": "browser_simulation"},
            )
        case.status = "awaiting_manager_quantities"
        add_audit_entry(
            self.session,
            business_id=case.business_id,
            actor_user_id=actor_id,
            action="provision.owner.supplier_contact_authorized",
            entity_type="provision_case",
            entity_id=case.id,
            request_id=None,
            metadata={"telephony": False},
        )
        await self.session.commit()
        return case

    async def manager_response(
        self,
        case: ProvisionCase,
        contact_id: UUID,
        actor_id: UUID,
        transcript: str,
        quantities: dict[str, Decimal],
    ) -> ProvisionCase:
        if case.status != "awaiting_manager_quantities":
            raise ConflictError("This provision case is not awaiting manager quantities")
        contact = await self.session.get(VoiceContact, contact_id)
        if (
            not contact
            or contact.business_id != case.business_id
            or contact.role != "manager"
            or not contact.is_active
        ):
            raise NotFoundError("Active manager contact not found")
        quantities = quantities or self._parse_quantities(
            transcript, case.shortage_snapshot["items"]
        )
        required_ids = {item["inventory_id"] for item in case.shortage_snapshot["items"]}
        if set(quantities) != required_ids:
            raise ConflictError("Provide a positive quantity for every shortage item")
        conversation = await self._conversation(case, "manager_quantity_collection", contact.id)
        serialized = {key: str(value) for key, value in quantities.items()}
        self._turn(conversation, "caller", transcript, {"quantities": serialized})
        conversation.status = "manager_quantities_confirmed"
        conversation.turn_count += 1
        recommendations = dict(case.manager_recommendations)
        recommendations[str(contact.id)] = {"contact": contact.full_name, "quantities": serialized}
        case.manager_recommendations = recommendations
        managers = await self._contacts(case.business_id, "manager")
        if all(str(manager.id) in recommendations for manager in managers):
            rows = [entry["quantities"] for entry in recommendations.values()]
            conflict = any(len({row[item_id] for row in rows}) > 1 for item_id in required_ids)
            case.status = (
                "awaiting_owner_conflict_resolution" if conflict else "awaiting_supplier_quotation"
            )
            if not conflict:
                case.manager_recommendations = {**recommendations, "final": rows[0]}
        add_audit_entry(
            self.session,
            business_id=case.business_id,
            actor_user_id=actor_id,
            action="provision.manager.quantities_recorded",
            entity_type="provision_case",
            entity_id=case.id,
            request_id=None,
            metadata={"manager_contact_id": str(contact.id)},
        )
        await self.session.commit()
        return case

    async def resolve_conflict(
        self, case: ProvisionCase, actor_id: UUID, transcript: str, quantities: dict[str, Decimal]
    ) -> ProvisionCase:
        if case.status != "awaiting_owner_conflict_resolution":
            raise ConflictError("No manager quantity conflict is awaiting resolution")
        required_ids = {item["inventory_id"] for item in case.shortage_snapshot["items"]}
        if set(quantities) != required_ids:
            raise ConflictError("Resolve every shortage item with an explicit quantity")
        recommendations = dict(case.manager_recommendations)
        recommendations["final"] = {key: str(value) for key, value in quantities.items()}
        recommendations["owner_resolution_transcript"] = transcript
        case.manager_recommendations = recommendations
        case.status = "awaiting_supplier_quotation"
        await self._record_case_turn(
            case,
            case.owner_contact_id,
            "owner_purchase_authorization",
            "caller",
            transcript,
            {"resolution": recommendations["final"]},
        )
        await self.session.commit()
        return case

    async def supplier_response(
        self,
        case: ProvisionCase,
        actor_id: UUID,
        transcript: str,
        currency: str,
        delivery_days: int,
        items: list[dict],
    ) -> ProvisionCase:
        if case.status != "awaiting_supplier_quotation":
            raise ConflictError("This provision case is not awaiting a supplier quotation")
        supplier = await self._contact(case.business_id, "supplier")
        final = case.manager_recommendations.get("final")
        if not final:
            raise ConflictError("Manager quantities must be finalized before supplier simulation")
        expected_ids = set(final)
        by_inventory = {str(item["inventory_id"]): item for item in items}
        if set(by_inventory) != expected_ids:
            raise ConflictError("A supplier quote is required for every finalized item")
        quote = {
            "supplier_contact_id": str(supplier.id),
            "supplier": supplier.full_name,
            "currency": currency,
            "delivery_days": delivery_days,
            "items": items,
            "transcript": transcript,
            "simulated": True,
        }
        case.supplier_quote = quote
        case.status = "awaiting_owner_purchase_approval"
        await self._record_case_turn(
            case, supplier.id, "supplier_quotation", "caller", transcript, quote
        )
        add_audit_entry(
            self.session,
            business_id=case.business_id,
            actor_user_id=actor_id,
            action="provision.supplier.quote_recorded",
            entity_type="provision_case",
            entity_id=case.id,
            request_id=None,
            metadata={"simulated": True, "delivery_days": delivery_days},
        )
        await self.session.commit()
        return case

    async def purchase_decision(
        self, case: ProvisionCase, actor_id: UUID, transcript: str, approve: bool
    ) -> ProvisionCase:
        if case.status != "awaiting_owner_purchase_approval":
            raise ConflictError("This provision case is not awaiting exact purchase approval")
        case.approval = {
            "approved": approve,
            "transcript": transcript,
            "recorded_at": datetime.now(UTC).isoformat(),
        }
        await self._record_case_turn(
            case,
            case.owner_contact_id,
            "owner_purchase_authorization",
            "caller",
            transcript,
            case.approval,
        )
        if not approve:
            case.status, case.completed_at = "owner_purchase_declined", datetime.now(UTC)
        elif case.demo_mode:
            case.status, case.completed_at = "demo_purchase_approved_not_created", datetime.now(UTC)
        else:
            purchase = await self._create_purchase(case, actor_id)
            case.purchase_id = purchase.id
            case.status, case.completed_at = "purchase_order_created", datetime.now(UTC)
        add_audit_entry(
            self.session,
            business_id=case.business_id,
            actor_user_id=actor_id,
            action="provision.owner.purchase_decision",
            entity_type="provision_case",
            entity_id=case.id,
            request_id=None,
            metadata={"approved": approve, "demo_mode": case.demo_mode},
        )
        await self.session.commit()
        return case

    async def list_cases(self, business_id: UUID) -> list[ProvisionCase]:
        return list(
            await self.session.scalars(
                select(ProvisionCase)
                .where(ProvisionCase.business_id == business_id)
                .order_by(ProvisionCase.created_at.desc())
                .limit(50)
            )
        )

    async def _create_purchase(self, case: ProvisionCase, actor_id: UUID):
        supplier_contact = await self._contact(case.business_id, "supplier")
        supplier = await self.session.scalar(
            select(Supplier).where(
                Supplier.business_id == case.business_id,
                Supplier.name == supplier_contact.full_name,
            )
        )
        if supplier is None:
            supplier = Supplier(
                business_id=case.business_id,
                name=supplier_contact.full_name,
                contact_name=supplier_contact.full_name,
                is_active=True,
            )
            self.session.add(supplier)
            await self.session.flush()
        quote = case.supplier_quote or {}
        final = case.manager_recommendations["final"]
        quote_items = {str(item["inventory_id"]): item for item in quote["items"]}
        payload_items = []
        for item in case.shortage_snapshot["items"]:
            inventory_id = item["inventory_id"]
            requested = Decimal(final[inventory_id])
            quoted = quote_items[inventory_id]
            if Decimal(str(quoted["available_quantity"])) < requested:
                raise ConflictError("Supplier cannot fulfill the explicitly approved quantity")
            kwargs = {f"{item['item_type']}_id": UUID(item["item_id"])}
            payload_items.append(
                PurchaseItemCreate(
                    quantity=requested, unit_cost=Decimal(str(quoted["unit_cost"])), **kwargs
                )
            )
        currency = quote["currency"]
        base_currency = await self.session.scalar(
            select(Business.base_currency).where(Business.id == case.business_id)
        )
        if currency != base_currency:
            raise ConflictError("Supplier quote currency must match the business base currency")
        return await ProcurementService(self.session).create_order(
            case.business_id,
            actor_id,
            PurchaseCreate(
                supplier_id=supplier.id,
                items=payload_items,
                currency=currency,
                idempotency_key=f"provision-{case.id}",
            ),
            "local-provision",
            commit_transaction=False,
        )

    async def _contact(self, business_id: UUID, role: str) -> VoiceContact:
        contact = await self.session.scalar(
            select(VoiceContact)
            .where(
                VoiceContact.business_id == business_id,
                VoiceContact.role == role,
                VoiceContact.is_active.is_(True),
            )
            .order_by(VoiceContact.created_at)
        )
        if contact is None:
            raise ConflictError(f"No active {role} contact is configured")
        return contact

    async def _contacts(self, business_id: UUID, role: str) -> list[VoiceContact]:
        return list(
            await self.session.scalars(
                select(VoiceContact)
                .where(
                    VoiceContact.business_id == business_id,
                    VoiceContact.role == role,
                    VoiceContact.is_active.is_(True),
                )
                .order_by(VoiceContact.created_at)
            )
        )

    async def _conversation(
        self, case: ProvisionCase, workflow: str, contact_id: UUID
    ) -> VoiceConversation:
        rows = list(
            await self.session.scalars(
                select(VoiceConversation)
                .where(
                    VoiceConversation.business_id == case.business_id,
                    VoiceConversation.workflow == workflow,
                    VoiceConversation.contact_id == contact_id,
                )
                .order_by(VoiceConversation.created_at.desc())
            )
        )
        for row in rows:
            if row.shortage_snapshot.get("provision_case_id") == str(case.id):
                return row
        raise NotFoundError("Provision conversation not found")

    async def _record_case_turn(
        self,
        case: ProvisionCase,
        contact_id: UUID,
        workflow: str,
        speaker: str,
        transcript: str,
        structured: dict,
    ) -> None:
        conversation = VoiceConversation(
            business_id=case.business_id,
            contact_id=contact_id,
            workflow=workflow,
            status="recorded",
            shortage_snapshot={
                "provision_case_id": str(case.id),
                "transport": "browser_simulation",
            },
        )
        self.session.add(conversation)
        await self.session.flush()
        self._turn(conversation, speaker, transcript, structured)

    @staticmethod
    def _turn(
        conversation: VoiceConversation, speaker: str, transcript: str, structured: dict
    ) -> None:
        conversation.turn_count += 1
        conversation.status = conversation.status or "recorded"
        # Flush before this method is called for persisted conversation paths.
        # SQLAlchemy resolves the UUID default when the parent is flushed.
        from sqlalchemy.orm import object_session

        session = object_session(conversation)
        if session is None:
            raise RuntimeError("Conversation must be attached to a database session")
        session.add(
            VoiceConversationTurn(
                conversation_id=conversation.id,
                speaker=speaker,
                transcript=transcript,
                structured_data=structured,
            )
        )

    @staticmethod
    def _parse_quantities(transcript: str, items: list[dict]) -> dict[str, Decimal]:
        import re

        parsed: dict[str, Decimal] = {}
        normalized = transcript.lower()
        for item in items:
            match = re.search(
                rf"{re.escape(item['name'].lower())}[^0-9]*(\\d+(?:\\.\\d+)?)", normalized
            )
            if match:
                parsed[item["inventory_id"]] = Decimal(match.group(1))
        return parsed

    @staticmethod
    def _demo_snapshot() -> dict:
        return {
            "generated_at": datetime.now(UTC).isoformat(),
            "demo": True,
            "pending_order_count": 4,
            "affected_order_count": "demo",
            "items": [
                {
                    "inventory_id": "00000000-0000-0000-0000-000000000001",
                    "item_id": "00000000-0000-0000-0000-000000000001",
                    "item_type": "ingredient",
                    "name": "Demo rice",
                    "unit": "kg",
                    "available": "2",
                    "minimum_target": "20",
                    "shortage_to_minimum": "18",
                    "level": "critical",
                }
            ],
        }
