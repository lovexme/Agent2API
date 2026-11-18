from abc import ABC, abstractmethod

class PlatformAdapter(ABC):
    @abstractmethod
    async def check(self, account): ...

    @abstractmethod
    async def models(self, account): ...

    @abstractmethod
    async def complete(self, account, model, messages, stream=False, temperature=None, tools=None, tool_choice=None): ...
    supports_tools = False
