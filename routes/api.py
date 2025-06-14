import logging
from flask import Blueprint, jsonify, current_app

api_bp = Blueprint('api', __name__)
logger = logging.getLogger(__name__)


@api_bp.route('/health')
def health_check():
    """Проверка здоровья сервиса"""
    try:
        # Проверка состояния сервисов
        db_status = "connected" if hasattr(current_app, 'db') and current_app.db else "error"
        transcriber_status = "initialized" if hasattr(current_app,
                                                      'transcriber') and current_app.transcriber else "error"
        payment_status = "initialized" if hasattr(current_app, 'payment') and current_app.payment else "error"

        overall_status = "healthy" if all([
            db_status == "connected",
            transcriber_status == "initialized",
            payment_status == "initialized"
        ]) else "degraded"

        return jsonify({
            "status": overall_status,
            "services": {
                "database": db_status,
                "transcriber": transcriber_status,
                "payment": payment_status
            },
            "version": "1.0.0"
        })

    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return jsonify({
            "status": "error",
            "error": str(e)
        }), 500


@api_bp.route('/stats')
def get_stats():
    """Получение статистики бота"""
    try:
        # Здесь можно добавить получение статистики из БД
        return jsonify({
            "total_users": 0,
            "total_transcriptions": 0,
            "daily_active_users": 0
        })

    except Exception as e:
        logger.error(f"Failed to get stats: {e}")
        return jsonify({"error": str(e)}), 500