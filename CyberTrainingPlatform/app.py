import os
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from sqlalchemy.orm import DeclarativeBase
import stripe

class Base(DeclarativeBase):
    pass

db = SQLAlchemy(model_class=Base)
login_manager = LoginManager()

app = Flask(__name__)
app.secret_key = os.environ.get("SESSION_SECRET")

# Configure PostgreSQL database
app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get("DATABASE_URL", "sqlite:///notudemy.db")
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

# Configure file uploads
app.config['MAX_CONTENT_LENGTH'] = 200 * 1024 * 1024  # 200MB limit
app.config['UPLOAD_FOLDER'] = os.path.join(app.static_folder, 'uploads')

# Ensure upload folder exists
if not os.path.exists(app.config['UPLOAD_FOLDER']):
    os.makedirs(app.config['UPLOAD_FOLDER'])

stripe.api_key = os.environ.get('STRIPE_SECRET_KEY')

db.init_app(app)
login_manager.init_app(app)
login_manager.login_view = 'login'

from routes import *

with app.app_context():
    db.create_all()