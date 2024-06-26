from sqlalchemy import Numeric, Column, ForeignKey, DateTime, Enum, Integer
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
import enum

from app.models.model_base import BaseModel as Base

class ContractStatusEnum(enum.Enum):
    active = "active"
    expired = "expired"
    terminated = "terminated"

class Contract(Base):
    __tablename__ = 'contract'
    contract_id = Column(UUID(as_uuid=True), primary_key=True)
    contract_type_id = Column(UUID(as_uuid=True), ForeignKey('contract_type.contract_type_id'))
    contract_details = Column(UUID(as_uuid=True))
    payment_type_id = Column(UUID(as_uuid=True), ForeignKey('payment_types.payment_type_id'))
    num_invoices = Column(Integer)
    payment_amount = Column(Numeric(10, 2))
    fee_percentage = Column(Numeric(5, 2))
    fee_amount = Column(Numeric(10, 2))
    date_signed = Column(DateTime(timezone=True))
    start_date = Column(DateTime(timezone=True))
    end_date = Column(DateTime(timezone=True))
    contract_status = Column(Enum(ContractStatusEnum))

    contract_documents = relationship('Documents', secondary='contract_documents', back_populates='contract')
    invoices = relationship('Invoice', secondary='contract_invoice', back_populates='contracts')

    under_contract = relationship('UnderContract', back_populates='contract')
    contract_type = relationship('ContractType', back_populates='contracts')
    payment_type = relationship('PaymentTypes', back_populates='contracts')