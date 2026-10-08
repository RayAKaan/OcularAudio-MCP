import unittest

from universal_sources import (
    is_direct_media_extension,
    is_media_url_scheme,
    platform_from_extractor,
    platform_from_host,
    source_family,
    universal_capabilities,
)


class UniversalSourceTests(unittest.TestCase):
    def test_known_social_platforms(self):
        self.assertEqual(platform_from_host("www.snapchat.com"), "snapchat")
        self.assertEqual(platform_from_host("linkedin.com"), "linkedin")
        self.assertEqual(platform_from_host("www.pinterest.com"), "pinterest")
        self.assertEqual(platform_from_host("www.vk.com"), "vk")

    def test_known_media_platforms(self):
        self.assertEqual(platform_from_host("kick.com"), "kick")
        self.assertEqual(platform_from_host("www.soundcloud.com"), "soundcloud")
        self.assertEqual(platform_from_host("archive.org"), "archive")

    def test_extractor_fallback(self):
        self.assertEqual(platform_from_extractor("Twitter"), "x")
        self.assertEqual(platform_from_extractor("youtube:tab"), "youtube")
        self.assertEqual(platform_from_extractor("ExampleSite"), "examplesite")
        self.assertEqual(platform_from_extractor(""), "generic_web")

    def test_families(self):
        self.assertEqual(source_family("tiktok"), "video_social")
        self.assertEqual(source_family("vimeo"), "video_platform")
        self.assertEqual(source_family("soundcloud"), "audio_platform")
        self.assertEqual(source_family("local"), "local")
        self.assertEqual(source_family("unknown-site"), "generic")

    def test_generic_and_local_capabilities(self):
        capabilities = universal_capabilities()
        self.assertTrue(capabilities["universal_sources"])
        self.assertTrue(capabilities["generic_web_fallback"])
        self.assertTrue(capabilities["extractor_driven_discovery"])
        self.assertTrue(capabilities["local_files"])
        self.assertIn("youtube", capabilities["platforms"])
        self.assertIn("snapchat", capabilities["platforms"])
        self.assertIn("soundcloud", capabilities["platforms"])

    def test_media_schemes_and_extensions(self):
        self.assertTrue(is_media_url_scheme("RTMP"))
        self.assertTrue(is_media_url_scheme("rtsp"))
        self.assertTrue(is_direct_media_extension(".MP4"))
        self.assertTrue(is_direct_media_extension(".m3u8"))


if __name__ == "__main__":
    unittest.main()
