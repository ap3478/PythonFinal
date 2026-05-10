"""
FastAPI Main Application Module — Branch 4: Profile & Password Management

Builds on the auth + BREAD foundation by adding:
- GET/PUT /users/me      — profile read and update
- POST /users/me/change-password  — re-hash and write an audit row

Stats and admin endpoints land in subsequent branches.
"""

from contextlib import asynccontextmanager
from datetime import datetime, timezone, timedelta
from uuid import UUID
from typing import List, Optional

from fastapi import FastAPI, Depends, HTTPException, status, Request, Query
from fastapi.security import OAuth2PasswordRequestForm
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.auth.dependencies import (
    get_current_active_user,
    get_current_user_db,
    get_current_admin_user,
)
from app.models.calculation import Calculation
from app.models.password_change import PasswordChange
from app.models.user import User
from app.schemas.calculation import (
    CalculationBase,
    CalculationResponse,
    CalculationUpdate,
)
from app.schemas.token import TokenResponse
from app.schemas.user import (
    UserCreate,
    UserResponse,
    UserLogin,
    UserUpdate,
    PasswordUpdate,
)
from app.schemas.reports import (
    UserStatsResponse,
    CalculationTypeBreakdown,
    PasswordChangeResponse,
    AdminCalculationResponse,
    AdminUserResponse,
    AdminStatsResponse,
)
from app.database import Base, get_db, engine


# ----------------------------------------------------------------------------
# Lifespan
# ----------------------------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    print("Creating tables...")
    Base.metadata.create_all(bind=engine)
    print("Tables created successfully!")
    yield


app = FastAPI(
    title="Calculations API",
    description="API for managing calculations",
    version="1.0.0",
    lifespan=lifespan,
)


app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")


# ----------------------------------------------------------------------------
# Web routes
# ----------------------------------------------------------------------------
@app.get("/", response_class=HTMLResponse, tags=["web"])
def read_index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


@app.get("/login", response_class=HTMLResponse, tags=["web"])
def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})


@app.get("/register", response_class=HTMLResponse, tags=["web"])
def register_page(request: Request):
    return templates.TemplateResponse("register.html", {"request": request})


@app.get("/dashboard", response_class=HTMLResponse, tags=["web"])
def dashboard_page(request: Request):
    return templates.TemplateResponse("dashboard.html", {"request": request})


@app.get("/dashboard/view/{calc_id}", response_class=HTMLResponse, tags=["web"])
def view_calculation_page(request: Request, calc_id: str):
    return templates.TemplateResponse(
        "view_calculation.html", {"request": request, "calc_id": calc_id}
    )


@app.get("/dashboard/edit/{calc_id}", response_class=HTMLResponse, tags=["web"])
def edit_calculation_page(request: Request, calc_id: str):
    return templates.TemplateResponse(
        "edit_calculation.html", {"request": request, "calc_id": calc_id}
    )


@app.get("/profile", response_class=HTMLResponse, tags=["web"])
def profile_page(request: Request):
    """Profile page: edit username/email/name and change password."""
    return templates.TemplateResponse("profile.html", {"request": request})


@app.get("/stats", response_class=HTMLResponse, tags=["web"])
def stats_page(request: Request):
    """Personal usage stats / report page."""
    return templates.TemplateResponse("stats.html", {"request": request})


@app.get("/admin", response_class=HTMLResponse, tags=["web"])
def admin_page(request: Request):
    """Admin dashboard: all users, all calculations, password-change audit."""
    return templates.TemplateResponse("admin.html", {"request": request})


# ----------------------------------------------------------------------------
# Health
# ----------------------------------------------------------------------------
@app.get("/health", tags=["health"])
def read_health():
    return {"status": "ok"}


# ----------------------------------------------------------------------------
# Auth
# ----------------------------------------------------------------------------
@app.post(
    "/auth/register",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["auth"],
)
def register(user_create: UserCreate, db: Session = Depends(get_db)):
    user_data = user_create.dict(exclude={"confirm_password"})
    try:
        user = User.register(db, user_data)
        db.commit()
        db.refresh(user)
        return user
    except ValueError as e:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@app.post("/auth/login", response_model=TokenResponse, tags=["auth"])
def login_json(user_login: UserLogin, db: Session = Depends(get_db)):
    auth_result = User.authenticate(db, user_login.username, user_login.password)
    if auth_result is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    user = auth_result["user"]
    db.commit()

    expires_at = auth_result.get("expires_at")
    if expires_at and expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    else:
        expires_at = datetime.now(timezone.utc) + timedelta(minutes=15)

    return TokenResponse(
        access_token=auth_result["access_token"],
        refresh_token=auth_result["refresh_token"],
        token_type="bearer",
        expires_at=expires_at,
        user_id=user.id,
        username=user.username,
        email=user.email,
        first_name=user.first_name,
        last_name=user.last_name,
        is_active=user.is_active,
        is_verified=user.is_verified,
    )


@app.post("/auth/token", tags=["auth"])
def login_form(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db),
):
    auth_result = User.authenticate(db, form_data.username, form_data.password)
    if auth_result is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return {"access_token": auth_result["access_token"], "token_type": "bearer"}


# ----------------------------------------------------------------------------
# User profile
# ----------------------------------------------------------------------------
@app.get("/users/me", response_model=UserResponse, tags=["users"])
def read_current_user(current_user: User = Depends(get_current_user_db)):
    """Return the full profile of the authenticated user."""
    return current_user


@app.put("/users/me", response_model=UserResponse, tags=["users"])
def update_current_user(
    update: UserUpdate,
    current_user: User = Depends(get_current_user_db),
    db: Session = Depends(get_db),
):
    """Update first/last name, username, or email. Username/email collisions return 400."""
    payload = update.model_dump(exclude_unset=True)
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No fields provided to update",
        )

    new_username = payload.get("username")
    new_email = payload.get("email")
    if new_username or new_email:
        conflict_q = db.query(User).filter(User.id != current_user.id)
        clauses = []
        if new_username:
            clauses.append(User.username == new_username)
        if new_email:
            clauses.append(User.email == new_email)
        if clauses and conflict_q.filter(or_(*clauses)).first() is not None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Username or email already in use",
            )

    for key, value in payload.items():
        setattr(current_user, key, value)
    current_user.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(current_user)
    return current_user


@app.post(
    "/users/me/change-password",
    status_code=status.HTTP_200_OK,
    tags=["users"],
)
def change_password(
    payload: PasswordUpdate,
    request: Request,
    current_user: User = Depends(get_current_user_db),
    db: Session = Depends(get_db),
):
    """
    Change the authenticated user's password.

    Requires the current password as proof of identity. On success, writes a
    PasswordChange audit record (user_id, IP, User-Agent, timestamp).
    """
    if not current_user.verify_password(payload.current_password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Current password is incorrect",
        )

    current_user.password = User.hash_password(payload.new_password)
    current_user.updated_at = datetime.now(timezone.utc)

    audit = PasswordChange(
        user_id=current_user.id,
        changed_by_user_id=current_user.id,
        ip_address=(request.client.host if request.client else None),
        user_agent=request.headers.get("user-agent"),
    )
    db.add(audit)
    db.commit()
    return {"detail": "Password updated successfully"}





# ----------------------------------------------------------------------------
# Per-user Stats / Report Endpoint
# ----------------------------------------------------------------------------
@app.get(
    "/users/me/stats",
    response_model=UserStatsResponse,
    tags=["users"],
)
def my_stats(
    current_user: User = Depends(get_current_user_db),
    db: Session = Depends(get_db),
):
    """
    Aggregate calculation statistics for the authenticated user.
    Counts, per-type breakdown, average operands, and average result.
    """
    rows = (
        db.query(Calculation)
        .filter(Calculation.user_id == current_user.id)
        .all()
    )

    total = len(rows)
    if total == 0:
        return UserStatsResponse(
            total_calculations=0,
            total_operands=0,
            average_operands_per_calculation=0.0,
            average_result=None,
            breakdown=[],
            most_used_type=None,
            first_calculation_at=None,
            last_calculation_at=None,
        )

    total_operands = sum(len(r.inputs or []) for r in rows)
    results = [r.result for r in rows if r.result is not None]
    avg_result = (sum(results) / len(results)) if results else None

    by_type = {}
    for r in rows:
        by_type.setdefault(r.type, []).append(r)

    breakdown = [
        CalculationTypeBreakdown(
            type=t,
            count=len(items),
            average_inputs=(sum(len(i.inputs or []) for i in items) / len(items)),
            last_used_at=max(i.created_at for i in items),
        )
        for t, items in sorted(by_type.items(), key=lambda kv: -len(kv[1]))
    ]

    most_used_type = breakdown[0].type if breakdown else None

    return UserStatsResponse(
        total_calculations=total,
        total_operands=total_operands,
        average_operands_per_calculation=total_operands / total,
        average_result=avg_result,
        breakdown=breakdown,
        most_used_type=most_used_type,
        first_calculation_at=min(r.created_at for r in rows),
        last_calculation_at=max(r.created_at for r in rows),
    )

# ----------------------------------------------------------------------------
# Calculations BREAD
# ----------------------------------------------------------------------------
@app.post(
    "/calculations",
    response_model=CalculationResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["calculations"],
)
def create_calculation(
    calculation_data: CalculationBase,
    current_user=Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    try:
        new_calculation = Calculation.create(
            calculation_type=calculation_data.type,
            user_id=current_user.id,
            inputs=calculation_data.inputs,
        )
        new_calculation.result = new_calculation.get_result()
        db.add(new_calculation)
        db.commit()
        db.refresh(new_calculation)
        return new_calculation
    except ValueError as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@app.get("/calculations", response_model=List[CalculationResponse], tags=["calculations"])
def list_calculations(
    current_user=Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    return (
        db.query(Calculation)
        .filter(Calculation.user_id == current_user.id)
        .all()
    )


@app.get(
    "/calculations/{calc_id}",
    response_model=CalculationResponse,
    tags=["calculations"],
)
def get_calculation(
    calc_id: str,
    current_user=Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    try:
        calc_uuid = UUID(calc_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid calculation id format.")
    calculation = (
        db.query(Calculation)
        .filter(Calculation.id == calc_uuid, Calculation.user_id == current_user.id)
        .first()
    )
    if not calculation:
        raise HTTPException(status_code=404, detail="Calculation not found.")
    return calculation


@app.put(
    "/calculations/{calc_id}",
    response_model=CalculationResponse,
    tags=["calculations"],
)
def update_calculation(
    calc_id: str,
    calculation_update: CalculationUpdate,
    current_user=Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    try:
        calc_uuid = UUID(calc_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid calculation id format.")
    calculation = (
        db.query(Calculation)
        .filter(Calculation.id == calc_uuid, Calculation.user_id == current_user.id)
        .first()
    )
    if not calculation:
        raise HTTPException(status_code=404, detail="Calculation not found.")

    if calculation_update.inputs is not None:
        calculation.inputs = calculation_update.inputs
        calculation.result = calculation.get_result()

    calculation.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(calculation)
    return calculation


@app.delete(
    "/calculations/{calc_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    tags=["calculations"],
)
def delete_calculation(
    calc_id: str,
    current_user=Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    try:
        calc_uuid = UUID(calc_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid calculation id format.")
    calculation = (
        db.query(Calculation)
        .filter(Calculation.id == calc_uuid, Calculation.user_id == current_user.id)
        .first()
    )
    if not calculation:
        raise HTTPException(status_code=404, detail="Calculation not found.")
    db.delete(calculation)
    db.commit()
    return None




# ----------------------------------------------------------------------------
# Admin Endpoints
# ----------------------------------------------------------------------------
@app.get(
    "/admin/users",
    response_model=List[AdminUserResponse],
    tags=["admin"],
)
def admin_list_users(
    _admin: User = Depends(get_current_admin_user),
    db: Session = Depends(get_db),
):
    """List every user in the system. Admin only."""
    rows = db.query(User).order_by(User.created_at.desc()).all()
    out = []
    for u in rows:
        out.append(
            AdminUserResponse(
                id=u.id,
                username=u.username,
                email=u.email,
                first_name=u.first_name,
                last_name=u.last_name,
                is_active=bool(u.is_active),
                is_verified=bool(u.is_verified),
                is_admin=bool(getattr(u, "is_admin", False)),
                created_at=u.created_at,
                updated_at=u.updated_at,
                last_login=u.last_login,
                calculation_count=(
                    db.query(func.count(Calculation.id))
                    .filter(Calculation.user_id == u.id)
                    .scalar()
                    or 0
                ),
            )
        )
    return out


@app.get(
    "/admin/calculations",
    response_model=List[AdminCalculationResponse],
    tags=["admin"],
)
def admin_list_calculations(
    limit: int = Query(200, ge=1, le=1000),
    user_id: Optional[UUID] = Query(None),
    type: Optional[str] = Query(None),
    _admin: User = Depends(get_current_admin_user),
    db: Session = Depends(get_db),
):
    """List calculations from every user. Admin only. Filters: ?user_id=, ?type=, ?limit="""
    q = (
        db.query(Calculation, User.username, User.email)
        .outerjoin(User, User.id == Calculation.user_id)
    )
    if user_id is not None:
        q = q.filter(Calculation.user_id == user_id)
    if type:
        q = q.filter(Calculation.type == type.lower())
    q = q.order_by(Calculation.created_at.desc()).limit(limit)

    out = []
    for calc, username, email in q.all():
        out.append(
            AdminCalculationResponse(
                id=calc.id,
                user_id=calc.user_id,
                type=calc.type,
                inputs=list(calc.inputs or []),
                result=calc.result,
                created_at=calc.created_at,
                updated_at=calc.updated_at,
                username=username,
                email=email,
            )
        )
    return out


@app.get(
    "/admin/password-changes",
    response_model=List[PasswordChangeResponse],
    tags=["admin"],
)
def admin_list_password_changes(
    limit: int = Query(200, ge=1, le=1000),
    user_id: Optional[UUID] = Query(None),
    _admin: User = Depends(get_current_admin_user),
    db: Session = Depends(get_db),
):
    """List password-change audit records across all users. Admin only."""
    q = (
        db.query(PasswordChange, User.username, User.email)
        .outerjoin(User, User.id == PasswordChange.user_id)
    )
    if user_id is not None:
        q = q.filter(PasswordChange.user_id == user_id)
    q = q.order_by(PasswordChange.changed_at.desc()).limit(limit)

    out = []
    for change, username, email in q.all():
        out.append(
            PasswordChangeResponse(
                id=change.id,
                user_id=change.user_id,
                changed_by_user_id=change.changed_by_user_id,
                changed_at=change.changed_at,
                ip_address=change.ip_address,
                user_agent=change.user_agent,
                username=username,
                email=email,
            )
        )
    return out


@app.get(
    "/admin/stats",
    response_model=AdminStatsResponse,
    tags=["admin"],
)
def admin_stats(
    _admin: User = Depends(get_current_admin_user),
    db: Session = Depends(get_db),
):
    """High-level system stats for the admin dashboard."""
    total_users = db.query(func.count(User.id)).scalar() or 0
    active_users = (
        db.query(func.count(User.id)).filter(User.is_active.is_(True)).scalar() or 0
    )
    admin_users = (
        db.query(func.count(User.id)).filter(User.is_admin.is_(True)).scalar() or 0
    )
    total_calcs = db.query(func.count(Calculation.id)).scalar() or 0
    total_pwd = db.query(func.count(PasswordChange.id)).scalar() or 0

    by_type_rows = (
        db.query(Calculation.type, func.count(Calculation.id))
        .group_by(Calculation.type)
        .all()
    )
    by_type = {t: int(c) for t, c in by_type_rows}

    return AdminStatsResponse(
        total_users=int(total_users),
        active_users=int(active_users),
        admin_users=int(admin_users),
        total_calculations=int(total_calcs),
        total_password_changes=int(total_pwd),
        calculations_by_type=by_type,
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="127.0.0.1", port=8001, log_level="info")
