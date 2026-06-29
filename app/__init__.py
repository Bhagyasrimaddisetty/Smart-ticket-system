from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_jwt_extended import JWTManager
from flask_mail import Mail
from flask_cors import CORS
from pymongo import MongoClient
from celery import Celery
import os

db = SQLAlchemy()
jwt = JWTManager()
mail = Mail()
celery = Celery()

mongo_client = None
mongo_db = None


def create_app(config_name="development"):
    app = Flask(__name__)
    app.config.from_object(f"app.config.{config_name.capitalize()}Config")

    # Extensions
    db.init_app(app)
    jwt.init_app(app)
    mail.init_app(app)
    CORS(app)

    # MongoDB
    global mongo_client, mongo_db
    try:
        mongo_client = MongoClient(app.config.get("MONGO_URI", "mongodb://localhost:27017/"), serverSelectionTimeoutMS=2000)
        mongo_db = mongo_client[app.config.get("MONGO_DB", "ticket_analytics")]
    except Exception:
        pass  # MongoDB optional for analytics

    # Celery
    celery.conf.update(
        broker_url=app.config.get("CELERY_BROKER_URL", "redis://localhost:6379/0"),
        result_backend=app.config.get("CELERY_RESULT_BACKEND", "redis://localhost:6379/0"),
    )

    # Blueprints
    from app.routes.auth import auth_bp
    from app.routes.tickets import tickets_bp
    from app.routes.comments import comments_bp
    from app.routes.dashboard import dashboard_bp

    app.register_blueprint(auth_bp, url_prefix="/api")
    app.register_blueprint(tickets_bp, url_prefix="/api")
    app.register_blueprint(comments_bp, url_prefix="/api")
    app.register_blueprint(dashboard_bp, url_prefix="/api")

    with app.app_context():
        db.create_all()

    return app
