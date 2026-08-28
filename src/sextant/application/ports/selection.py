"""What every registry-backed port shares when nothing accepts the input."""


class NoAdapterError(LookupError):
    """Nothing in a registry accepts the input. Raised rather than returning
    None: a missing adapter is a gap in the install, and a caller that has to
    remember to check for None is a caller that will forget."""
