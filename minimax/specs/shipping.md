# Shipping policy (active specification, revision 2)

- SPEC-SHIP-001: For subtotal **>= CNY 100.00**, standard shipping costs CNY 0.
- SPEC-SHIP-002: For subtotal < CNY 100.00, standard shipping costs CNY 8.
- SPEC-SHIP-003: Express shipping adds CNY 12 to the applicable standard fee.
- SPEC-SHIP-004: Negative subtotal and unknown shipping methods raise ValueError.
- SPEC-SHIP-005: Keep the public `shipping_quote(subtotal, method="standard")` API
  and Decimal output unchanged.
The archived policy is obsolete. Fix the inclusive boundary without changing other behaviors.
