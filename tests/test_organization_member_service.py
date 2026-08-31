from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.services.organization_member import OrganizationMemberService


class FakeDatabase:
    async def commit(self):
        pass

    async def rollback(self):
        pass

    async def refresh(self, item):
        return item


class FakeMemberships:
    async def get_by_organization_and_user(self, organization_id, user_id):
        return None


class FakeRoles:
    async def get_by_id(self, role_id):
        return SimpleNamespace(id=role_id, name="member")


class FakeUsers:
    async def get_by_id(self, user_id):
        return None


@pytest.mark.asyncio
async def test_add_member_rejects_unknown_user_before_insert():
    service = OrganizationMemberService(
        db=FakeDatabase(),
        repository=FakeMemberships(),
        role_repository=FakeRoles(),
        user_repository=FakeUsers(),
    )

    with pytest.raises(HTTPException) as exc:
        await service.add_member(
            organization_id=uuid4(),
            user_id=uuid4(),
            role_id=uuid4(),
        )

    assert exc.value.status_code == 404
    assert exc.value.detail == "User not found"
