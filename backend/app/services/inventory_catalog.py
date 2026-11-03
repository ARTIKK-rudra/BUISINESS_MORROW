from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.errors import ConflictError, NotFoundError
from app.db.models import Ingredient, Product, Recipe, RecipeIngredient
from app.schemas.recipes import IngredientCreate, RecipeCreate
from app.services.audit import add_audit_entry
from app.services.units import convert_quantity, normalize_unit


class InventoryCatalogService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def list_ingredients(self, business_id: UUID) -> list[Ingredient]:
        return list(
            await self.session.scalars(
                select(Ingredient)
                .where(Ingredient.business_id == business_id, Ingredient.is_active.is_(True))
                .order_by(Ingredient.name)
            )
        )

    async def create_ingredient(
        self, business_id: UUID, actor_id: UUID, payload: IngredientCreate, request_id: str | None
    ) -> Ingredient:
        unit = normalize_unit(payload.unit)
        if payload.maximum_stock is not None and payload.maximum_stock < payload.minimum_stock:
            raise ConflictError("maximum_stock must be at least minimum_stock")
        ingredient = Ingredient(
            business_id=business_id,
            sku=payload.sku.strip(),
            name=payload.name.strip(),
            unit=unit,
            minimum_stock=payload.minimum_stock,
            maximum_stock=payload.maximum_stock,
            safety_stock=payload.safety_stock,
        )
        self.session.add(ingredient)
        try:
            await self.session.flush()
            add_audit_entry(
                self.session,
                business_id=business_id,
                actor_user_id=actor_id,
                action="ingredient.created",
                entity_type="ingredient",
                entity_id=ingredient.id,
                request_id=request_id,
            )
            await self.session.commit()
        except IntegrityError as exc:
            await self.session.rollback()
            raise ConflictError("An ingredient with this SKU already exists") from exc
        await self.session.refresh(ingredient)
        return ingredient

    async def list_recipes(self, business_id: UUID) -> list[Recipe]:
        return list(
            await self.session.scalars(
                select(Recipe)
                .options(selectinload(Recipe.ingredients))
                .where(Recipe.business_id == business_id)
                .order_by(Recipe.created_at.desc())
            )
        )

    async def save_recipe(
        self,
        business_id: UUID,
        actor_id: UUID,
        payload: RecipeCreate,
        request_id: str | None,
        recipe_id: UUID | None = None,
    ) -> Recipe:
        product = await self.session.scalar(
            select(Product).where(
                Product.id == payload.product_id, Product.business_id == business_id
            )
        )
        if product is None:
            raise NotFoundError("Product not found")
        yield_unit = normalize_unit(payload.yield_unit)
        convert_quantity(payload.yield_quantity, yield_unit, product.unit)
        ingredient_ids = {line.ingredient_id for line in payload.ingredients}
        ingredients = list(
            await self.session.scalars(
                select(Ingredient).where(
                    Ingredient.business_id == business_id,
                    Ingredient.id.in_(ingredient_ids),
                    Ingredient.is_active.is_(True),
                )
            )
        )
        by_id = {row.id: row for row in ingredients}
        if set(by_id) != ingredient_ids:
            raise NotFoundError("One or more recipe ingredients were not found")
        recipe_ingredients = [
            RecipeIngredient(
                ingredient_id=line.ingredient_id,
                quantity=convert_quantity(line.quantity, line.unit, by_id[line.ingredient_id].unit),
                unit=by_id[line.ingredient_id].unit,
            )
            for line in payload.ingredients
        ]
        recipe = None
        if recipe_id:
            recipe = await self.session.scalar(
                select(Recipe)
                .options(selectinload(Recipe.ingredients))
                .where(Recipe.id == recipe_id, Recipe.business_id == business_id)
            )
            if recipe is None:
                raise NotFoundError("Recipe not found")
            recipe.product_id = product.id
            recipe.yield_quantity = payload.yield_quantity
            recipe.yield_unit = yield_unit
            recipe.ingredients.clear()
            recipe.ingredients.extend(recipe_ingredients)
        else:
            recipe = Recipe(
                business_id=business_id,
                product_id=product.id,
                yield_quantity=payload.yield_quantity,
                yield_unit=yield_unit,
                ingredients=recipe_ingredients,
            )
            self.session.add(recipe)
        try:
            await self.session.flush()
            add_audit_entry(
                self.session,
                business_id=business_id,
                actor_user_id=actor_id,
                action="recipe.updated" if recipe_id else "recipe.created",
                entity_type="recipe",
                entity_id=recipe.id,
                request_id=request_id,
            )
            await self.session.commit()
        except IntegrityError as exc:
            await self.session.rollback()
            raise ConflictError("A recipe already exists for this product") from exc
        return await self.session.scalar(
            select(Recipe).options(selectinload(Recipe.ingredients)).where(Recipe.id == recipe.id)
        )
