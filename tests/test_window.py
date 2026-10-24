import os
import unittest

from vnremaster.window import (
    WindowError,
    WindowInfo,
    capture_client,
    list_windows,
)


INFO = WindowInfo(
    hwnd=0x1234,
    pid=42,
    class_name="DemoWindow",
    title="Demo Game",
    width=1200,
    height=900,
    visible=True,
)


class WindowInfoTests(unittest.TestCase):
    def test_default_match(self):
        self.assertTrue(INFO.matches())

    def test_pid_and_class(self):
        self.assertTrue(INFO.matches(pid=42, class_name="DemoWindow"))
        self.assertFalse(INFO.matches(pid=43))
        self.assertFalse(INFO.matches(class_name="Other"))

    def test_title_is_substring_and_case_sensitive(self):
        self.assertTrue(INFO.matches(title_contains="Game"))
        self.assertFalse(INFO.matches(title_contains="game"))

    def test_min_size(self):
        self.assertTrue(INFO.matches(min_size=(1200, 900)))
        self.assertFalse(INFO.matches(min_size=(1201, 900)))

    def test_hidden_window(self):
        hidden = WindowInfo(1, 2, "X", "Y", 800, 600, False)
        self.assertFalse(hidden.matches())
        self.assertTrue(hidden.matches(visible_only=False))

    def test_area(self):
        self.assertEqual(INFO.area, 1200 * 900)


class WindowOsTests(unittest.TestCase):
    def test_invalid_hwnd_raises(self):
        with self.assertRaises(WindowError):
            capture_client(0)

    @unittest.skipIf(os.name == "nt", "enumeration is expected to work on Windows")
    def test_enumeration_requires_windows(self):
        with self.assertRaises(WindowError):
            list_windows()


if __name__ == "__main__":
    unittest.main()
