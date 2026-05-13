from flask_wtf import FlaskForm
from flask_wtf.file import FileField, FileRequired, FileAllowed
from wtforms import StringField, PasswordField, BooleanField, SubmitField, TextAreaField
from wtforms.validators import DataRequired, ValidationError, EqualTo, Length
import sqlalchemy as sa
from app import db
from app.models import User


class LoginForm(FlaskForm):
    username = StringField("Username", validators=[DataRequired()])
    password = PasswordField("Password", validators=[DataRequired()])
    remember_me = BooleanField("Remember Me")
    submit = SubmitField("Login")


class RegistrationForm(FlaskForm):
    username = StringField("Username", validators=[DataRequired()])
    password = PasswordField("Password", validators=[DataRequired()])
    password2 = PasswordField(
        "Repeat Password", validators=[DataRequired(), EqualTo("password")]
    )
    submit = SubmitField("Register")

    def validate_username(self, username):
        user = db.session.scalar(sa.select(User).where(User.username == username.data))
        if user is not None:
            raise ValidationError("Please use a different username.")


class EditProfileForm(FlaskForm):
    # username = StringField('Username', validators=[DataRequired()])
    about_me = TextAreaField("About me (Markdown formatted)", validators=[Length(min=0, max=140)])
    profile_picture = FileField(
        "Profile picture",
        validators=[
            FileAllowed(
                ["png", "jpg", "jpeg", "bmp", "webp", "svg", "gif"],
                "File type must be png, jpg, jpeg, bmp, webp, svg, or gif.",
            ),
        ],
        render_kw={"accept": ".png,.jpg,.jpeg,.bmp,.webp,.svg,.gif"},
    )
    submit = SubmitField("Submit")

    def __init__(self, original_username, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.original_username = original_username

    def validate_username(self, username):
        if username.data != self.original_username:
            user = db.session.scalar(
                sa.select(User).where(User.username == username.data)
            )
            if user is not None:
                raise ValidationError("Please use a different username.")


class EmptyForm(FlaskForm):
    submit = SubmitField("Submit")


class SubmitVideoForm(FlaskForm):
    video = FileField(
        "Video file",
        validators=[
            FileRequired(),
            FileAllowed(
                ["mp4", "mov", "mkv", "webm", "ogv"],
                "File type must be mp4, mov, mkv, webm, or ogv!",
            ),
        ],
        render_kw={"accept": ".mp4,.mov,.mkv,.webm,.ogv"},
    )
    coords = TextAreaField("Enter GPS coords", validators=[DataRequired()])
    description = TextAreaField("Description")
    hashtags = TextAreaField("Hashtags")
    submit = SubmitField("Submit")
