import os

basedir = os.path.abspath(os.path.dirname(__file__))


class Config:
    SECRET_KEY = (
        os.environ.get("SECRET_KEY")
        or "066df992b530a9342e165be936e2cac737053a1f5122f6e9ea9f28e3a753fc85f977643a0001f12cd45b38ef41524f8341093afff12e917158ba526fcca42f38"
    )
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        "DATABASE_URL"
    ) or "sqlite:///" + os.path.join(basedir, "roam.db")
