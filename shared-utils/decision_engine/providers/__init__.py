"""JEV 1.1 decision-engine providers (spec section 3).

D04 owns ``typesafe_direct``; D06 owns the client-scoped credential stores
(spec section 3.3). Each provider module is stdlib-only, performs no network
or filesystem I/O at import, never touches credentials on disk, and never
mutates process environment.
"""
