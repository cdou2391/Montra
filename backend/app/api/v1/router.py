from fastapi import APIRouter

from app.api.v1 import (
    accounts,
    attachments,
    auth,
    budgets,
    cards,
    currencies,
    families,
    goals,
    health,
    loans,
    planning,
    reports,
    transactions,
)

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(auth.router)
api_router.include_router(accounts.router)
api_router.include_router(transactions.router)
api_router.include_router(cards.router)
api_router.include_router(planning.router)
api_router.include_router(loans.router)
api_router.include_router(families.router)
api_router.include_router(reports.router)
api_router.include_router(attachments.router)
api_router.include_router(currencies.router)
api_router.include_router(budgets.router)
api_router.include_router(goals.router)
