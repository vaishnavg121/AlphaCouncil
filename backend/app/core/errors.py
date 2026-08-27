"""Domain errors that fail closed without embedding external-service secrets."""


class ExecutionDisabledError(RuntimeError):
    """Raised if future execution code is invoked before an authorized milestone."""


class CredentialsUnavailableError(RuntimeError):
    """Raised when no complete, paper-safe Alpaca credential bundle is available."""
