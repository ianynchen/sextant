class Flags:
    """A plain class of switches. Its values are the repository's constants, not something a
    deployment sets; Sextant does not evaluate the test that reads one, so the route included
    under it exists "not evaluated" (the rule for every test Sextant does not decide)."""

    SUPPORT_ROUTES: bool = True


flags = Flags()
