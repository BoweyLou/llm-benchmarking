from __future__ import annotations

import unittest

from backend.model_names import remove_trailing_free_suffix


class ModelNameTests(unittest.TestCase):
    def test_removes_only_a_trailing_free_suffix(self) -> None:
        self.assertEqual(remove_trailing_free_suffix("Example (free)"), "Example")
        self.assertEqual(remove_trailing_free_suffix("Example ( FREE ) "), "Example")
        self.assertEqual(remove_trailing_free_suffix("Example (free) edition"), "Example (free) edition")
        self.assertEqual(remove_trailing_free_suffix("Free Example"), "Free Example")
        self.assertEqual(remove_trailing_free_suffix("Example (freedom)"), "Example (freedom)")
