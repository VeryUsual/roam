from datetime import datetime, timezone
from typing import Optional
import sqlalchemy as sa
import sqlalchemy.orm as so
from app import db
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import UserMixin
from app import login
from hashlib import md5
from collections import Counter
from password_strength import PasswordPolicy

policy = PasswordPolicy.from_names(strength=0.01)


@login.user_loader
def load_user(id):
    return db.session.get(User, int(id))


followers = sa.Table(
    "followers",
    db.metadata,
    sa.Column("follower_id", sa.Integer, sa.ForeignKey("user.id"), primary_key=True),
    sa.Column("followed_id", sa.Integer, sa.ForeignKey("user.id"), primary_key=True),
)

likes = sa.Table(
    "likes",
    db.metadata,
    sa.Column("liker_id", sa.Integer, sa.ForeignKey("user.id"), primary_key=True),
    sa.Column("video_id", sa.Integer, sa.ForeignKey("video.id"), primary_key=True),
)

views = sa.Table(
    "views",
    db.metadata,
    sa.Column("viewer_id", sa.Integer, sa.ForeignKey("user.id"), primary_key=True),
    sa.Column("video_id", sa.Integer, sa.ForeignKey("video.id"), primary_key=True),
    sa.Column("datetime", sa.DateTime, default=lambda: datetime.now(timezone.utc)),
)


class User(UserMixin, db.Model):
    id: so.Mapped[int] = so.mapped_column(primary_key=True)
    username: so.Mapped[str] = so.mapped_column(sa.String(64), index=True, unique=True)
    password: so.Mapped[Optional[str]] = so.mapped_column(sa.String(256))
    videos: so.WriteOnlyMapped["Video"] = so.Relationship(back_populates="author")
    about_me: so.Mapped[Optional[str]] = so.mapped_column(sa.String(140))
    last_seen: so.Mapped[Optional[datetime]] = so.mapped_column(
        default=lambda: datetime.now(timezone.utc)
    )
    profile_picture: so.Mapped[str] = so.mapped_column(sa.String(200), nullable=True)

    following: so.WriteOnlyMapped["User"] = so.relationship(
        secondary=followers,
        primaryjoin=(followers.c.follower_id == id),
        secondaryjoin=(followers.c.followed_id == id),
        back_populates="followers",
    )
    followers: so.WriteOnlyMapped["User"] = so.relationship(
        secondary=followers,
        primaryjoin=(followers.c.followed_id == id),
        secondaryjoin=(followers.c.follower_id == id),
        back_populates="following",
    )
    liked_videos: so.Mapped[list["Video"]] = so.relationship(
        "Video", secondary=likes, back_populates="likers", lazy="select"
    )
    viewed_videos: so.Mapped[list["Video"]] = so.relationship(
        "Video", secondary=views, back_populates="viewers", lazy="select"
    )
    ip_address: so.Mapped[str] = so.mapped_column(
        sa.String(48), server_default="", default=""
    )
    reports: so.Mapped[list["Report"]] = so.relationship(back_populates="reporter")
    banned: so.Mapped[bool] = so.mapped_column(default=False, server_default="False")
    role: so.Mapped[int] = so.mapped_column(
        server_default="0", default="0"
    )  # 0 is normal, 1 is moderator, 2 is admin
    saved_videos: so.Mapped[list["SavedVideos"]] = so.relationship(
        back_populates="user"
    )

    def __repr__(self):
        return "<User {}>".format(self.username)

    def set_password(self, password):
        ptest = policy.test(password)
        if ptest != []:
            raise Exception(str(ptest))
        self.password = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password, password)

    def avatar(self, size):
        if self.profile_picture is not None:
            return f"/pfp/{self.profile_picture}/{str(size)}"
        username = self.username.lower()
        return f"/avatar/{username}/{size}"

    def follow(self, user):
        if not self.is_following(user):
            self.following.add(user)

    def unfollow(self, user):
        if self.is_following(user):
            self.following.remove(user)

    def is_following(self, user):
        query = self.following.select().where(User.id == user.id)
        return db.session.scalar(query) is not None

    def followers_count(self):
        query = sa.select(sa.func.count()).select_from(
            self.followers.select().subquery()
        )
        return db.session.scalar(query)

    def following_count(self):
        query = sa.select(sa.func.count()).select_from(
            self.following.select().subquery()
        )
        return db.session.scalar(query)

    def following_videos(self):
        Author = so.aliased(User)
        Follower = so.aliased(User)
        return (
            sa.select(Video)
            .join(Video.author.of_type(Author))
            .join(Author.followers.of_type(Follower), isouter=True)
            .where(
                sa.or_(
                    Follower.id == self.id,
                    Author.id == self.id,
                )
            )
            .where(Video.privacy_level == 0)
            .where(not Video.draft)
            .group_by(Video)
            .order_by(Video.timestamp.desc())
        )

    def like(self, video: "Video"):
        if not self.has_liked(video):
            self.liked_videos.append(video)

    def unlike(self, video: "Video"):
        if self.has_liked(video):
            self.liked_videos.remove(video)

    def has_liked(self, video: "Video") -> bool:
        return video in self.liked_videos

    def likes_count(self) -> int:
        return len(self.liked_videos)

    def view(self, video: "Video"):
        if not self.has_viewed(video):
            self.viewed_videos.append(video)

    def has_viewed(self, video: "Video") -> bool:
        return video in self.viewed_videos

    def view_count(self) -> int:
        return len(self.viewed_videos)

    def save(self, video: "Video"):
        if not self.has_saved(video):
            self.saved_videos.append(video)

    def unsave(self, video: "Video"):
        if self.has_saved(video):
            self.saved_videos.remove(video)

    def has_saved(self, video: "Video") -> bool:
        return video in self.saved_videos


class Video(db.Model):
    id: so.Mapped[int] = so.mapped_column(primary_key=True)
    filepath: so.Mapped[str] = so.mapped_column(sa.String(140))
    timestamp: so.Mapped[datetime] = so.mapped_column(
        index=True, default=lambda: datetime.now(timezone.utc)
    )
    user_id: so.Mapped[int] = so.mapped_column(sa.ForeignKey(User.id), index=True)
    author: so.Mapped[User] = so.relationship(back_populates="videos")
    lat: so.Mapped[float] = so.mapped_column(
        sa.Float, nullable=False, server_default="0.0"
    )
    lon: so.Mapped[float] = so.mapped_column(
        sa.Float, nullable=False, server_default="0.0"
    )
    description: so.Mapped[str] = so.mapped_column(sa.String(1000), server_default="")
    hashtags: so.Mapped[str] = so.mapped_column(sa.String(500), server_default="")
    likers: so.Mapped[list["User"]] = so.relationship(
        "User", secondary=likes, back_populates="liked_videos", lazy="select"
    )
    viewers: so.Mapped[list["User"]] = so.relationship(
        "User", secondary=views, back_populates="viewed_videos", lazy="select"
    )
    privacy_level: so.Mapped[int] = so.mapped_column(
        server_default="0", default="0"
    )  # 0 is public, 1 is unlisted, and 2 is private
    ip_address: so.Mapped[str] = so.mapped_column(
        sa.String(48), server_default="", default=""
    )
    reports: so.Mapped[list["Report"]] = so.relationship(back_populates="video")
    savers: so.Mapped[list["SavedVideos"]] = so.relationship(back_populates="video")
    draft: so.Mapped[bool] = so.mapped_column(
        sa.Boolean, nullable=False, server_default="False", default=False
    )

    def __repr__(self):
        return "<Video {}>".format(self.filepath)

    def like_count(self) -> int:
        return len(self.likers)

    def is_liked_by(self, user: "User") -> bool:
        return user in self.likers

    def view_count(self) -> int:
        return len(self.viewers)

    def is_viewed_by(self, user: "User") -> bool:
        return user in self.viewers

    def when_viewed(self) -> list[datetime]:
        query = (
            sa.select(views.c.datetime)
            .where(views.c.video_id == self.id)
            .order_by(views.c.datetime.desc())
        )
        rows = db.session.execute(query).scalars().all()
        return list(rows)

    def monthly_view_counts(self):
        times = self.when_viewed()
        months = [t.astimezone(timezone.utc).strftime("%Y-%m") for t in times]
        counts = Counter(months)
        labels = sorted(counts.keys())
        data = [counts[m] for m in labels]
        return labels, data


class Report(db.Model):
    id: so.Mapped[int] = so.mapped_column(primary_key=True)
    reason: so.Mapped[str] = so.mapped_column(sa.String(1000), default="")
    video_id: so.Mapped[int] = so.mapped_column(sa.ForeignKey("video.id"))
    user_id: so.Mapped[int] = so.mapped_column(sa.ForeignKey(User.id), index=True)
    reporter: so.Mapped[User] = so.relationship(back_populates="reports")
    video: so.Mapped[Video] = so.relationship(back_populates="reports")


class SavedVideos(db.Model):
    id: so.Mapped[int] = so.mapped_column(primary_key=True)
    user_id: so.Mapped[int] = so.mapped_column(sa.ForeignKey(User.id), index=True)
    video_id: so.Mapped[int] = so.mapped_column(sa.ForeignKey("video.id"))
    folder: so.Mapped[str] = so.mapped_column(sa.String(300), default="")
    user: so.Mapped[list["User"]] = so.relationship(back_populates="saved_videos")
    video: so.Mapped[list["Video"]] = so.relationship(back_populates="savers")
