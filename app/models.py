from datetime import datetime, timezone
from typing import Optional
import sqlalchemy as sa
import sqlalchemy.orm as so
from app import db
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import UserMixin
from app import login
from hashlib import md5

@login.user_loader
def load_user(id):
    return db.session.get(User, int(id))

followers = sa.Table(
    'followers',
    db.metadata,
    sa.Column('follower_id', sa.Integer, sa.ForeignKey('user.id'), primary_key=True),
    sa.Column('followed_id', sa.Integer, sa.ForeignKey('user.id'), primary_key=True)
)

class User(UserMixin, db.Model):
    id: so.Mapped[int] = so.mapped_column(primary_key=True)
    username: so.Mapped[str] = so.mapped_column(sa.String(64), index=True, unique=True)
    password: so.Mapped[Optional[str]] = so.mapped_column(sa.String(256))
    videos: so.WriteOnlyMapped["Video"] = so.Relationship(back_populates="author")
    about_me: so.Mapped[Optional[str]] = so.mapped_column(sa.String(140))
    last_seen: so.Mapped[Optional[datetime]] = so.mapped_column(default=lambda: datetime.now(timezone.utc))
    following: so.WriteOnlyMapped['User'] = so.relationship(
        secondary=followers, primaryjoin=(followers.c.follower_id == id),
        secondaryjoin=(followers.c.followed_id == id),
        back_populates='followers')
    followers: so.WriteOnlyMapped['User'] = so.relationship(
        secondary=followers, primaryjoin=(followers.c.followed_id == id),
        secondaryjoin=(followers.c.follower_id == id),
        back_populates='following')

    def __repr__(self):
        return '<User {}>'.format(self.username)
    
    def set_password(self, password):
        self.password = generate_password_hash(password)
    
    def check_password(self, password):
        return check_password_hash(self.password, password)
    
    def avatar(self, size):
        digest = md5(self.username.lower().encode('utf-8')).hexdigest()
        return f'https://www.gravatar.com/avatar/{digest}?d=identicon&s={size}'
    
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
        query = sa.select(sa.func.count()).select_from(self.followers.select().subquery())
        return db.session.scalar(query)
    
    def following_count(self):
        query = sa.select(sa.func.count()).select_from(self.following.select().subquery())
        return db.session.scalar(query)
    
    def following_videos(self):
        Author = so.aliased(User)
        Follower = so.aliased(User)
        return (
            sa.select(Video)
            .join(Video.author.of_type(Author))
            .join(Author.followers.of_type(Follower), isouter=True)
            .where(sa.or_(
                Follower.id == self.id,
                Author.id == self.id,
            ))
            .group_by(Video)
            .order_by(Video.timestamp.desc())
        )

class Video(db.Model):
    id: so.Mapped[int] = so.mapped_column(primary_key=True)
    filepath: so.Mapped[str] = so.mapped_column(sa.String(140))
    timestamp: so.Mapped[datetime] = so.mapped_column(index=True, default=lambda: datetime.now(timezone.utc))
    user_id: so.Mapped[int] = so.mapped_column(sa.ForeignKey(User.id), index=True)
    author: so.Mapped[User] = so.relationship(back_populates="videos")
    lat: so.Mapped[float] = so.mapped_column(sa.Float, nullable=False, server_default="0.0")
    lon: so.Mapped[float] = so.mapped_column(sa.Float, nullable=False, server_default="0.0")

    def __repr__(self):
        return '<Video {}>'.format(self.filepath)