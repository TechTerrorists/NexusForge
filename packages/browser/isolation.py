import os
import uuid
import shutil
import logging
import asyncio
from dataclasses import dataclass, field
from typing import Any, Optional

logger = logging.getLogger(__name__)


@dataclass
class BrowserProfile:
    session_id: str
    profile_dir: str
    cdp_socket_path: str
    user_data_dir: str
    cookies_dir: str
    cache_dir: str
    created_at: float = field(default_factory=lambda: __import__("time").time())

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "profile_dir": self.profile_dir,
            "cdp_socket_path": self.cdp_socket_path,
            "user_data_dir": self.user_data_dir,
            "cookies_dir": self.cookies_dir,
            "cache_dir": self.cache_dir,
            "created_at": self.created_at,
        }


class BrowserIsolationManager:
    def __init__(self, base_dir: str = "/tmp/nexusforge_browser_profiles"):
        self._base_dir = base_dir
        self._profiles: dict[str, BrowserProfile] = {}
        os.makedirs(base_dir, exist_ok=True)

    async def create_profile(self, session_id: str) -> BrowserProfile:
        """Create an isolated Chrome profile for a session.

        Creates separate directories for cookies, web storage, and cache
        to ensure complete isolation between sessions.
        """
        if session_id in self._profiles:
            logger.warning(
                f"Profile already exists for session {session_id}, "
                "returning existing profile"
            )
            return self._profiles[session_id]

        profile_dir = os.path.join(self._base_dir, session_id)
        user_data_dir = os.path.join(profile_dir, "user_data")
        cookies_dir = os.path.join(profile_dir, "cookies")
        cache_dir = os.path.join(profile_dir, "cache")
        cdp_socket_path = os.path.join(profile_dir, "cdp.sock")

        os.makedirs(user_data_dir, exist_ok=True)
        os.makedirs(cookies_dir, exist_ok=True)
        os.makedirs(cache_dir, exist_ok=True)

        profile = BrowserProfile(
            session_id=session_id,
            profile_dir=profile_dir,
            cdp_socket_path=cdp_socket_path,
            user_data_dir=user_data_dir,
            cookies_dir=cookies_dir,
            cache_dir=cache_dir,
        )

        self._profiles[session_id] = profile
        logger.info(
            f"Created browser profile for session {session_id} "
            f"at {profile_dir}"
        )
        return profile

    async def get_cdp_connection(self, session_id: str) -> dict[str, Any]:
        """Get CDP websocket connection info for a session browser.

        Returns a dict with the websocket URL and connection details
        that can be used to connect to the browser via CDP.
        """
        if session_id not in self._profiles:
            raise ValueError(
                f"No profile found for session {session_id}. "
                "Create a profile first."
            )

        profile = self._profiles[session_id]

        return {
            "websocket_url": f"ws://127.0.0.1:9222/devtools/browser/{session_id}",
            "http_url": "http://127.0.0.1:9222",
            "socket_path": profile.cdp_socket_path,
            "profile_dir": profile.profile_dir,
            "user_data_dir": profile.user_data_dir,
        }

    async def destroy_profile(self, session_id: str) -> bool:
        """Destroy a browser profile and clean up all associated files."""
        if session_id not in self._profiles:
            logger.warning(
                f"No profile found for session {session_id} to destroy"
            )
            return False

        profile = self._profiles.pop(session_id)

        try:
            if os.path.exists(profile.profile_dir):
                shutil.rmtree(profile.profile_dir)
            logger.info(
                f"Destroyed browser profile for session {session_id}"
            )
            return True
        except Exception as e:
            logger.error(
                f"Error destroying profile for session {session_id}: {e}"
            )
            return False

    def get_all_profiles(self) -> list[dict[str, Any]]:
        """Get all active browser profiles."""
        return [profile.to_dict() for profile in self._profiles.values()]

    def get_profile(self, session_id: str) -> Optional[BrowserProfile]:
        """Get a profile by session ID."""
        return self._profiles.get(session_id)

    async def cleanup_stale_profiles(
        self, max_age_seconds: int = 3600
    ) -> int:
        """Clean up profiles older than max_age_seconds. Returns count removed."""
        import time

        current_time = time.time()
        stale_sessions = []

        for session_id, profile in self._profiles.items():
            if current_time - profile.created_at > max_age_seconds:
                stale_sessions.append(session_id)

        for session_id in stale_sessions:
            await self.destroy_profile(session_id)

        if stale_sessions:
            logger.info(f"Cleaned up {len(stale_sessions)} stale browser profiles")

        return len(stale_sessions)

    def get_profile_count(self) -> int:
        """Get the number of active profiles."""
        return len(self._profiles)
