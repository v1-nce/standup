class StandupError(Exception):
    """Root of every failure the backend raises. Third-party exceptions never escape past it."""


class NotFound(StandupError):
    """The thing asked for does not exist."""


class InvalidInput(StandupError):
    """The caller asked for something impossible."""


class Busy(StandupError):
    """Something is already running that this would tread on."""


class NotConfigured(StandupError):
    """A prerequisite the user must supply is missing."""


class Upstream(StandupError):
    """An external dependency failed."""
