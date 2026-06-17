import importlib.metadata

try:
    version = importlib.metadata.version("hive-nectar")
except importlib.metadata.PackageNotFoundError:
    version = "1.0.1"
