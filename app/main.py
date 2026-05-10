"""
FastAPI Main Application Module — Branch 1: Auth and User Management

This branch ships only the auth foundation. The /calculations BREAD endpoints,
profile/password/stats/admin endpoints, and Alembic migrations land in
subsequent feature branches.
"""

from contextlib import asynccontextmanager
from datetime import datetime, timezone, timedelta

from fastapi import FastAPI, Depends, HTTPException, status, Request
from fastapi.security import OAuth2PasswordRequestForm
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_active_user
from app.models.user import User
from app.schemas.token import TokenResponse
from app.schemas.user import UserCreate, UserResponse, UserLogin
from app.database import Base, get_db, engine


# ----------------------------------------------------------------------------
# Lifespan: create tables on startup (Alembic replaces this in a later branch)
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


# ----------------------------------------------------------------------------
# Static files and templates
# ----------------------------------------------------------------------------
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")


# ----------------------------------------------------------------------------
# Web routes
# ----------------------------------------------------------------------------
@app.get("/", response_class=HTMLResponse, tags=["web"])
def read_index(request: Request):
    """Landing page with links to register and login."""
    return templates.TemplateResponse("index.html", {"request": request})


@app.get("/login", response_class=HTMLResponse, tags=["web"])
def login_page(request: Request):
    """Login form."""
    return templates.TemplateResponse("login.html", {"request": request})


@app.get("/register", response_class=HTMLResponse, tags=["web"])
def register_page(request: Request):
    """Registration form."""
    return templates.TemplateResponse("register.html", {"request": request})


# ----------------------------------------------------------------------------
# Health
# ----------------------------------------------------------------------------
@app.get("/health", tags=["health"])
def read_health():
    return {"status": "ok"}


# ----------------------------------------------------------------------------
# Auth: register
# ----------------------------------------------------------------------------
@app.post(
    "/auth/register",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["auth"],
)
def register(user_create: UserCreate, db: Session = Depends(get_db)):
    """Create a new user account."""
    user_data = user_create.dict(exclude={"confirm_password"})
    try:
        user = User.register(db, user_data)
        db.commit()
        db.refresh(user)
        return user
    except ValueError as e:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


# ----------------------------------------------------------------------------
# Auth: login (JSON body)
# ----------------------------------------------------------------------------
@app.post("/auth/login", response_model=TokenResponse, tags=["auth"])
def login_json(user_login: UserLogin, db: Session = Depends(get_db)):
    """Login with JSON payload. Returns access token, refresh token, and user info."""
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


# ----------------------------------------------------------------------------
# Auth: login (form data — for Swagger's Authorize button)
# ----------------------------------------------------------------------------
@app.post("/auth/token", tags=["auth"])
def login_form(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db),
):
    """Login with form data (used by Swagger UI's Authorize)."""
    auth_result = User.authenticate(db, form_data.username, form_data.password)
    if auth_result is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return {"access_token": auth_result["access_token"], "token_type": "bearer"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="127.0.0.1", port=8001, log_level="info")
