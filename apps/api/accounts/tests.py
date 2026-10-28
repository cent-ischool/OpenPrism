from django.test import TestCase
from rest_framework.test import APIClient

from projects.models import Membership


class AuthTests(TestCase):
    def setUp(self):
        self.client = APIClient()

    def register(self, email='a@example.com', password='correct-horse-battery'):
        return self.client.post('/api/auth/register', {'email': email, 'password': password, 'name': 'Ann'}, format='json')

    def test_register_creates_user_and_personal_workspace(self):
        res = self.register()
        self.assertEqual(res.status_code, 201)
        self.assertTrue(res.data['ok'])
        self.assertIn('access', res.data)
        self.assertEqual(Membership.objects.filter(user__email='a@example.com', role='owner').count(), 1)

    def test_duplicate_email_uses_ok_error_shape(self):
        self.register()
        res = self.register(email='A@example.com')
        self.assertEqual(res.status_code, 400)
        self.assertFalse(res.data['ok'])
        self.assertIn('already exists', res.data['error'])

    def test_weak_password_rejected(self):
        self.assertEqual(self.register(password='123').status_code, 400)

    def test_login_then_me(self):
        self.register()
        login = self.client.post('/api/auth/login', {'email': 'a@example.com', 'password': 'correct-horse-battery'}, format='json')
        self.assertEqual(login.status_code, 200)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {login.data['access']}")
        me = self.client.get('/api/auth/me')
        self.assertEqual(me.data['user']['email'], 'a@example.com')

    def test_me_requires_auth_with_ok_error_shape(self):
        res = self.client.get('/api/auth/me')
        self.assertEqual(res.status_code, 401)
        self.assertFalse(res.data['ok'])
