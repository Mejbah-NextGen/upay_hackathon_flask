from io import BytesIO
from decimal import Decimal
from unittest.mock import patch

from PIL import Image
import zxingcpp

from app.domain.models import User, Transaction
from app.domain.notifications import NotificationReadReceipt
from app.domain.preferences import DisplayPreference
from app.extensions import db
from app.services.navigation_service import notification_summary
from app.services.qr_service import _serializer
from tests.helpers import AppTestCase


class DisplayAndNotificationTests(AppTestCase):
    def setUp(self):
        super().setUp()
        self.login()

    def test_language_theme_persist_without_translating_user_values(self):
        self.user.full_name = "Dashboard"
        db.session.commit()
        response = self.client.post('/preferences/display', data={'language': 'bn', 'theme': 'dark', 'next': '/profile/'})
        self.assertEqual(response.location, '/profile/')
        preferences = db.session.get(DisplayPreference, self.user_id)
        self.assertEqual((preferences.language, preferences.theme), ('bn', 'dark'))
        html = self.client.get('/profile/').get_data(as_text=True)
        self.assertIn('lang="bn" data-theme="dark"', html)
        self.assertIn('আমার প্রোফাইল', html)
        self.assertIn('value="Dashboard"', html)
        self.assertIn('data-user-content>Dashboard', html)
        self.client = self.app.test_client()
        self.login()
        self.assertIn(b'lang="bn" data-theme="dark"', self.client.get('/').data)

    def test_preferences_validate_redirects_values_and_csrf(self):
        for target in ('https://example.com', '//example.com', '/\\example.com', '/\nLocation:x'):
            response = self.client.post('/preferences/display', data={'next': target})
            self.assertEqual(response.location, '/')
        self.assertEqual(self.client.post('/preferences/display', data={'language':'xx'}).status_code, 400)
        self.app.config['WTF_CSRF_ENABLED'] = True
        self.assertEqual(self.client.post('/preferences/display', data={'theme':'dark'}).status_code, 400)

    def test_bangla_choice_survives_login_logout_and_escaped_user_content(self):
        self.client = self.app.test_client()
        self.client.post('/preferences/display',data={'language':'bn'})
        self.client.post('/auth/login',data={'mobile':self.user.mobile})
        self.client.post('/auth/otp',data={'otp':'123456'})
        self.assertIn(b'lang="bn"',self.client.get('/').data)
        self.user.full_name='<script>private</script>'
        db.session.commit()
        html=self.client.get('/profile/').get_data(as_text=True)
        self.assertNotIn('<script>private</script>',html)
        self.assertIn('&lt;script&gt;private&lt;/script&gt;',html)
        self.client.post('/auth/logout')
        self.assertIn(b'lang="bn"',self.client.get('/auth/login').data)

    def test_opened_notification_shows_receipt_and_decrements_only_it(self):
        first = Transaction(user_id=self.user_id, kind='ADD_MONEY', direction='IN', title='Added', amount=Decimal('20'))
        second = Transaction(user_id=self.user_id, kind='SEND_MONEY', direction='OUT', title='Sent', amount=Decimal('10'))
        other = User(full_name='Other', mobile='01898765432', balance=0)
        db.session.add_all([first, second, other]); db.session.commit()
        foreign = Transaction(user_id=other.id, kind='ADD_MONEY', direction='IN', title='Private', amount=1)
        db.session.add(foreign); db.session.commit()
        self.assertEqual(notification_summary(self.user_id)['unread_count'], 2)
        response = self.client.post(f'/notifications/{second.id}/open', follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Sent', response.data)
        self.assertEqual(notification_summary(self.user_id)['unread_count'], 1)
        self.assertIsNotNone(db.session.get(NotificationReadReceipt, (self.user_id, second.id)))
        self.client.post(f'/notifications/{second.id}/open')
        self.assertEqual(notification_summary(self.user_id)['unread_count'], 1)
        self.assertEqual(self.client.post(f'/notifications/{foreign.id}/open').status_code, 404)
        self.assertEqual(notification_summary(other.id)['unread_count'], 1)
        self.client.post('/notifications/read')
        self.assertEqual(notification_summary(self.user_id)['unread_count'], 0)

    def test_dashboard_one_profile_one_contact_and_priority_order(self):
        html = self.client.get('/').get_data(as_text=True)
        self.assertEqual(html.count('href="/profile/"'), 1)
        self.assertEqual(html.count(self.user.mobile), 1)
        self.assertNotIn('Verified Wallet', html)
        self.assertLess(html.index('class="stats-grid"'), html.index('class="section-card quick-pay-card"'))
        self.assertLess(html.index('class="section-card quick-pay-card"'), html.index('class="section-card period-filter"'))
        self.assertLess(html.index('id="notificationDropdown"'), html.index('id="navbarLanguage"'))
        self.assertLess(html.index('id="navbarLanguage"'), html.index('class="profile-chip"'))


class QrTests(AppTestCase):
    def setUp(self):
        super().setUp(); self.login()

    def code(self, **extra):
        return 'UPAYX:' + _serializer().dumps({'user_id':self.user_id, 'kind':'BILL_PAYMENT', 'reference':'TEST-1001', 'provider':'Titas Gas', 'category':'gas', 'amount':'20.50', **extra})

    def test_signed_qr_roundtrip_image_decoder_and_wallet_is_unchanged(self):
        response = self.client.get('/qr/image?kind=BILL_PAYMENT&category=gas&provider=Titas+Gas&reference=TEST-1001&amount=20.50')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.mimetype, 'image/svg+xml')
        self.assertIn(b'<svg', response.data)
        code = self.code()
        verified = self.client.post('/qr/verify', json={'code':code})
        self.assertEqual(verified.status_code, 200)
        self.assertEqual(verified.json['category'], 'gas')
        picture = Image.fromarray(zxingcpp.write_barcode(zxingcpp.BarcodeFormat.QRCode, code, width=700, height=700))
        upload = BytesIO(); picture.save(upload, 'PNG'); upload.seek(0)
        response = self.client.post('/qr/read-image', data={'image':(upload,'qr.png')})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json['reference'], 'TEST-1001')
        self.assertEqual(self.user.balance, Decimal('1000.00'))
        self.assertEqual(Transaction.query.count(), 0)

    def test_qr_tamper_expiry_wrong_user_and_invalid_amount(self):
        code = self.code()
        self.assertEqual(self.client.post('/qr/verify', json={'code':code+'x'}).status_code, 400)
        other = User(full_name='Other QR', mobile='01898765431', balance=0)
        db.session.add(other); db.session.commit(); self.login(other.id)
        self.assertEqual(self.client.post('/qr/verify', json={'code':code}).status_code, 400)
        self.login()
        with patch('itsdangerous.timed.time.time', return_value=0):
            expired = self.code()
        self.assertEqual(self.client.post('/qr/verify', json={'code':expired}).status_code, 400)
        for amount in ('NaN', 'Infinity', '0', '-1', '100001', '1.234'):
            self.assertEqual(self.client.get('/qr/image', query_string={'kind':'CASH_OUT','amount':amount}).status_code, 400)
        self.assertEqual(self.client.post('/qr/read-image', data={'image':(BytesIO(b'bad'), 'bad.png')}).status_code,400)

    def test_shared_request_can_fill_peer_wallet_but_cannot_change_requester(self):
        code = self.code(kind='REQUEST_MONEY', reference=self.user.mobile, provider='', category='')
        peer = User(full_name='QR Peer', mobile='01898765430', balance=100)
        db.session.add(peer); db.session.commit(); self.login(peer.id)
        response = self.client.post('/qr/verify', json={'code':code})
        self.assertEqual(response.status_code,200)
        self.assertEqual(response.json['kind'],'SEND_MONEY')
        self.assertEqual(response.json['reference'],self.user.mobile)
        invalid = self.code(kind='REQUEST_MONEY', reference=peer.mobile)
        self.assertEqual(self.client.post('/qr/verify', json={'code':invalid}).status_code,400)
        self.assertEqual(peer.balance,Decimal('100.00'))


class ExpandedPhotoTests(AppTestCase):
    def setUp(self):
        super().setUp(); self.login()

    def fields(self, **extra):
        return {'full_name':self.user.full_name,'email':self.user.email,**extra}

    def test_common_formats_and_phone_heic_decode_to_private_jpeg(self):
        for format in ('GIF','BMP','TIFF','ICO','AVIF','HEIF'):
            with self.subTest(format=format):
                upload=BytesIO(); Image.new('RGB',(256,256),'blue').save(upload,format); upload.seek(0)
                response=self.client.post('/profile/',data=self.fields(photo=(upload,'picture.'+format.lower())))
                self.assertEqual(response.status_code,302)
                photo=self.client.get('/profile/photo')
                self.assertEqual(photo.mimetype,'image/jpeg')

    def test_crop_position_resize_and_invalid_settings_are_atomic(self):
        picture=Image.new('RGB',(800,400),'blue'); picture.paste('red',(0,0,400,400))
        upload=BytesIO(); picture.save(upload,'PNG'); upload.seek(0)
        response=self.client.post('/profile/',data=self.fields(photo=(upload,'picture.png'),photo_fit='square',photo_size='256',crop_x='100'))
        self.assertEqual(response.status_code,302)
        before=self.client.get('/profile/photo').data
        with Image.open(BytesIO(before)) as result:
            self.assertEqual(result.size,(256,256)); self.assertGreater(result.getpixel((128,128))[2],200)
        self.assertEqual(self.client.post('/profile/',data=self.fields(full_name='Changed',crop_x='NaN')).status_code,400)
        self.assertNotEqual(self.user.full_name,'Changed')
        self.assertEqual(self.client.get('/profile/photo').data,before)
