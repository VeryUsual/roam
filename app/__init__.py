from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from config import Config
from flask_login import LoginManager
from flask_moment import Moment
from flask_htmlmin import HTMLMIN
import flask_monitoringdashboard as dashboard
import os
from flask_socketio import SocketIO

app = Flask(__name__)
app.config.from_object(Config)
db = SQLAlchemy(app)
migrate = Migrate(app, db)
login = LoginManager(app)
login.login_view = "login"
moment = Moment(app)
htmlmin = HTMLMIN(
    app, remove_comments=False, remove_empty_space=True, disable_css_min=False
)

dashboard.config.init_from(
    file=os.path.join(os.getcwd(), "flaskmonitoringdashboard_config.cfg")
)

from app import routes, models, errors

dashboard.bind(app)
