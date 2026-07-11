"""Service package for SmartCS.

Import concrete services from their modules to avoid eager circular imports while
legacy routes are being migrated.
"""

__all__ = ["ChatService", "CrisisService", "UserService"]


def __getattr__(name):
    if name == "ChatService":
        from services.chat_service import ChatService
        return ChatService
    if name == "CrisisService":
        from services.crisis_service import CrisisService
        return CrisisService
    if name == "UserService":
        from services.user_service import UserService
        return UserService
    raise AttributeError(name)
