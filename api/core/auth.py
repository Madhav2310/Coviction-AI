"""

Shared auth helpers — demo user resolution (MVP: no real auth yet).

"""

from uuid import UUID



from fastapi import HTTPException

from sqlalchemy import select

from sqlalchemy.ext.asyncio import AsyncSession



from models.tables import User



DEMO_USER_EMAIL = "demo@coviction.ai"





async def get_user_id(db: AsyncSession) -> UUID:

    """Resolve the demo user's ID. Raises 500 if not found."""

    result = await db.execute(select(User).where(User.email == DEMO_USER_EMAIL))

    user = result.scalar_one_or_none()

    if not user:

        raise HTTPException(status_code=500, detail="Demo user not found")

    return user.id





async def ensure_demo_user(db: AsyncSession) -> User:

    """Get or create the demo user."""

    result = await db.execute(select(User).where(User.email == DEMO_USER_EMAIL))

    user = result.scalar_one_or_none()

    if not user:

        user = User(email=DEMO_USER_EMAIL)

        db.add(user)

        await db.commit()

        await db.refresh(user)

    return user
