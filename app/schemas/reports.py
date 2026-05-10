"""
Stats / Reports / Admin Schemas

These Pydantic models support the new report and admin endpoints. They are
deliberately separate from the existing user/calculation schemas so the
original modules remain easy to read and diff.
"""

from datetime import datetime
from typing import Dict, List, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class CalculationTypeBreakdown(BaseModel):
    """One row of the per-type breakdown returned by the stats endpoint."""

    type: str = Field(..., description="Calculation type (e.g., 'addition')")
    count: int = Field(..., ge=0, description="Number of calculations of this type")
    average_inputs: float = Field(
        ...,
        description="Average number of operands across this type's calculations",
    )
    last_used_at: Optional[datetime] = Field(
        None, description="Timestamp of the most recent calculation of this type"
    )

    model_config = ConfigDict(from_attributes=True)


class UserStatsResponse(BaseModel):
    """Aggregate usage statistics for the authenticated user."""

    total_calculations: int = Field(..., ge=0)
    total_operands: int = Field(
        ..., ge=0, description="Sum of operand counts across all calculations"
    )
    average_operands_per_calculation: float = Field(
        ...,
        description="Mean operands per calculation (0 when there are none)",
    )
    average_result: Optional[float] = Field(
        None, description="Mean of all stored results (None when there are none)"
    )
    breakdown: List[CalculationTypeBreakdown] = Field(default_factory=list)
    most_used_type: Optional[str] = Field(
        None, description="Calculation type with the highest count, if any"
    )
    first_calculation_at: Optional[datetime] = None
    last_calculation_at: Optional[datetime] = None

    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={
            "example": {
                "total_calculations": 7,
                "total_operands": 18,
                "average_operands_per_calculation": 2.57,
                "average_result": 31.43,
                "breakdown": [
                    {
                        "type": "addition",
                        "count": 4,
                        "average_inputs": 2.5,
                        "last_used_at": "2025-04-15T12:30:00Z",
                    }
                ],
                "most_used_type": "addition",
                "first_calculation_at": "2025-04-01T09:00:00Z",
                "last_calculation_at": "2025-04-15T12:30:00Z",
            }
        },
    )


class PasswordChangeResponse(BaseModel):
    """A single password-change audit record."""

    id: UUID
    user_id: UUID
    changed_by_user_id: Optional[UUID] = None
    changed_at: datetime
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None

    # Joined fields, populated by the admin endpoint
    username: Optional[str] = None
    email: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class AdminCalculationResponse(BaseModel):
    """Calculation row enriched with owner info, used by the admin view."""

    id: UUID
    user_id: UUID
    type: str
    inputs: List[float]
    result: Optional[float] = None
    created_at: datetime
    updated_at: datetime

    username: Optional[str] = None
    email: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class AdminUserResponse(BaseModel):
    """A user record returned by ``GET /admin/users``."""

    id: UUID
    username: str
    email: str
    first_name: str
    last_name: str
    is_active: bool
    is_verified: bool
    is_admin: bool
    created_at: datetime
    updated_at: datetime
    last_login: Optional[datetime] = None
    calculation_count: int = 0

    model_config = ConfigDict(from_attributes=True)


class AdminStatsResponse(BaseModel):
    """Site-wide stats shown on the admin dashboard."""

    total_users: int
    active_users: int
    admin_users: int
    total_calculations: int
    total_password_changes: int
    calculations_by_type: Dict[str, int] = Field(default_factory=dict)

    model_config = ConfigDict(from_attributes=True)
