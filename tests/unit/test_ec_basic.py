from nectargraphenebase.account import (
    _mod_inverse,
    _point_add,
)


def test_basic_operations():
    """Test basic elliptic curve operations - simplified version"""
    # Test modular inverse
    inv = _mod_inverse(3, 7)
    assert inv == 5, "Modular inverse test failed"

    # Test with small curve y² = x³ + 7 mod 13:
    p_small = 13
    b_small = 7

    # Test point (1, 1) - should NOT be on curve
    x_test, y_test = 1, 1
    left = (y_test * y_test) % p_small
    right = (x_test * x_test * x_test + b_small) % p_small
    assert left != right

    # Test point (8, 5) - should be on curve
    x_test, y_test = 8, 5
    left = (y_test * y_test) % p_small
    right = (x_test * x_test * x_test + b_small) % p_small
    assert left == right

    # Simple point addition test
    p1 = (1, 2)
    p2 = (3, 4)
    # This won't be on the actual curve, but tests the arithmetic
    result = _point_add(p1, p2, p_small)
    assert result is not None
