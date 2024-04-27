from uuid import UUID
from pydantic import ValidationError, BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.exc import NoResultFound
from sqlalchemy.orm import selectinload
from typing import Any, Dict, List, Type, Optional, Union, override

from app.dao.base_dao import BaseDAO
from app.dao.address_dao import AddressDAO
from app.dao.entity_dao import EntityDAO
from app.dao.role_dao import RoleDAO
from app.utils.response import DAOResponse
from app.models import User, Addresses, Role, EntityAddress
from app.schema import UserResponse, Address, AddressBase, UserAuthInfo, UserUpdateSchema, UserCreateSchema, UserEmergencyInfo, UserBase, UserEmployerInfo, User as UserSchema

class UserDAO(BaseDAO[User]):
    def __init__(self, model: Type[User]):
        super().__init__(model)
        self.primary_key = "user_id"

    @override
    async def create(self, db_session: AsyncSession, obj_in: Union[UserCreateSchema | Dict]) -> DAOResponse[UserResponse]:
        try:
            user_data = obj_in
            
            # check if user exists
            existing_user : User = await self._user_exists(db_session, user_data.get('email'))
            if existing_user:
                return DAOResponse[UserResponse](success=False, error="User already exists", data=UserResponse.from_orm_model(existing_user))

            # extract base information
            user_info = self._extract_data(user_data, UserBase)

            # create new user
            new_user: User = await super().create(db_session=db_session, obj_in=user_info)
            user_id = new_user.user_id

            # add additional info if exists
            await self._handle_user_details(db_session, user_id, user_data)
            user_load_addr: User = await self.query(
                db_session=db_session,
                filters={f"{self.primary_key}":user_id},
                single=True,
                options=[selectinload(User.addresses)]
            )
            
            # commit object to db session
            await self.commit_and_refresh(db_session, user_load_addr)
            return DAOResponse[UserResponse](success=True, data=UserResponse.from_orm_model(new_user))
        
        except ValidationError as e:
            return DAOResponse(success=False, validation_error=str(e))
        except Exception as e:
            await db_session.rollback()
            return DAOResponse[UserResponse](success=False, error=f"Fatal {str(e)}")
    
    @override
    async def update(self, db_session: AsyncSession, db_obj: User, obj_in: UserUpdateSchema) -> DAOResponse[UserResponse]:
        try:
            # update user info
            existing_user : User = await super().update(db_session=db_session, db_obj=db_obj, obj_in=obj_in)
            user_id = existing_user.user_id

            # add additional info if exists
            await self._handle_user_details(db_session, user_id, obj_in.model_dump())
            
            # commit object to db session
            await self.commit_and_refresh(db_session, existing_user)
            return DAOResponse[UserResponse](success=True, data=UserResponse.from_orm_model(existing_user))
        
        except ValidationError as e:
            return DAOResponse(success=False, validation_error=str(e))
        except Exception as e:
            await db_session.rollback()
            return DAOResponse[UserResponse](success=False, error=f"Fatal Update {str(e)}")
    
    @override
    async def get_all(self, db_session: AsyncSession) -> DAOResponse[List[UserResponse]]:
        result = await super().get_all(db_session=db_session)
        
        # check if no result
        if not result:
            return DAOResponse(success=True, data=[])

        return DAOResponse[List[UserResponse]](success=True, data=[UserResponse.from_orm_model(r) for r in result])
    
    @override
    async def get(self, db_session: AsyncSession, id: Union[UUID | Any | int]) -> DAOResponse[UserResponse]:

        result = await super().get(db_session=db_session, id=id)

        # check if no result
        if not result:
            return DAOResponse(success=True, data={})

        return DAOResponse[UserResponse](success=True, data=UserResponse.from_orm_model(result))
 
    async def _user_exists(self, db_session: AsyncSession, email: str) -> bool:
        existing_user : User = await self.query(db_session=db_session, filters={"email": email}, single=True)
        return existing_user

    async def _handle_user_details(self, db_session: AsyncSession, user_id: UUID, user_data: UserSchema):
        details_methods = {
            'user_emergency_info': (self.add_emergency_info, UserEmergencyInfo),
            'user_employer_info': (self.add_employment_info, UserEmployerInfo),
            'user_auth_info': (self.add_auth_info, UserAuthInfo),
            'address': (self.add_user_address, Address if 'address' in user_data and 'address_id' in user_data['address'] else AddressBase)
        }

        results = {}
        
        for detail_key, (method, schema) in details_methods.items():
            detail_data = self._extract_data(user_data, schema, nested_key=detail_key)

            if detail_data is not None:
                results[detail_key] = await method(db_session, user_id, schema(**detail_data))
                
        return results
    
    def _extract_data(self, data: dict, schema: Type[BaseModel], nested_key: Optional[str] = None) -> dict:
        if nested_key:
            data = data.get(nested_key, {})

        return {key: data[key] for key in data if key in schema.model_fields} if data else None
    
    async def add_user_role(self, db_session: AsyncSession, user_id: str, role_alias: str) -> DAOResponse:
        role_dao = RoleDAO(Role)

        try:
            async with db_session as db:
                user: User = await self.query(db_session=db, filters={f"{self.primary_key}": user_id},single=True,options=[selectinload(User.roles)])
                role: Role = await role_dao.query(db_session=db, filters={"alias": role_alias}, single=True)

                if user is None or role is None:
                    raise NoResultFound()
        
                if role in user.roles:
                    return DAOResponse[dict](success=False, error="Role already exists for the user", data=user.to_dict())
                
                user.roles.append(role)
                await self.commit_and_refresh(db, user)

                return DAOResponse[dict](success=True, data=user.to_dict())
        except NoResultFound as e:
            return DAOResponse[dict](success=False, error="User or Role not found")
        except Exception as e:
            return DAOResponse[User](success=False, error=str(e))
        
    async def add_employment_info(self, db_session: AsyncSession, user_id: str, employee_info: UserEmployerInfo) -> Optional[User]:
        try:
            user : User = await self.query(db_session=db_session, filters={f"{self.primary_key}": user_id}, single=True)
            updated_user : User = await super().update(db_session=db_session, db_obj=user, obj_in=employee_info)

            return updated_user
        except NoResultFound:
            pass

    async def add_emergency_info(self, db_session: AsyncSession, user_id: str,  emergency_info: UserEmergencyInfo) -> Optional[User]:
        try:
            user : User = await self.query(db_session=db_session, filters={f"{self.primary_key}": user_id}, single=True)
            updated_user : User = await super().update(db_session=db_session, db_obj=user, obj_in=emergency_info)

            return updated_user
        except NoResultFound:
            pass

    async def add_auth_info(self, db_session: AsyncSession, user_id: str,  auth_info: UserAuthInfo) -> Optional[User]:
        try:
            user : User = await self.query(db_session=db_session, filters={f"{self.primary_key}": user_id}, single=True)
            updated_user : User = await super().update(db_session=db_session, db_obj=user, obj_in=auth_info)

            return updated_user
        except NoResultFound:
            pass

    async def add_user_address(self, db_session: AsyncSession, entity_id: UUID, address_obj: Union[Address, AddressBase]) -> Optional[Addresses| dict]:
        address_dao = AddressDAO(Addresses)
        entity_address_dao = EntityDAO(EntityAddress)

        try:
            # Check if the address already exists
            address_key = "address_id"
            existing_address = await address_dao.query(db_session=db_session, filters={address_key: address_obj.address_id}, single=True, options=[selectinload(Addresses.users)]) if address_key in address_obj.model_fields else None
            
            if existing_address:
                # Update the existing address
                obj_data = self._extract_data(address_obj.model_dump(), Address)
                addr_data = Address(**obj_data)
                
                address : Addresses = await address_dao.update(db_session=db_session, db_obj=existing_address, obj_in=addr_data.model_dump())

            else:
                # Create a new Address instance from the validated address_data
                address : Addresses = await address_dao.create(db_session=db_session, address_data=address_obj)
            
                # Link user model to new addresses
                await entity_address_dao.create(db_session = db_session, obj_in = {
                    "entity_type": self.model.__name__,
                    "entity_id": entity_id,
                    "address_id": address.address_id,
                    "emergency_address": False,
                    "emergency_address_hash": ""
                })

            return address
        
        except Exception as e:
            return DAOResponse[dict](success=False, error=f"An unexpected error occurred {e}")