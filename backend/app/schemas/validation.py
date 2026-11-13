from datetime import date
from typing import Literal
from pydantic import BaseModel, Field, field_validator


class LoginSchema(BaseModel):
    email: str
    password: str


class CreateLotSchema(BaseModel):
    lot_code: str = Field(..., min_length=3, max_length=64)
    supplier_code: str = Field(..., min_length=2, max_length=32)
    material_name: str = Field(..., min_length=2, max_length=120)
    quantity_received: float = Field(..., gt=0)
    unit_of_measure: str = Field(default="kg", max_length=20)


class CreateBatchSchema(BaseModel):
    batch_code: str = Field(..., min_length=3, max_length=64)
    machine_id: str = Field(..., min_length=2, max_length=32)
    units_produced: int = Field(..., gt=0)
    qc_status: str = Field(default="PASS")
    defect_rate_pct: float = Field(default=0.0, ge=0.0, le=100.0)


class OperatorBatchSchema(BaseModel):
    batch_code: str = Field(..., min_length=3, max_length=64)
    production_date: date
    shift: Literal["A", "B", "C"]
    machine_id: str = Field(..., min_length=2, max_length=32)
    operator_id: str = Field(..., min_length=2, max_length=32)
    input_lot_ref: str = Field(..., min_length=3, max_length=64)
    units_produced: int = Field(..., gt=0)
    cycle_time_min: float = Field(..., gt=0, le=1440)


class CreateRelationSchema(BaseModel):
    parent_type: str
    parent_code: str
    child_type: str
    child_code: str
    quantity_consumed: float = Field(..., gt=0)
    snapshot_version: int = Field(default=1, ge=1)

    @field_validator("parent_type")
    @classmethod
    def validate_parent_type(cls, v: str) -> str:
        v = v.upper()
        if v not in ("LOT", "BATCH"):
            raise ValueError("parent_type must be LOT or BATCH")
        return v

    @field_validator("child_type")
    @classmethod
    def validate_child_type(cls, v: str) -> str:
        v = v.upper()
        if v not in ("BATCH", "DISPATCH"):
            raise ValueError("child_type must be BATCH or DISPATCH")
        return v


class CreateDispatchSchema(BaseModel):
    dispatch_code: str = Field(..., min_length=3, max_length=64)
    buyer_code: str = Field(..., min_length=2, max_length=32)
    quantity_pcs: int = Field(..., gt=0)
    parent_batches: list[str] = Field(..., min_length=1)


class RecordTxSchema(BaseModel):
    tx_hash: str = Field(..., min_length=66, max_length=66)
    contract_name: str
    function_name: str
    sender_address: str | None = None
    reference_id: str | None = None
