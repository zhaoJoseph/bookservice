from typing import Annotated

from fastapi import APIRouter, Depends, status, Body, Form, Request, Response
from typing import Optional
from fastapi.security import OAuth2PasswordRequestForm

from fastapi_users.authentication import JWTStrategy
from fastapi_users.exceptions import UserAlreadyExists, UserAlreadyVerified, UserNotExists, InvalidVerifyToken

from .dependencies import current_active_user, get_jwt_strategy
from ..config import settings
from ..models import User, UserManager, get_user_manager
from ..schemas import Status, Token, UserCreate, UserRead
from .exceptions import EmailExists, IncorrectLogin, UserSuspended, InvalidToken, UserNotFound
from .utils import generate_verification_token, genres_to_string
from .schemas import UserForm

router: APIRouter = APIRouter()

@router.post("/register", response_model=UserRead, status_code=status.HTTP_201_CREATED)
async def register(
    form_data: Annotated[UserForm, Form()], 
    user_manager: Annotated[UserManager, Depends(get_user_manager)]
):
    try:
        user_create = UserCreate(**form_data.model_dump())
    except Exception as e:
        from fastapi import HTTPException
        raise HTTPException(status_code=422, detail=str(e))
    
    try:
        user_create.is_active = False
        user_create.is_verified = False
        user_create.status = Status.inactive
        user_create.genres = genres_to_string(form_data.genres)
        user = await user_manager.create(user_create, safe=True)
    except UserAlreadyExists:
        raise EmailExists()
    return user

@router.post("/token", response_model=Token)
async def login(
    response: Response,
    form_data: Annotated[OAuth2PasswordRequestForm, Depends()],
    user_manager: Annotated[UserManager, Depends(get_user_manager)],
    strategy: Annotated[JWTStrategy, Depends(get_jwt_strategy)],
):
    user = await user_manager.authenticate(form_data)

    if user is None:
        raise IncorrectLogin()

    if user.status in (Status.suspended, Status.inactive):
        raise UserSuspended()

    access_token = await strategy.write_token(user)

    response.set_cookie(
        key="access_token",
        value=access_token,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        max_age=3600,
        path="/"
    )

    response.headers["HX-Redirect"] = "/catalog"

    return Token(accessToken=access_token, tokenType="bearer")


@router.get("/me", response_model=UserRead)
async def read_current_user(user: Annotated[User, Depends(current_active_user)]):
    return user

@router.get("/verify", response_model=UserRead)
async def verify_user(token: str, user_manager: UserManager = Depends(get_user_manager)):
    try:
        user = await user_manager.verify(token)
    except InvalidVerifyToken:
        raise InvalidToken()
    except UserNotExists:
        raise UserNotFound()
    except UserAlreadyVerified:
        raise UserAlreadyVerified()
    return user

@router.post("/request-verify-token", status_code=status.HTTP_202_ACCEPTED)
async def request_verify_token(
    email: Annotated[str, Form()],
    user_manager: Annotated[UserManager, Depends(get_user_manager)],
    request: Request
):
    try:
        user = await user_manager.get_by_email(email)
        await user_manager.request_verify(user, request)
    except UserNotExists:
        pass 
    return {"detail": "Verification email sent if account exists"}