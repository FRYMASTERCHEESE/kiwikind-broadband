from django.test import SimpleTestCase


class AdvertisingSellerTests(SimpleTestCase):
    def test_root_seller_files_are_public_plain_text_with_exact_publisher(self):
        for path in ('/app-ads.txt', '/ads.txt'):
            with self.subTest(path=path):
                response = self.client.get(path, secure=True)
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response['Content-Type'], 'text/plain; charset=utf-8')
                body = b''.join(response.streaming_content).decode()
                records = [line for line in body.splitlines() if line and not line.startswith('#')]
                self.assertEqual(records, ['google.com, pub-4051392846058327, DIRECT, f08c47fec0942fa0'])
                self.assertNotIn('<script', body)

    def test_seller_files_reject_writes(self):
        for path in ('/app-ads.txt', '/ads.txt'):
            self.assertEqual(self.client.post(path, secure=True).status_code, 405)
