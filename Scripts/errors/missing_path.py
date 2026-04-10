class PathMissing(Exception):
    def __init__(self, hint, message="Path Missing"):
        self.hint = hint
        self.message = message
        super().__init__(f"{message}: {hint}")