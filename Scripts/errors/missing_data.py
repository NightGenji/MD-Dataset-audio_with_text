class NoneFound(Exception):
    def __init__(self, hint, message="Found None - Needs actual Data"):
        self.hint = hint
        self.message = message
        super().__init__(f"{message}: {hint}")
