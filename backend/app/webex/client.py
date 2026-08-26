import httpx

from .queries import TASK_QUERY, TASK_DETAILS_QUERY, TASK_LEG_DETAILS_QUERY
from .token_manager import token_manager
from ..config import settings


class WxccError(RuntimeError):
    pass


class WxccClient:
    def __init__(self):
        self.base_url = settings.wxcc_base_url.rstrip("/")

    def _headers(self, force_refresh: bool = False):
        token = token_manager.get_access_token(force_refresh=force_refresh)
        return {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    def _do_search(self, payload: dict, force_refresh: bool = False):
        with httpx.Client(timeout=60) as client:
            return client.post(
                f"{self.base_url}/search",
                headers=self._headers(force_refresh=force_refresh),
                json=payload,
            )

    def _search(self, query: str, from_ms: int, to_ms: int) -> dict:
        if to_ms - from_ms > 86_400_000:
            raise ValueError("WxCC Search window cannot exceed 24 hours.")

        payload = {
            "query": query,
            "variables": {"from": from_ms, "to": to_ms},
        }

        resp = self._do_search(payload)

        # One retry after forced refresh for auth failures.
        if resp.status_code in (401, 403) and token_manager.has_refresh_credentials():
            resp = self._do_search(payload, force_refresh=True)

        if resp.status_code >= 400:
            raise WxccError(f"WxCC HTTP {resp.status_code}: {resp.text}")

        body = resp.json()
        if body.get("error") or body.get("errors"):
            raise WxccError(f"WxCC GraphQL error: {body}")
        return body

    def get_tasks(self, from_ms: int, to_ms: int) -> list[dict]:
        body = self._search(TASK_QUERY, from_ms, to_ms)
        return body.get("data", {}).get("task", {}).get("tasks", []) or []

    def get_task_details(self, from_ms: int, to_ms: int) -> list[dict]:
        body = self._search(TASK_DETAILS_QUERY, from_ms, to_ms)
        return body.get("data", {}).get("taskDetails", {}).get("tasks", []) or []

    def get_task_legs(self, from_ms: int, to_ms: int) -> list[dict]:
        body = self._search(TASK_LEG_DETAILS_QUERY, from_ms, to_ms)
        return body.get("data", {}).get("taskLegDetails", {}).get("taskLegs", []) or []
