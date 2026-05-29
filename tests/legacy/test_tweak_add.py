#!/usr/bin/env python3
"""Tests for pure Python secp256k1 tweak-add implementation"""

import hashlib
import os
import sys
import unittest
from typing import cast

# Add src to path so we can import nectargraphenebase
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from nectargraphenebase.account import PublicKey


class TestTweakAdd(unittest.TestCase):
    """Test cases for pure Python secp256k1 tweak-add implementation"""

    def setUp(self):
        """Set up test fixtures"""
        # Use a known public key directly to avoid ecdsa dependency
        self.test_pub_key = "STM6oVMzJJJgSu3hV1DZBcLdMUJYj3Cs6kGXf6WVLP3HhgLgNkA5J"
        self.test_pub = PublicKey(self.test_pub_key)

        # Test tweak values
        self.valid_tweak = hashlib.sha256(b"test_tweak").digest()
        self.zero_tweak = b"\x00" * 32
        # Use a number that is definitely larger than the curve order
        # SECP256K1_N is approximately 0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFEBAAEDCE6AF48A03BBFD25E8CD0364141
        # We'll create a number that's SECP256K1_N + some large offset
        from nectargraphenebase.account import SECP256K1_N

        large_num = SECP256K1_N + (1 << 100)  # Add a large number to ensure it's bigger
        self.large_tweak = large_num.to_bytes(32, "big")

    def test_basic_tweak_add(self):
        """Test basic tweak-add operation"""
        result = self.test_pub.add(self.valid_tweak)

        # Should return a PublicKey instance
        self.assertIsInstance(result, PublicKey)

        # Should have same prefix as original
        self.assertEqual(result.prefix, self.test_pub.prefix)

        # Should be different from original
        self.assertNotEqual(str(result), str(self.test_pub))

        # Should be deterministic (same input gives same output)
        result2 = self.test_pub.add(self.valid_tweak)
        self.assertEqual(str(result), str(result2))

    def test_child_method_compatibility(self):
        """Test that child() method works with new add() implementation"""
        offset = b"test_offset"
        child_key = self.test_pub.child(offset)

        # Should return a PublicKey instance
        self.assertIsInstance(child_key, PublicKey)

        # Should have same prefix as original
        self.assertEqual(child_key.prefix, self.test_pub.prefix)

        # Should be different from original
        self.assertNotEqual(str(child_key), str(self.test_pub))

    def test_tweak_validation(self):
        """Test tweak validation"""
        # Valid tweak should work
        result = self.test_pub.add(self.valid_tweak)
        self.assertIsInstance(result, PublicKey)

        # Zero tweak should raise ValueError
        with self.assertRaises(ValueError) as cm:
            self.test_pub.add(self.zero_tweak)
        self.assertIn("cannot be zero", str(cm.exception))

        # Tweak too large should raise ValueError
        with self.assertRaises(ValueError) as cm:
            self.test_pub.add(self.large_tweak)
        self.assertIn("must be less than curve order", str(cm.exception))

    def test_invalid_tweak_types(self):
        """Test invalid tweak input types"""
        # Wrong type
        with self.assertRaises(ValueError) as cm:
            self.test_pub.add(cast(bytes, 12345))
        self.assertIn("must be bytes", str(cm.exception))

        # Wrong length
        with self.assertRaises(ValueError) as cm:
            self.test_pub.add(b"short")
        self.assertIn("must be exactly 32 bytes", str(cm.exception))

        with self.assertRaises(ValueError) as cm:
            self.test_pub.add(b"too_long" * 10)
        self.assertIn("must be exactly 32 bytes", str(cm.exception))

    def test_deterministic_behavior(self):
        """Test that same inputs produce same outputs"""
        tweak1 = hashlib.sha256(b"deterministic_test_1").digest()
        tweak2 = hashlib.sha256(b"deterministic_test_2").digest()

        result1a = self.test_pub.add(tweak1)
        result1b = self.test_pub.add(tweak1)
        result2a = self.test_pub.add(tweak2)

        # Same tweak should give same result
        self.assertEqual(str(result1a), str(result1b))

        # Different tweaks should give different results
        self.assertNotEqual(str(result1a), str(result2a))

    def test_different_keys_different_results(self):
        """Test that different keys with same tweak give different results"""
        # Use a different public key for comparison
        other_pub_key = "STM8YAMLtNcnqGNd3fx28NP3WoyuqNtzxXpwXTkZjbfe9scBmSyGT"
        other_pub = PublicKey(other_pub_key)

        result1 = self.test_pub.add(self.valid_tweak)
        result2 = other_pub.add(self.valid_tweak)

        # Different keys should give different results
        self.assertNotEqual(str(result1), str(result2))

    def test_round_trip_consistency(self):
        """Test that operations are consistent"""
        # Create a child key
        child = self.test_pub.child(b"round_trip_test")

        # Apply another tweak to the child
        grandchild = child.add(hashlib.sha256(b"another_tweak").digest())

        # Both should be valid PublicKey instances
        self.assertIsInstance(child, PublicKey)
        self.assertIsInstance(grandchild, PublicKey)

        # All should have same prefix
        self.assertEqual(child.prefix, self.test_pub.prefix)
        self.assertEqual(grandchild.prefix, self.test_pub.prefix)


if __name__ == "__main__":
    unittest.main()
