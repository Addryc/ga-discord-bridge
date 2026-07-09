"""Discord incoming-webhook client.

Deliberately tiny: the bridge only ever posts a single pre-formatted embed,
so this wraps exactly that. Creating a webhook takes 30 seconds in Discord:
Channel settings → Integrations → Webhooks → New Webhook → Copy URL. Treat
the URL as a secret — anyone holding it can post to the channel.
"""

from __future__ import annotations

import httpx

from ga_discord_bridge.errors import (
    DiscordWebhookResponseError,
    DiscordWebhookTransportError,
)


class DiscordWebhookClient:
    def __init__(
        self,
        webhook_url: str,
        *,
        timeout: float = 10.0,
        client: httpx.Client | None = None,
    ) -> None:
        self._webhook_url = webhook_url.strip()
        self._client = client or httpx.Client(timeout=timeout)
        self._owns_client = client is None

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def __enter__(self) -> "DiscordWebhookClient":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    def post_embed(self, embed: dict[str, object]) -> None:
        """POST one embed to the webhook (Discord replies 204 on success)."""
        try:
            response = self._client.post(self._webhook_url, json={"embeds": [embed]})
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise DiscordWebhookResponseError(
                f"Discord webhook rejected the embed with status {exc.response.status_code}"
            ) from exc
        except httpx.HTTPError as exc:
            raise DiscordWebhookTransportError("Discord webhook request failed") from exc
