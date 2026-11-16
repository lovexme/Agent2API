from .tabbit import TabbitAdapter
from .loomy import LoomyAdapter
from .openai_compat import OpenAICompatAdapter

ADAPTERS = {"tabbit": TabbitAdapter, "loomy": LoomyAdapter, "openai_compat": OpenAICompatAdapter}
