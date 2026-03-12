"""
Attora — Product API Routes

GET    /api/products            — List all products for org
POST   /api/products            — Create product
GET    /api/products/{id}       — Get product detail
PUT    /api/products/{id}       — Update product
DELETE /api/products/{id}       — Delete product
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.product import Product
from app.models.user import User
from app.schemas.product import ProductCreate, ProductResponse, ProductUpdate
from app.api.deps import get_current_user, get_org_id

router = APIRouter()


@router.get("", response_model=list[ProductResponse])
async def list_products(
    current_user: User = Depends(get_current_user),
    org_id: uuid.UUID = Depends(get_org_id),
    db: AsyncSession = Depends(get_db),
) -> list[ProductResponse]:
    """List all products for the organization, ordered by sort_order."""
    result = await db.execute(
        select(Product)
        .where(Product.org_id == org_id)
        .order_by(Product.sort_order, Product.name)
    )
    products = result.scalars().all()
    return [ProductResponse.model_validate(p) for p in products]


@router.post("", response_model=ProductResponse, status_code=status.HTTP_201_CREATED)
async def create_product(
    request: ProductCreate,
    current_user: User = Depends(get_current_user),
    org_id: uuid.UUID = Depends(get_org_id),
    db: AsyncSession = Depends(get_db),
) -> ProductResponse:
    """Create a new product for the organization."""
    product = Product(
        org_id=org_id,
        name=request.name,
        description=request.description,
        price=request.price,
        currency=request.currency,
        checkout_url=request.checkout_url,
        conversion_value=request.conversion_value,
        eligibility_criteria=request.eligibility_criteria,
        objection_responses=request.objection_responses,
        is_active=request.is_active,
        sort_order=request.sort_order,
    )
    db.add(product)
    await db.flush()
    await db.refresh(product)

    return ProductResponse.model_validate(product)


@router.get("/{product_id}", response_model=ProductResponse)
async def get_product(
    product_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    org_id: uuid.UUID = Depends(get_org_id),
    db: AsyncSession = Depends(get_db),
) -> ProductResponse:
    """Get a single product by ID."""
    result = await db.execute(
        select(Product)
        .where(Product.id == product_id)
        .where(Product.org_id == org_id)
    )
    product = result.scalar_one_or_none()

    if product is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Product not found",
        )

    return ProductResponse.model_validate(product)


@router.put("/{product_id}", response_model=ProductResponse)
async def update_product(
    product_id: uuid.UUID,
    request: ProductUpdate,
    current_user: User = Depends(get_current_user),
    org_id: uuid.UUID = Depends(get_org_id),
    db: AsyncSession = Depends(get_db),
) -> ProductResponse:
    """Update an existing product."""
    result = await db.execute(
        select(Product)
        .where(Product.id == product_id)
        .where(Product.org_id == org_id)
    )
    product = result.scalar_one_or_none()

    if product is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Product not found",
        )

    update_data = request.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(product, field, value)

    await db.flush()
    await db.refresh(product)

    return ProductResponse.model_validate(product)


@router.delete("/{product_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_product(
    product_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    org_id: uuid.UUID = Depends(get_org_id),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Delete a product."""
    result = await db.execute(
        select(Product)
        .where(Product.id == product_id)
        .where(Product.org_id == org_id)
    )
    product = result.scalar_one_or_none()

    if product is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Product not found",
        )

    await db.delete(product)
    await db.flush()
