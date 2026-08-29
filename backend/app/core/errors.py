"""Domain errors that fail closed without embedding external-service secrets."""


class ExecutionDisabledError(RuntimeError):
    """Raised if future execution code is invoked before an authorized milestone."""


class ExecutionError(RuntimeError):
    """Raised when execution operations fail."""


class MarketDataError(RuntimeError):
    """Raised when market data operations fail."""

    def __init__(
        self,
        message: str,
        original: Exception | None = None,
        reason_code: str | None = None,
    ):
        super().__init__(message)
        self.original = original
        self.reason_code = reason_code


class CredentialsUnavailableError(RuntimeError):
    """Raised when no complete, paper-safe Alpaca credential bundle is available."""
