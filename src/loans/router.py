from fastapi import APIRouter
from .schemas import Loan, LoanListQuery, LoanListQueryAdmin, LoanUpdate, LoanPublic
from .dependencies import get_loan_service

from typing import Annotated
from fastapi import Depends
from ..auth.dependencies import current_active_user
from ..books.dependencies import require_admin
from ..models import User

from .services import LoanService

import math
from typing import Annotated
from fastapi import APIRouter, Depends, Header, Request, status

from fastapi.templating import Jinja2Templates


router = APIRouter()

templates = Jinja2Templates(directory="templates")

@router.get("/search", response_model=LoanPublic)
async def get_loan_search(
    request: Request,
    user: Annotated[User, Depends(current_active_user)],
):
    context = {
        "request": request,
    }

    return templates.TemplateResponse(request, "partials/loan_modal.html", context)

@router.get("/admin/search", response_model=LoanPublic)
async def get_loan_admin_search(
    request: Request,
    user: Annotated[User, Depends(current_active_user)],
):
    context = {
        "request": request,
    }

    return templates.TemplateResponse(request, "partials/loans_list_admin_modal.html", context)

@router.get("/admin", status_code=status.HTTP_200_OK)
async def get_loans_list_admin(
    request: Request,
    service: Annotated[LoanService, Depends(get_loan_service)],
    query: Annotated[LoanListQueryAdmin, Depends()],
    user: Annotated[User, Depends(require_admin)],
    hx_request: Annotated[str | None, Header(alias="HX-Request")] = None,
):
    loans, total = await service.list_loans_admin(query)

    limit = query.limit or 20
    total_pages = max(1, math.ceil(total / limit))

    current_page = max(1, query.page or 1)
    WINDOW = 2
    start_page = max(1, current_page - WINDOW)
    end_page = min(total_pages, current_page + WINDOW)

    desired_count = WINDOW * 2 + 1
    visible_count = end_page - start_page + 1
    if visible_count < desired_count:
        if start_page == 1:
            end_page = min(total_pages, start_page + desired_count - 1)
        elif end_page == total_pages:
            start_page = max(1, end_page - desired_count + 1)

    page_range = list(range(start_page, end_page + 1))

    base_params = (
        f"title={query.title or ''}&author={query.author or ''}"
        f"&isbn={query.isbn or ''}&genre={query.genre or ''}&status={query.status or ''}"
    )

    context = {
        "request": request,
        "loans": loans,
        "total": total,
        "page": current_page,
        "total_pages": total_pages,
        "page_range": page_range,
        "limit": limit,
        "base_params": base_params,
    }

    if hx_request == "true":
        return templates.TemplateResponse(request, "partials/loan_list_admin.html", context)

    return {
        "data": [Loan.model_validate(loan) for loan in loans], 
        "total": total,
        "page": current_page,
        "limit": limit,
    }

@router.get("/admin/edit/{loan_id}", status_code=status.HTTP_200_OK)
async def get_loan_edit_form(
    request: Request,
    loan_id: int,
    service: Annotated[LoanService, Depends(get_loan_service)],
    user: Annotated[User, Depends(require_admin)],
):
    loan = await service.get_by_id(loan_id, user)

    return templates.TemplateResponse(request, "partials/loan_edit_modal.html", {"request": request, "loan": loan})

@router.get("/admin/{loan_id}/approve-form", status_code=status.HTTP_200_OK)
async def get_approve_form(
    loan_id: int,
    request: Request,
    service: Annotated[LoanService, Depends(get_loan_service)],
    user: Annotated[User, Depends(require_admin)],
):
    loan = await service.get_by_id(loan_id, user)

    return templates.TemplateResponse(request, "partials/loan_approve_form.html", {"request": request, "loan": loan})


@router.get("/admin/{loan_id}/revoke-form", status_code=status.HTTP_200_OK)
async def get_revoke_form(
    loan_id: int,
    request: Request,
    service: Annotated[LoanService, Depends(get_loan_service)],
    user: Annotated[User, Depends(require_admin)],
):
    loan = await service.get_by_id(loan_id, user)

    return templates.TemplateResponse(request, "partials/loan_revoke_form.html", {"request": request, "loan": loan})

@router.get("/{id}", response_model=LoanPublic)
async def get_loan_search_by_id(
    id: int,
    service: Annotated[LoanService, Depends(get_loan_service)],
    user: Annotated[User, Depends(current_active_user)] 
):
    return await service.get_by_id(id, user)

@router.get("/{id}/detail", response_model=LoanPublic)
async def get_loan_detail(
    request: Request,
    id: int,
    service: Annotated[LoanService, Depends(get_loan_service)],
    user: Annotated[User, Depends(current_active_user)],
    hx_request: Annotated[str | None, Header(alias="HX-Request")] = None,
):
    loan = await service.get_by_id(id, user)

    if hx_request == "true":
        return templates.TemplateResponse(request, "partials/loan_detail.html", {"loan": loan})

    return loan

@router.put("/{loan_id}/return", status_code=status.HTTP_200_OK)
async def return_loan(
    loan_id: int,
    request: Request,
    service: Annotated[LoanService, Depends(get_loan_service)],
    user: Annotated[User, Depends(current_active_user)],
    hx_request: Annotated[str | None, Header(alias="HX-Request")] = None,
):
    loan = await service.get_by_id(loan_id, user)

    loan = await service.return_loan(loan_id, user)

    if hx_request == "true":
        return templates.TemplateResponse(request, "partials/loan_detail.html", {"loan": loan, "request": request})
    
    return loan

@router.put("/{id}", response_model=LoanPublic)
async def update_loan(
    id: int,
    loan_in: LoanUpdate,
    service: Annotated[LoanService, Depends(get_loan_service)],
    user: Annotated[User, Depends(require_admin)]
):
    return await service.update_loan(id, loan_in, user)

@router.post("/request/{book_id}", response_model=LoanPublic)
async def request_loan(
    request: Request,
    book_id: int,
    service: Annotated[LoanService, Depends(get_loan_service)],
    user: Annotated[User, Depends(current_active_user)],
    hx_request: Annotated[str | None, Header(alias="HX-Request")] = None,
):
    loan = await service.request_loan(book_id, user)

    if hx_request == "true":
        return templates.TemplateResponse(request, "partials/loan_message.html", {"loan": loan})

    return loan


@router.get("", status_code=status.HTTP_200_OK)
async def get_loans_list(
    request: Request,
    service: Annotated[LoanService, Depends(get_loan_service)],
    query: Annotated[LoanListQuery, Depends()],
    user: Annotated[User, Depends(current_active_user)],
    hx_request: Annotated[str | None, Header(alias="HX-Request")] = None,
):
    loans, total = await service.list_loans(query, borrower_id=user.id)

    limit = query.limit or 20
    total_pages = max(1, math.ceil(total / limit))

    current_page = max(1, query.page or 1)
    WINDOW = 2
    start_page = max(1, current_page - WINDOW)
    end_page = min(total_pages, current_page + WINDOW)

    desired_count = WINDOW * 2 + 1
    visible_count = end_page - start_page + 1
    if visible_count < desired_count:
        if start_page == 1:
            end_page = min(total_pages, start_page + desired_count - 1)
        elif end_page == total_pages:
            start_page = max(1, end_page - desired_count + 1)

    page_range = list(range(start_page, end_page + 1))

    base_params = (
        f"title={query.title or ''}&author={query.author or ''}"
        f"&isbn={query.isbn or ''}&genre={query.genre or ''}&status={query.status or ''}"
    )

    context = {
        "request": request,
        "loans": loans,
        "total": total,
        "page": current_page,
        "total_pages": total_pages,
        "page_range": page_range,
        "limit": limit,
        "base_params": base_params,
    }

    if hx_request == "true":
        return templates.TemplateResponse(request, "partials/loans_list.html", context)

    return {
        "data": [Loan.model_validate(loan) for loan in loans], 
        "total": total,
        "page": current_page,
        "limit": limit,
    }