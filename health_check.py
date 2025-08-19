# health_check.py
import json
import asyncio
import httpx
from typing import Dict, Any
from datetime import datetime
from config import settings
from services.database import DatabaseService


async def check_telegram_api() -> Dict[str, Any]:
    """Проверка доступности Telegram API"""
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.get(f"https://api.telegram.org/bot{settings.TELEGRAM_TOKEN}/getMe")
            if response.status_code == 200:
                return {"status": "healthy", "service": "telegram"}
            else:
                return {"status": "unhealthy", "service": "telegram", "error": f"HTTP {response.status_code}"}
    except Exception as e:
        return {"status": "unhealthy", "service": "telegram", "error": str(e)}


async def check_openai_api() -> Dict[str, Any]:
    """Проверка доступности OpenAI API"""
    if not settings.OPENAI_API_KEY:
        return {"status": "disabled", "service": "openai", "error": "API key not configured"}

    try:
        from openai import AsyncOpenAI
        client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY, timeout=10)
        models = await client.models.list()
        return {"status": "healthy", "service": "openai"}
    except Exception as e:
        return {"status": "unhealthy", "service": "openai", "error": str(e)}


async def check_database() -> Dict[str, Any]:
    """Проверка подключения к базе данных"""
    try:
        db_service = DatabaseService()
        await db_service.initialize()
        await db_service.close()
        return {"status": "healthy", "service": "database"}
    except Exception as e:
        return {"status": "unhealthy", "service": "database", "error": str(e)}


async def check_redis() -> Dict[str, Any]:
    """Проверка подключения к Redis"""
    try:
        import redis.asyncio as redis
        redis_client = redis.from_url(settings.REDIS_URL)
        await redis_client.ping()
        await redis_client.close()
        return {"status": "healthy", "service": "redis"}
    except Exception as e:
        return {"status": "unhealthy", "service": "redis", "error": str(e)}


async def run_health_checks() -> Dict[str, Any]:
    """Выполнение всех проверок здоровья"""
    checks = await asyncio.gather(
        check_telegram_api(),
        check_openai_api(),
        check_database(),
        check_redis(),
        return_exceptions=True
    )

    results = {}
    overall_healthy = True

    for check in checks:
        if isinstance(check, Exception):
            results["unknown"] = {"status": "error", "error": str(check)}
            overall_healthy = False
        else:
            service_name = check["service"]
            results[service_name] = check
            if check["status"] not in ["healthy", "disabled"]:
                overall_healthy = False

    return {
        "overall_status": "healthy" if overall_healthy else "unhealthy",
        "services": results,
        "timestamp": datetime.utcnow().isoformat()
    }