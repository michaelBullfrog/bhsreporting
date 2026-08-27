import httpx

from .queries import TASK_QUERY, TASK_DETAILS_QUERY, TASK_LEG_DETAILS_QUERY, AGENT_SESSION_QUERY
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

    def _search(
        self,
        query: str,
        from_ms: int,
        to_ms: int,
        extra_variables: dict | None = None,
    ) -> dict:
        if to_ms - from_ms > 86_400_000:
            raise ValueError("WxCC Search window cannot exceed 24 hours.")

        variables = {"from": from_ms, "to": to_ms}
        if extra_variables:
            variables.update(extra_variables)

        payload = {
            "query": query,
            "variables": variables,
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

    def get_agent_sessions(self, from_ms: int, to_ms: int) -> list[dict]:
        """
        Fetch agent sessions and exhaust activity pagination.

        WxCC returns activities as a paginated connection. The first page can
        contain fewer nodes than totalCount, so this method repeatedly queries
        the same window with the returned endCursor and merges activity nodes
        into each channel/session.
        """
        sessions_by_id: dict[str, dict] = {}
        after = None
        seen_cursors: set[str] = set()

        while True:
            body = self._search(
                AGENT_SESSION_QUERY,
                from_ms,
                to_ms,
                extra_variables={"after": after},
            )

            page_sessions = (
                body.get("data", {})
                .get("agentSession", {})
                .get("agentSessions", [])
                or []
            )

            any_next_page = False
            next_cursor = None

            for session in page_sessions:
                session_id = session.get("agentSessionId")
                if not session_id:
                    continue

                existing = sessions_by_id.get(session_id)
                if existing is None:
                    # Deep-enough copy for the structures we mutate below.
                    existing = {
                        **session,
                        "channelInfo": [],
                    }
                    for ch in session.get("channelInfo") or []:
                        acts = ch.get("activities") or {}
                        existing["channelInfo"].append({
                            **ch,
                            "activities": {
                                **acts,
                                "nodes": list(acts.get("nodes") or []),
                            },
                        })
                    sessions_by_id[session_id] = existing
                else:
                    channels_by_id = {
                        ch.get("channelId"): ch
                        for ch in existing.get("channelInfo") or []
                    }

                    for ch in session.get("channelInfo") or []:
                        channel_id = ch.get("channelId")
                        incoming_acts = ch.get("activities") or {}
                        incoming_nodes = incoming_acts.get("nodes") or []

                        if channel_id not in channels_by_id:
                            existing.setdefault("channelInfo", []).append({
                                **ch,
                                "activities": {
                                    **incoming_acts,
                                    "nodes": list(incoming_nodes),
                                },
                            })
                            continue

                        target = channels_by_id[channel_id]
                        target_acts = target.setdefault("activities", {})
                        target_nodes = target_acts.setdefault("nodes", [])

                        existing_ids = {
                            n.get("id") for n in target_nodes if n.get("id")
                        }
                        for node in incoming_nodes:
                            node_id = node.get("id")
                            if node_id and node_id in existing_ids:
                                continue
                            target_nodes.append(node)
                            if node_id:
                                existing_ids.add(node_id)

                        if incoming_acts.get("totalCount") is not None:
                            target_acts["totalCount"] = incoming_acts["totalCount"]
                        if incoming_acts.get("pageInfo") is not None:
                            target_acts["pageInfo"] = incoming_acts["pageInfo"]

                # Determine whether this response indicates more activity pages.
                for ch in session.get("channelInfo") or []:
                    page_info = (ch.get("activities") or {}).get("pageInfo") or {}
                    if page_info.get("hasNextPage"):
                        any_next_page = True
                        cursor = page_info.get("endCursor")
                        if cursor:
                            next_cursor = cursor
                            break
                if next_cursor:
                    break

            if not any_next_page:
                break

            if not next_cursor:
                raise WxccError(
                    "WxCC activity pagination reported hasNextPage=true "
                    "without an endCursor."
                )

            if next_cursor in seen_cursors:
                raise WxccError(
                    f"WxCC activity pagination repeated cursor {next_cursor}."
                )

            seen_cursors.add(next_cursor)
            after = next_cursor

        # Sort merged activity nodes chronologically for stable storage/output.
        for session in sessions_by_id.values():
            for ch in session.get("channelInfo") or []:
                acts = ch.get("activities") or {}
                nodes = acts.get("nodes") or []
                nodes.sort(key=lambda n: (n.get("startTime") or 0, n.get("id") or ""))

        return list(sessions_by_id.values())
