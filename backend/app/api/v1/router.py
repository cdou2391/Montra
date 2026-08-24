from fastapi import APIRouter

from app.api.v1 import accounts, auth, cards, health, transactions

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(auth.router)
api_router.include_router(accounts.router)
api_router.include_router(transactions.router)
api_router.include_router(cards.router)
