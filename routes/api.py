import logging
from flask import Blueprint, jsonify, current_app

api_bp = Blueprint('api', __name__)
logger = logging.getLogger(__name__)


@api_bp.route('/health')
def health_check():
    """Проверка здоровья сервиса"""
    try:
        # Проверка статуса базы данных
        message_handler = current_app.config.get('message_handler')
        if message_handler and message_handler.db:
            db_status = message_handler.db.check_connection()
        else:
            db_status = False

        return jsonify({
            "status": "healthy" if db_status else "degraded",
            "services": {
                "database": "connected" if db_status else "disconnected",
                "webhook": "active",
                "transcription": "ready"
            }
        }), 200 if db_status else 503

    except Exception as e:
        logger.error(f"Health check failed: {str(e)}")
        return jsonify({
            "status": "unhealthy",
            "error": str(e)
        }), 500


@api_bp.route('/stats')
def get_stats():
    """Получение статистики сервиса"""
    try:
        message_handler = current_app.config.get('message_handler')
        if not message_handler or not message_handler.db:
            return jsonify({"error": "Service not initialized"}), 503

        stats = {
            "total_users": message_handler.db.users.count_documents({}),
            "total_transcriptions": message_handler.db.transcriptions.count_documents({}),
            "active_today": message_handler.db.get_active_users_today()
        }

        return jsonify(stats), 200

    except Exception as e:
        logger.error(f"Failed to get stats: {str(e)}")
        return jsonify({"error": "Failed to retrieve statistics"}), 500