from pathlib import Path


class LocalStorage:
    """Local file storage adapter for development and testing."""

    def __init__(self, root: Path) -> None:
        self.root = root

    def resolve(self, path: Path) -> Path:
        return self.root / path

