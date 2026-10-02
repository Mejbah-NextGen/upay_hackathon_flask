from io import BytesIO

from PIL import Image

from app.domain.models import User
from app.domain.profiles import UserProfile
from app.extensions import db
from tests.helpers import AppTestCase


class ProfileDetailsTests(AppTestCase):
    def setUp(self):
        super().setUp()
        self.login()

    def fields(self, **extra):
        return {"full_name": "Updated Person", "email": "updated@example.com",
                "nickname": "Mej", "address": "Dhaka, Bangladesh", **extra}

    def test_details_and_photo_persist_and_can_be_removed(self):
        picture = BytesIO()
        Image.new("RGB", (800, 600), "blue").save(picture, "PNG")
        picture.seek(0)
        response = self.client.post("/profile/", data=self.fields(photo=(picture, "picture.png")))
        self.assertEqual(response.status_code, 302)
        details = db.session.get(UserProfile, self.user_id)
        self.assertEqual(details.nickname, "Mej")
        self.assertEqual(details.address, "Dhaka, Bangladesh")
        response = self.client.get("/profile/photo")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.mimetype, "image/jpeg")
        with Image.open(BytesIO(response.data)) as photo:
            self.assertEqual(photo.size, (512, 384))
        self.assertIn("no-store", response.headers["Cache-Control"])
        self.assertIn(b"Your profile picture", self.client.get("/profile/").data)
        self.assertEqual(self.client.post("/profile/", data=self.fields(remove_photo="on")).status_code, 302)
        self.assertEqual(self.client.get("/profile/photo").status_code, 404)

    def test_invalid_upload_or_details_do_not_partially_save(self):
        old_name = self.user.full_name
        invalid = [self.fields(photo=(BytesIO(b"<script>bad</script>"), "bad.png")),
                   self.fields(nickname="N" * 41), self.fields(address="A" * 301)]
        for fields in invalid:
            with self.subTest(fields=list(fields)):
                self.assertEqual(self.client.post("/profile/", data=fields).status_code, 400)
                self.assertEqual(self.user.full_name, old_name)
                self.assertIsNone(db.session.get(UserProfile, self.user_id))

    def test_photo_is_private_to_current_account(self):
        db.session.add(UserProfile(user_id=self.user_id, photo_data=b"private-image", photo_mime="image/jpeg"))
        other = User(full_name="Other Person", mobile="01812345678")
        db.session.add(other)
        db.session.commit()
        self.login(other.id)
        self.assertEqual(self.client.get("/profile/photo").status_code, 404)
        with self.client.session_transaction() as session:
            session.clear()
        self.assertEqual(self.client.get("/profile/photo").status_code, 302)

    def test_oversized_upload_has_friendly_error_and_preserves_profile(self):
        original_name = self.user.full_name
        self.app.config["MAX_CONTENT_LENGTH"] = 1024
        response = self.client.post("/profile/", data=self.fields(
            photo=(BytesIO(b"x" * 2048), "large.jpg")
        ))
        self.assertEqual(response.status_code, 413)
        self.assertIn(b"Picture too large", response.data)
        self.assertEqual(self.user.full_name, original_name)
        self.assertIsNone(db.session.get(UserProfile, self.user_id))
