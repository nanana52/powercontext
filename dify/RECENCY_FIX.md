# Memory chronology repair
The previous adapter used FTS relevance order to interpret "last visit". A real SDK reproduction with a short first entry and longer second entry returned the older entry first. The ledger query now reads authoritative current Memory entries and orders by created_in_revision descending; explicit semantic queries retain actual FTS. This is a functional fix, not an established explanation of official error100.

The saved ledger contains the current item and action only. Previously each rendered reply embedded its previous-history opening, and then that whole reply was saved again, unnecessarily nesting old records. Existing entries remain readable. No history or player input is fabricated.
