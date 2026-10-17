import os


os.environ["PYTHON_DOTENV_DISABLED"] = "1"
for environment_name in tuple(os.environ):
    if environment_name.startswith(("QX_", "SCANNER_")) or environment_name == "OPENAI_API_KEY":
        os.environ.pop(environment_name, None)

from qx.config.settings import Settings


Settings.model_config = {**Settings.model_config, "env_file": None}
