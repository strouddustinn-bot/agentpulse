"""Shared errors for host-platform capabilities that are not yet supported."""


class UnsupportedPlatformError(RuntimeError):
    """A host capability is unavailable and must fail closed."""


__all__ = ["UnsupportedPlatformError"]
