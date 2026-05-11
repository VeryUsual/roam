import os
os.environ['DATABASE_URL'] = 'sqlite://'

from datetime import datetime, timezone, timedelta
import unittest
from app import app, db
from app.models import User, Video

class UserModelCase(unittest.TestCase):
    def setUp(self):
        self.app_context = app.app_context()
        self.app_context.push()
        db.create_all()
    
    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.app_context.pop()
    
    def test_password_hashing(self):
        u = User(username='test')
        u.set_password('secret')
        self.assertFalse(u.check_password('password'))
        self.assertTrue(u.check_password('secret'))
    
    def test_avatar(self):
        u = User(username='test')
        self.assertEqual(u.avatar(128), 'https://www.gravatar.com/avatar/098f6bcd4621d373cade4e832627b4f6?d=identicon&s=128')
    
    def test_follow(self):
        u1 = User(username='user_one')
        u2 = User(username='user_two')
        db.session.add(u1)
        db.session.add(u2)
        db.session.commit()
        following = db.session.scalars(u1.following.select()).all()
        followers = db.session.scalars(u2.followers.select()).all()
        self.assertEqual(following, [])
        self.assertEqual(followers, [])

        u1.follow(u2)
        db.session.commit()
        self.assertTrue(u1.is_following(u2))
        self.assertEqual(u1.following_count(), 1)
        self.assertEqual(u2.followers_count(), 1)
        u1_following = db.session.scalars(u1.following.select()).all()
        u2_followers = db.session.scalars(u2.followers.select()).all()
        self.assertEqual(u1_following[0].username, 'user_two')
        self.assertEqual(u2_followers[0].username, 'user_one')

        u1.unfollow(u2)
        db.session.commit()
        self.assertFalse(u1.is_following(u2))
        self.assertEqual(u1.following_count(), 0)
        self.assertEqual(u2.followers_count(), 0)

    def test_follow_videos(self):
        u1 = User(username='user_one')
        u2 = User(username='user_two')
        u3 = User(username='user_three')
        u4 = User(username='user_four')
        db.session.add_all([u1, u2, u3, u4])

        now = datetime.now(timezone.utc)
        p1 = Video(filepath="videofromuser1.mp4", author=u1,
                  timestamp=now + timedelta(seconds=1))
        p2 = Video(filepath="videofromuser2.mp4", author=u2,
                  timestamp=now + timedelta(seconds=4))
        p3 = Video(filepath="videofromuser3.mp4", author=u3,
                  timestamp=now + timedelta(seconds=3))
        p4 = Video(filepath="videofromuser4.mp4", author=u4,
                  timestamp=now + timedelta(seconds=2))
        db.session.add_all([p1, p2, p3, p4])
        db.session.commit()

        u1.follow(u2)
        u1.follow(u4)
        u2.follow(u3)
        u3.follow(u4)
        db.session.commit()

        f1 = db.session.scalars(u1.following_videos()).all()
        f2 = db.session.scalars(u2.following_videos()).all()
        f3 = db.session.scalars(u3.following_videos()).all()
        f4 = db.session.scalars(u4.following_videos()).all()
        self.assertEqual(f1, [p2, p4, p1])
        self.assertEqual(f2, [p2, p3])
        self.assertEqual(f3, [p3, p4])
        self.assertEqual(f4, [p4])

if __name__ == '__main__':
    unittest.main(verbosity=2)