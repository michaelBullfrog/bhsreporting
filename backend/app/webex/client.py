import httpx

from .queries import (TASK_QUERY, TASK_DETAILS_QUERY, TASK_LEG_DETAILS_QUERY, AGENT_SESSION_QUERY, AGENT_ACTIVITY_PAGE_QUERY)
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


    @staticmethod
    def _merge_activity_nodes(target_activity: dict, incoming_activity: dict) -> None:
        """Merge activity nodes by stable WxCC activity id."""
        target_nodes = target_activity.setdefault("nodes", [])
        known_ids = {
            node.get("id")
            for node in target_nodes
            if isinstance(node, dict) and node.get("id")
        }

        for node in incoming_activity.get("nodes") or []:
            if not isinstance(node, dict):
                continue
            node_id = node.get("id")
            if node_id and node_id in known_ids:
                continue
            target_nodes.append(node)
            if node_id:
                known_ids.add(node_id)

        if incoming_activity.get("totalCount") is not None:
            target_activity["totalCount"] = incoming_activity["totalCount"]

        if incoming_activity.get("pageInfo") is not None:
            target_activity["pageInfo"] = incoming_activity["pageInfo"]

    def _fetch_activity_pages_for_channel(
        self,
        *,
        from_ms: int,
        to_ms: int,
        session_id: str,
        channel_id: str,
        target_activity: dict,
    ) -> None:
        """
        Exhaust inner AAR pagination for exactly one session/channel.

        Inner cursors are scoped to the record that produced them. The query is
        therefore filtered to the ASR session and AAR agentChannelId before the
        cursor is reused.
        """
        page_info = target_activity.get("pageInfo") or {}
        after = page_info.get("endCursor")
        has_next = bool(page_info.get("hasNextPage"))
        seen_cursors: set[str] = set()

        while has_next:
            if not after:
                raise WxccError(
                    "WxCC activity pagination reported hasNextPage=true "
                    f"without an endCursor for session={session_id}, "
                    f"channel={channel_id}."
                )

            if after in seen_cursors:
                raise WxccError(
                    "WxCC activity pagination repeated cursor "
                    f"for session={session_id}, channel={channel_id}."
                )
            seen_cursors.add(after)

            body = self._search(
                AGENT_ACTIVITY_PAGE_QUERY,
                from_ms,
                to_ms,
                extra_variables={
                    "sessionId": session_id,
                    "channelId": channel_id,
                    "after": after,
                },
            )

            page_sessions = (
                body.get("data", {})
                .get("agentSession", {})
                .get("agentSessions", [])
                or []
            )

            matched_activity = None

            for session in page_sessions:
                if session.get("agentSessionId") != session_id:
                    continue

                for channel in session.get("channelInfo") or []:
                    if channel.get("channelId") != channel_id:
                        continue
                    matched_activity = channel.get("activities") or {}
                    break

                if matched_activity is not None:
                    break

            if matched_activity is None:
                raise WxccError(
                    "Targeted WxCC activity page did not return the requested "
                    f"session/channel: session={session_id}, channel={channel_id}."
                )

            self._merge_activity_nodes(target_activity, matched_activity)

            page_info = matched_activity.get("pageInfo") or {}
            has_next = bool(page_info.get("hasNextPage"))
            after = page_info.get("endCursor")

    def get_agent_sessions(self, from_ms: int, to_ms: int) -> list[dict]:
        """
        Fetch all agent sessions and all nested AAR activity nodes.

        Outer agentSession records are paginated independently using the
        top-level Pagination cursor. Each channel's inner activity connection is
        then paginated independently using its own cursor and targeted filters.
        """
        sessions_by_id: dict[str, dict] = {}

        # Cisco documents "NA" as a valid first-page cursor value.
        outer_cursor = "NA"
        seen_outer_cursors: set[str] = set()

        while True:
            body = self._search(
                AGENT_SESSION_QUERY,
                from_ms,
                to_ms,
                extra_variables={"cursor": outer_cursor},
            )

            agent_session_payload = (
                body.get("data", {})
                .get("agentSession", {})
                or {}
            )
            page_sessions = agent_session_payload.get("agentSessions", []) or []

            for session in page_sessions:
                session_id = session.get("agentSessionId")
                if not session_id:
                    continue

                if session_id not in sessions_by_id:
                    copied = {
                        **session,
                        "channelInfo": [],
                    }

                    for channel in session.get("channelInfo") or []:
                        activities = channel.get("activities") or {}
                        copied["channelInfo"].append({
                            **channel,
                            "activities": {
                                **activities,
                                "nodes": list(activities.get("nodes") or []),
                            },
                        })

                    sessions_by_id[session_id] = copied
                else:
                    existing = sessions_by_id[session_id]
                    channels_by_id = {
                        channel.get("channelId"): channel
                        for channel in existing.get("channelInfo") or []
                    }

                    for channel in session.get("channelInfo") or []:
                        channel_id = channel.get("channelId")
                        activities = channel.get("activities") or {}

                        if channel_id not in channels_by_id:
                            existing.setdefault("channelInfo", []).append({
                                **channel,
                                "activities": {
                                    **activities,
                                    "nodes": list(activities.get("nodes") or []),
                                },
                            })
                            continue

                        target_channel = channels_by_id[channel_id]
                        target_activity = target_channel.setdefault(
                            "activities", {}
                        )
                        self._merge_activity_nodes(
                            target_activity,
                            activities,
                        )

            outer_page_info = agent_session_payload.get("pageInfo") or {}
            if not outer_page_info.get("hasNextPage"):
                break

            next_cursor = outer_page_info.get("endCursor")
            if not next_cursor:
                raise WxccError(
                    "WxCC agentSession pagination reported hasNextPage=true "
                    "without an endCursor."
                )

            if next_cursor in seen_outer_cursors:
                raise WxccError(
                    f"WxCC agentSession pagination repeated cursor {next_cursor}."
                )

            seen_outer_cursors.add(next_cursor)
            outer_cursor = next_cursor

        # Now exhaust each inner AAR connection independently.
        for session_id, session in sessions_by_id.items():
            for channel in session.get("channelInfo") or []:
                channel_id = channel.get("channelId")
                if not channel_id:
                    continue

                activities = channel.setdefault("activities", {})
                page_info = activities.get("pageInfo") or {}

                if page_info.get("hasNextPage"):
                    self._fetch_activity_pages_for_channel(
                        from_ms=from_ms,
                        to_ms=to_ms,
                        session_id=session_id,
                        channel_id=channel_id,
                        target_activity=activities,
                    )

                nodes = activities.get("nodes") or []
                nodes.sort(
                    key=lambda node: (
                        node.get("startTime") or 0,
                        node.get("id") or "",
                    )
                )

                # This is retained in raw payloads and is useful for diagnosing
                # future source-data/pagination discrepancies.
                activities["fetchedCount"] = len(nodes)
                total_count = int(activities.get("totalCount") or 0)
                activities["paginationComplete"] = (
                    total_count == 0 or len(nodes) >= total_count
                )

        return list(sessions_by_id.values())
