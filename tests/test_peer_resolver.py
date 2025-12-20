import unittest

from bot.peer_resolver import normalize_telegram_target


class NormalizeTelegramTargetTest(unittest.TestCase):
    def test_username_and_message_links(self) -> None:
        cases = {
            "https://t.me/NotYourskillernxt": ("NotYourskillernxt", "username", None, True),
            "t.me/ExampleUser/42": ("ExampleUser", "message", 42, True),
            "@anotheruser": ("anotheruser", "username", None, True),
            "plainusername": ("plainusername", "username", None, True),
        }

        for url, (username, kind, message_id, supported) in cases.items():
            with self.subTest(url=url):
                normalized = normalize_telegram_target(url)
                self.assertEqual(normalized.username, username)
                self.assertEqual(normalized.kind, kind)
                self.assertEqual(normalized.message_id, message_id)
                self.assertEqual(normalized.supported, supported)

    def test_invite_links_marked_unsupported(self) -> None:
        cases = [
            "https://t.me/+abcdEFGH1234",
            "https://t.me/joinchat/abcdEFGH1234",
        ]

        for url in cases:
            with self.subTest(url=url):
                normalized = normalize_telegram_target(url)
                self.assertIsNone(normalized.username)
                self.assertFalse(normalized.supported)
                self.assertEqual(normalized.kind, "invite")


if __name__ == "__main__":
    unittest.main()
