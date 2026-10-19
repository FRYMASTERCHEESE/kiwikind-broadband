from django.test import SimpleTestCase, override_settings

@override_settings(INTAKE_ENABLED=False, REGISTRATION_ENABLED=False, ADMIN_ENABLED=False)
class PublicPolicyTests(SimpleTestCase):
    def page(self,path):
        response=self.client.get(path)
        self.assertEqual(response.status_code,200)
        return b''.join(response.streaming_content).decode()
    def test_privacy_is_public_and_names_actual_project_and_contact(self):
        html=self.page('/privacy/')
        self.assertIn('prelaunch project',html)
        self.assertIn('kiwikindbroadband@gmail.com',html)
        self.assertIn('/account-deletion/',html)
        self.assertIn('no automatic account-expiry',html)
    def test_deletion_path_works_without_signin_or_password(self):
        html=self.page('/account-deletion/')
        self.assertIn('mailto:kiwikindbroadband@gmail.com?subject=',html)
        self.assertIn('do not need a KiwiKind password',html)
        self.assertIn('nz.kiwikind.broadband',html)
        self.assertIn('processed manually',self.page('/privacy/'))
