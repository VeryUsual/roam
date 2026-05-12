from flask import render_template, redirect, url_for, flash, request, send_from_directory, jsonify
from flask_login import current_user, login_user, logout_user, login_required
import sqlalchemy as sa
from app import app, db
from app.forms import LoginForm, RegistrationForm, EditProfileForm, EmptyForm, SubmitVideoForm
from app.models import User, Video
from urllib.parse import urlsplit
from datetime import datetime, timezone
from math import radians
from sqlalchemy import select, func
import os
from werkzeug.utils import secure_filename
import re

VIDEOS_FOLDER = "videos"
ALLOWED_EXTENSIONS = {'mp4', 'mov', 'mkv', 'webm', 'ogv'}

def link_mentions(value):
    def repl(m):
        handle = m.group(1)
        return f'<a href="/user/{handle}">@{handle}</a>'
    return re.sub(r'@([A-Za-z0-9_]+)', repl, value)

app.jinja_env.filters["link_mentions"] = link_mentions

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@app.before_request
def before_request():
    if current_user.is_authenticated:
        current_user.last_seen = datetime.now(timezone.utc)
        db.session.commit()

@app.route("/")
@login_required
def index():
    videos = db.session.scalars(current_user.following_videos()).all()
    return render_template("index.html", videos=videos)

@app.route("/videos/<video_id>")
@login_required
def video(video_id):
    query = sa.select(Video).where(Video.id == video_id).order_by(Video.timestamp.desc())
    videos = db.session.scalars(query).all()
    if len(videos) >= 1:
        return render_template("index.html", videos=videos)
    else:
        return render_template("404.html"), 404

@app.route("/videos/closest/<video_id>")
@login_required
def closest_video(video_id):
    query = sa.select(Video).where(Video.id == video_id)
    video = db.session.scalar(query)
    current_lat = float(video.lat)
    current_lon = float(video.lon)

    distance = (
        6371 * 2 * func.asin(
            func.sqrt(
                func.pow(func.sin(func.radians((Video.lat - current_lat) / 2)), 2)
                + func.cos(func.radians(current_lat))
                * func.cos(func.radians(Video.lat))
                * func.pow(func.sin(func.radians((Video.lon - current_lon) / 2)), 2)
            )
        )
    )
    
    statement = (
        select(Video)
        .where(Video.id != video_id)
        .order_by(distance.asc())
        .limit(1)
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
        6371 * 2 * func.asin(
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

@app.route("/upload", methods=['GET', 'POST'])
@login_required
def upload():
    form = SubmitVideoForm()
    if form.validate_on_submit():
        filename = secure_filename(form.video.data.filename)
        if allowed_file(filename):
            form.video.data.save(os.path.join(app.instance_path, 'videos', filename))

            lat = form.coords.data.split(", ")[0]
            lon = form.coords.data.split(", ")[1]
            video = Video(filepath='video_files/' + filename, author=current_user, lat=lat, lon=lon, description=form.description.data, hashtags=form.hashtags.data)
            db.session.add(video)
            db.session.commit()
            flash('Your video is now public!')
            return redirect(url_for('upload'))
        else:
            flash('File type must be mp4, mov, mkv, webm, or ogv!')
            return redirect(url_for('upload'))
    return render_template("upload.html", form=form)

@app.route('/explore')
@login_required
def explore():
    query = sa.select(Video).order_by(Video.timestamp.desc())
    videos = db.session.scalars(query).all()
    return render_template('index.html', title='Explore', videos=videos)

@app.route("/welcome")
def welcome():
    return render_template("welcome.html")

@app.route("/login", methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    form = LoginForm()
    if form.validate_on_submit():
        user = db.session.scalar(
            sa.select(User).where(User.username == form.username.data))
        if user is None or not user.check_password(form.password.data):
            flash('Invalid username or password')
            return redirect(url_for('login'))
        login_user(user, remember=form.remember_me.data)
        next_page = request.args.get('next')
        if not next_page or urlsplit(next_page).netloc != '':
            next_page = url_for("index")
        return redirect(url_for("index"))
    return render_template("login.html", title="Login", form=form)

@app.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    form = RegistrationForm()
    if form.validate_on_submit():
        user = User(username=form.username.data)
        user.set_password(form.password.data)
        db.session.add(user)
        db.session.commit()
        flash('You are now registered! Please log in with your details.')
        return redirect(url_for('login'))
    return render_template('register.html', title='Register', form=form)

@app.route("/logout")
def logout():
    logout_user()
    return redirect(url_for('index'))

@app.route("/edit_profile", methods=['GET', 'POST'])
@login_required
def edit_profile():
    form = EditProfileForm(current_user.username)
    if form.validate_on_submit():
        current_user.username = form.username.data
        current_user.about_me = form.about_me.data
        db.session.commit()
        flash('Your changes have been saved.')
        return redirect(url_for('edit_profile'))
    elif request.method == 'GET':
        form.username.data = current_user.username
        form.about_me.data = current_user.about_me
    return render_template('edit_profile.html', title='Edit Profile', form=form)

@app.route('/user/<username>')
def user(username):
    user = db.first_or_404(sa.select(User).where(User.username == username))
    videos = db.session.scalars(user.videos.select().order_by(Video.timestamp.desc())).all()
    form = EmptyForm()
    return render_template('user.html', user=user, videos=videos, form=form)

@app.route('/follow/<username>', methods=['POST'])
@login_required
def follow(username):
    form = EmptyForm()
    if form.validate_on_submit():
        user = db.session.scalar(sa.select(User).where(User.username == username))
        if user is None:
            flash(f'User {username} not found.')
            return redirect(url_for('index'))
        if user == current_user:
            flash('You cannot follow yourself!')
            return redirect(url_for('user', username=username))
        current_user.follow(user)
        db.session.commit()
        flash(f'You are following {username}!')
        return redirect(url_for('user', username=username))
    else:
        return redirect(url_for('index'))

@app.route('/unfollow/<username>', methods=['POST'])
@login_required
def unfollow(username):
    form = EmptyForm()
    if form.validate_on_submit():
        user = db.session.scalar(
            sa.select(User).where(User.username == username))
        if user is None:
            flash(f'User {username} not found.')
            return redirect(url_for('index'))
        if user == current_user:
            flash('You cannot unfollow yourself!')
            return redirect(url_for('user', username=username))
        current_user.unfollow(user)
        db.session.commit()
        flash(f'You are not following {username}.')
        return redirect(url_for('user', username=username))
    else:
        return redirect(url_for('index'))

@app.route('/video_files/<name>')
def videos_files(name):
    print(name)
    return send_from_directory(os.path.join(app.instance_path, 'videos'), name)

@app.route('/search')
def search():
    q = request.args.get("q")
    results = Video.query.filter(Video.description.ilike('%' + q + '%')).all()

    return render_template("search.html", results=results)