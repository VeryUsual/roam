from flask import (
    render_template,
    redirect,
    url_for,
    flash,
    request,
    send_from_directory,
    jsonify,
    make_response,
    send_file,
)
from flask_login import current_user, login_user, logout_user, login_required
import sqlalchemy as sa
from app import app, db
from app.forms import (
    LoginForm,
    RegistrationForm,
    EditProfileForm,
    EmptyForm,
    SubmitVideoForm,
    EditVideoForm,
    ReportVideoForm,
    IssuePunishmentForm,
)
from app.models import User, Video, Report, SavedVideos
from urllib.parse import urlsplit
from datetime import datetime, timezone
from math import radians
from sqlalchemy import select, func
from avatar_generator import Avatar
import os
from werkzeug.utils import secure_filename
import re
import random
import string
from PIL import Image
from io import BytesIO
from flask_admin.contrib.sqla import ModelView
from flask_admin import Admin
from flask_socketio import join_room, leave_room, send, SocketIO, emit

admin = Admin(app, name="Roam Admin Panel")
socketio = SocketIO(app)

with app.app_context():
    db.create_all()

dms = {}

class RoamAdminModelView(ModelView):
    can_export = True
    action_disallowed_list = ["delete"]

    def is_accessible(self):
        if current_user.is_authenticated:
            return current_user.username == "admin" or current_user.role >= 2
        else:
            return False

    def inaccessible_callback(self, name, **kwargs):
        return redirect(url_for("login", next=request.url))


class RoamAdminUserModelView(RoamAdminModelView):
    can_export = True
    column_export_exclude_list = [
        "password",
    ]

    column_list = ["username", "about_me", "last_seen", "profile_picture"]

    form_excluded_columns = [
        "password",
        "videos",
        "following",
        "followers",
        "liked_videos",
        "viewed_videos",
        "reports",
    ]


class RoamAdminVideoModelView(RoamAdminModelView):
    form_excluded_columns = ["author", "likers", "viewers"]


admin.add_view(RoamAdminUserModelView(User, db.session))
admin.add_view(RoamAdminVideoModelView(Video, db.session))

VIDEOS_FOLDER = "videos"
ALLOWED_EXTENSIONS = {"mp4", "mov", "mkv", "webm", "ogv"}
ALLOWED_PFP_FILE_EXTENSIONS = {"png", "jpg", "jpeg", "bmp", "webp", "svg", "gif"}


def link_mentions(value):
    def repl(m):
        handle = m.group(1)
        return f'<a href="/user/{handle}">@{handle}</a>'

    return re.sub(r"@([A-Za-z0-9_]+)", repl, value)


app.jinja_env.filters["link_mentions"] = link_mentions


def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def allowed_pfp_file(filename):
    return (
        "." in filename
        and filename.rsplit(".", 1)[1].lower() in ALLOWED_PFP_FILE_EXTENSIONS
    )


@app.before_request
def before_request():
    if current_user.is_authenticated:
        if current_user.banned:
            logout_user()
            return redirect(url_for("login"))

        current_user.last_seen = datetime.now(timezone.utc)
        db.session.commit()


@app.route("/")
def index():
    if not current_user.is_authenticated:
        return redirect(url_for("welcome"))

    form = EmptyForm()
    videos = db.session.scalars(current_user.following_videos()).all()
    if len(videos) == 0:
        return redirect(url_for("explore"))
    return render_template("index.html", videos=videos, form=form)


@app.route("/videos/<int:video_id>")
@login_required
def video(video_id):
    query = sa.select(Video).where(Video.id == video_id).where(Video.privacy_level != 2)
    videos = db.session.scalars(query).all()
    if len(videos) >= 1:
        form = EmptyForm()
        if videos[0].draft and current_user != videos[0].author:
            return "Unauthorized", 401
        return render_template("index.html", videos=videos, form=form)
    else:
        return render_template("404.html"), 404


@app.route("/videos/analytics/<int:video_id>")
@login_required
def video_analytics(video_id):
    query = sa.select(Video).where(Video.id == video_id)
    video = db.session.scalar(query)

    videos = db.session.scalars(current_user.videos.select())
    if video:
        if video.user_id == current_user.id:
            return render_template(
                "video_analytics.html",
                title="Video Analytics",
                video=video,
                videos=videos,
            )
        else:
            return "Unauthorized", 401
    return "Not found", 404


@app.route("/myvideos")
@login_required
def myvideos():
    videos = db.session.scalars(current_user.videos.select()).all()

    if len(videos) > 0:
        return render_template("myvideos.html", title="My Videos", videos=videos)
    else:
        return "No videos."


@app.route("/videos/edit/<int:video_id>", methods=["GET", "POST"])
@login_required
def video_edit(video_id):
    query = sa.select(Video).where(Video.id == video_id)
    video = db.session.scalar(query)

    if video:
        if video.user_id == current_user.id:
            form = EditVideoForm()
            if form.validate_on_submit():
                if form.delete_checkbox.data:
                    db.session.delete(video)
                    db.session.commit()
                    flash("Successfully deleted your video.")
                    return redirect(url_for("index"))
                video.lat = form.coords.data.split(", ")[0]
                video.lon = form.coords.data.split(", ")[1]
                video.description = form.description.data
                video.hashtags = form.hashtags.data
                video.privacy_level = form.privacy_level.data
                video.draft = form.draft.data
                db.session.commit()
                flash("Changes successfully saved")
                return redirect(url_for("video_edit", video_id=video_id))
            elif request.method == "GET":
                form.coords.data = str(video.lat) + ", " + str(video.lon)
                form.description.data = video.description
                form.hashtags.data = video.hashtags
                form.privacy_level.data = video.privacy_level
                form.draft.data = video.draft
            return render_template(
                "video_edit.html", title="Edit Video", video=video, form=form
            )
        else:
            return "Unauthorized", 401
    else:
        return "Not found", 404


@app.route("/videos/closest/<video_id>")
@login_required
def closest_video(video_id):
    query = sa.select(Video).where(Video.id == video_id)
    video = db.session.scalar(query)
    current_lat = float(video.lat)
    current_lon = float(video.lon)

    distance = (
        6371
        * 2
        * func.asin(
            func.sqrt(
                func.pow(func.sin(func.radians((Video.lat - current_lat) / 2)), 2)
                + func.cos(func.radians(current_lat))
                * func.cos(func.radians(Video.lat))
                * func.pow(func.sin(func.radians((Video.lon - current_lon) / 2)), 2)
            )
        )
    )

    statement = (
        select(Video).where(Video.id != video_id).order_by(distance.asc()).limit(1)
    )

    closest_video = db.session.scalar(statement)
    if closest_video:
        return redirect(url_for("video", video_id=closest_video.id))
    else:
        return "None found"


@app.route("/videos/leave/<video_id>")
@login_required
def leave_video(video_id):
    query = sa.select(Video).where(Video.id == video_id)
    video = db.session.scalar(query)
    current_lat = float(video.lat)
    current_lon = float(video.lon)

    distance = (
        6371
        * 2
        * func.asin(
            func.sqrt(
                func.pow(func.sin(func.radians((Video.lat - current_lat) / 2)), 2)
                + func.cos(func.radians(current_lat))
                * func.cos(func.radians(Video.lat))
                * func.pow(func.sin(func.radians((Video.lon - current_lon) / 2)), 2)
            )
        )
    ).label("distance")

    statement = (
        select(Video)
        .where(Video.id != video_id)
        .where(distance >= 600)
        .order_by(func.random())
        .limit(1)
    )

    picked_video = db.session.scalar(statement)
    if picked_video:
        return redirect(url_for("video", video_id=picked_video.id))
    else:
        return "None found"


@app.route("/upload", methods=["GET", "POST"])
@login_required
def upload():
    form = SubmitVideoForm()
    if form.validate_on_submit():
        filename = "".join(
            random.choices(string.ascii_letters + string.digits, k=14)
        ) + secure_filename(form.video.data.filename)
        if allowed_file(filename):
            if len(form.coords.data.split(", ")) != 2:
                flash("Invalid coords")
                return redirect(url_for("upload"))

            if form.hashtags.data != "":
                for word in form.hashtags.data.split():
                    if not word.startswith("#"):
                        flash("Invalid hashtags")
                        return redirect(url_for("upload"))
                    if ">" in word or "<" in word:
                        flash("Invalid hashtags")
                        return redirect(url_for("upload"))

            form.video.data.save(os.path.join(app.instance_path, "videos", filename))

            lat = form.coords.data.split(", ")[0]
            lon = form.coords.data.split(", ")[1]
            video = Video(
                filepath="video_files/" + filename,
                author=current_user,
                lat=lat,
                lon=lon,
                description=form.description.data,
                hashtags=form.hashtags.data,
                privacy_level=form.privacy_level.data,
                ip_address=request.remote_addr,
            )
            db.session.add(video)
            db.session.commit()
            flash("Your video is now public!")
            return redirect(url_for("upload"))
        else:
            flash("File type must be mp4, mov, mkv, webm, or ogv!")
            return redirect(url_for("upload"))
    return render_template("upload.html", title="Upload", form=form)


@app.route("/explore")
@login_required
def explore():
    query = (
        sa.select(Video)
        .order_by(Video.timestamp.desc())
        .where(Video.privacy_level == 0)
        .where(not Video.draft)
    )
    videos = db.session.scalars(query).all()

    if len(videos) == 0:
        return redirect(url_for("upload"))

    form = EmptyForm()
    return render_template("index.html", title="Explore", videos=videos, form=form)


@app.route("/welcome")
def welcome():
    return render_template("welcome.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("index"))
    form = LoginForm()
    if form.validate_on_submit():
        user = db.session.scalar(
            sa.select(User).where(User.username == form.username.data)
        )
        if user is None or not user.check_password(form.password.data):
            flash("Invalid username or password")
            return redirect(url_for("login"))
        if user.banned:
            flash("You have been banned from the platform for violating rules.")
            return redirect(url_for("login"))
        login_user(user, remember=form.remember_me.data)
        next_page = request.args.get("next")
        if not next_page or urlsplit(next_page).netloc != "":
            next_page = url_for("index")
        return redirect(next_page)
    return render_template("login.html", title="Login", form=form)


@app.route("/register", methods=["GET", "POST"])
def register():
    if current_user.is_authenticated:
        return redirect(url_for("index"))
    form = RegistrationForm()
    if form.validate_on_submit():
        user = User(username=form.username.data, ip_address=request.remote_addr)
        try:
            user.set_password(form.password.data)
        except Exception:
            flash("Your password is too weak. Please try a stronger one.")
            return redirect(url_for("register"))
        db.session.add(user)
        db.session.commit()
        flash("You are now registered! Please log in with your details.")
        return redirect(url_for("login"))
    return render_template("register.html", title="Register", form=form)


@app.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("index"))


@app.route("/edit_profile", methods=["GET", "POST"])
@login_required
def edit_profile():
    form = EditProfileForm(current_user.username)
    if form.validate_on_submit():
        current_user.about_me = form.about_me.data
        if form.profile_picture.data:
            filename = "".join(
                random.choices(string.ascii_letters + string.digits, k=14)
            ) + secure_filename(form.profile_picture.data.filename)
            if allowed_pfp_file(filename):
                form.profile_picture.data.save(
                    os.path.join(app.instance_path, "profilepictures", filename)
                )
                current_user.profile_picture = filename
            else:
                flash("Invalid profile picture file.")
                return redirect(url_for("edit_profile"))
        db.session.commit()
        flash("Your changes have been saved.")
        return redirect(url_for("edit_profile"))
    elif request.method == "GET":
        # form.username.data = current_user.username
        form.about_me.data = current_user.about_me
    return render_template("edit_profile.html", title="Edit Profile", form=form)


@app.route("/user/<username>")
@login_required
def user(username):
    user = db.first_or_404(sa.select(User).where(User.username == username))
    videos = db.session.scalars(
        user.videos.select().order_by(Video.timestamp.desc())
    ).all()
    form = EmptyForm()
    return render_template(
        "user.html", title="@" + user.username, user=user, videos=videos, form=form
    )


@app.route("/follow/<username>", methods=["POST"])
@login_required
def follow(username):
    form = EmptyForm()
    if form.validate_on_submit():
        user = db.session.scalar(sa.select(User).where(User.username == username))
        if user is None:
            flash(f"User {username} not found.")
            return redirect(url_for("index"))
        if user == current_user:
            flash("You cannot follow yourself!")
            return redirect(url_for("user", username=username))
        current_user.follow(user)
        db.session.commit()
        flash(f"You are following {username}!")
        return redirect(url_for("user", username=username))
    else:
        return redirect(url_for("index"))


@app.route("/api/like/<video_id>", methods=["POST"])
@login_required
def like(video_id):
    video = db.session.scalar(sa.select(Video).where(Video.id == video_id))
    if video is None:
        return "Video not found"
    current_user.like(video)
    db.session.commit()
    return "Success"


@app.route("/api/save/<video_id>", methods=["POST"])
@login_required
def save(video_id):
    video = db.session.scalar(sa.select(Video).where(Video.id == video_id))
    if video is None:
        return "Video not found"
    savedvideo = SavedVideos(
        user=current_user, user_id=current_user.id, video_id=video_id, video=video
    )
    db.session.add(savedvideo)
    db.session.commit()
    return "Success"


@app.route("/api/unsave/<video_id>", methods=["POST"])
@login_required
def unsave(video_id):
    video = db.session.scalar(sa.select(Video).where(Video.id == video_id))
    if video is None:
        return "Video not found"
    videosave = db.session.scalar(
        sa.select(SavedVideos).where(
            SavedVideos.user == current_user and SavedVideos.video == video
        )
    )
    db.session.delete(videosave)
    db.session.commit()
    return "Success"


@app.route("/api/is_saved/<video_id>", methods=["POST"])
@login_required
def is_saved(video_id):
    video = db.session.scalar(sa.select(Video).where(Video.id == video_id))
    if video is None:
        return "Video not found", 404
    videosave = db.session.scalar(
        sa.select(SavedVideos).where(
            SavedVideos.user == current_user and SavedVideos.video == video
        )
    )
    if videosave is not None:
        return "Saved", 200
    else:
        return "Not Saved", 200


@app.route("/unfollow/<username>", methods=["POST"])
@login_required
def unfollow(username):
    form = EmptyForm()
    if form.validate_on_submit():
        user = db.session.scalar(sa.select(User).where(User.username == username))
        if user is None:
            flash(f"User {username} not found.")
            return redirect(url_for("index"))
        if user == current_user:
            flash("You cannot unfollow yourself!")
            return redirect(url_for("user", username=username))
        current_user.unfollow(user)
        db.session.commit()
        flash(f"You are not following {username}.")
        return redirect(url_for("user", username=username))
    else:
        return redirect(url_for("index"))


@app.route("/video_files/<name>")
def videos_files(name):
    if current_user:
        video = db.session.scalar(
            sa.select(Video).where(Video.filepath == "video_files/" + name)
        )
        if video is not None:
            current_user.view(video)
            db.session.commit()
    return send_from_directory(os.path.join(app.instance_path, "videos"), name)


@app.route("/pfp/<name>/<int:size>")
def pfp(name, size):
    pfp_path = os.path.join(app.instance_path, "profilepictures", name)
    if not pfp_path or not os.path.exists(pfp_path):
        return "Not found", 404

    with Image.open(pfp_path) as img:
        if img.mode not in ("RGB", "RGBA"):
            img = img.convert("RGB")
        img.thumbnail((int(size), int(size)), Image.LANCZOS)

        buf = BytesIO()
        fmt = img.format if img.format else "JPEG"
        save_kwargs = {}
        if fmt.upper() in ("JPEG", "JPG"):
            save_kwargs["quality"] = 70
            save_kwargs["optimize"] = True
        img.save(buf, format=fmt, **save_kwargs)
        buf.seek(0)

        mimetype = (
            "image/jpeg" if fmt.upper() in ("JPEG", "JPG") else f"image/{fmt.lower()}"
        )
        return send_file(buf, mimetype=mimetype)


@app.route("/search")
@login_required
def search():
    q = request.args.get("q")
    results = Video.query.filter(Video.description.ilike("%" + q + "%")).all()

    return render_template("search.html", results=results)


@app.route("/avatar/<username>/<int:size>")
def avatar(username, size):
    avatar = Avatar.generate(size, username, "PNG")
    headers = {"Content-Type": "image/png"}
    return make_response(avatar, 200, headers)


@app.route("/static/<path:filename>")
def static_files(filename):
    return send_from_directory("static", filename)


@app.route("/modpanel")
def modpanel():
    if current_user.username != "admin" and current_user.role < 1:
        return redirect(url_for("index"))
    return render_template("moderator.html", title="Moderator Panel")


@app.route("/modpanel/reports")
@login_required
def modpanel_reviewreports():
    if current_user.username != "admin" and current_user.role < 1:
        return redirect(url_for("index"))
    reports = db.session.scalars(sa.select(Report)).all()
    return render_template(
        "review_reports.html", title="Review Reports", reports=reports
    )


@app.route("/videos/report/<int:video_id>", methods=["GET", "POST"])
@login_required
def report_video(video_id):
    form = ReportVideoForm()
    if form.validate_on_submit():
        report = Report(
            reason=form.reason.data, video_id=video_id, reporter=current_user
        )
        db.session.add(report)
        db.session.commit()
        flash("Report submitted!")
        return redirect(url_for("report_video", video_id=video_id))
    return render_template("report_video.html", form=form)


@app.route("/api/moderator/report/remove/<int:report_id>")
@login_required
def remove_report(report_id):
    if current_user.username != "admin" and current_user.role < 1:
        return "Unauthorized", 401
    report = db.session.scalar(sa.select(Report).where(Report.id == report_id))
    if report is None:
        return "No report", 400
    db.session.delete(report)
    db.session.commit()
    return "Success"


@app.route("/modpanel/punish", methods=["GET", "POST"])
@login_required
def punish():
    form = IssuePunishmentForm()
    if form.validate_on_submit():
        user = db.session.scalar(sa.select(User).where(User.id == form.user_id.data))
        if not user:
            flash(f"No user with ID {form.user_id.data} found!")
            return redirect(url_for("punish"))
        if user == current_user:
            flash("You can't punish yourself!")
            return redirect(url_for("punish"))
        if user.username == "admin":
            flash("You can't ban the admin!")
            return redirect(url_for("punish"))
        if form.punishment.data == "ban":
            if user.banned:
                flash("User already banned!")
                return redirect(url_for("punish"))
            user.banned = True
            db.session.commit()
            flash("User banned!")
        return redirect(url_for("punish"))

    return render_template("issue_punishment.html", form=form)


@app.route("/videos/saved")
@login_required
def saved_videos_route():
    savedvideos = db.session.scalars(
        sa.select(SavedVideos).where(SavedVideos.user_id == current_user.id)
    ).all()
    return render_template(
        "saved_videos.html", title="Saved Videos", videos=savedvideos
    )

def dm_room_string(user1, user2):
    return "&".join(sorted([str(user1), str(user2)]))

@app.route("/chat", methods=["GET", "POST"])
def chat():
    if request.method == "POST":
        username = request.form.get("username")

        if not username:
            return render_template("chat.html", error="Invalid username")
        
        dms[dm_room_string(username, current_user.username)] = {"messages": []}

        return redirect(url_for("dm", username=username))

    return render_template("chat.html")

@app.route("/dm/<username>")
def dm(username):
    if username is None or dm_room_string(username, current_user.username) not in dms:
        return redirect(url_for("chat"))
    
    messages = dms[dm_room_string(username, current_user.username)]["messages"]

    return render_template("dm.html", username=username, room=dm_room_string(username, current_user.username), messages=messages)

@socketio.on("message")
def message(data):
    data["room"] = data["room"].replace("&amp;", "&")

    if data["room"] not in dms:
        return
    
    content = {
        "name": current_user.username,
        "message": data["data"]
    }

    dms[data["room"]]["messages"].append(content)
    emit("message", content, room=data["room"].replace("&", "&amp;"))

@socketio.on("connect")
def connect():
    room = request.args.get("room")
    if room:
        join_room(room)

@socketio.on("disconnect")
def disconnect():
    room = request.args.get("room")
    if room:
        leave_room(room)