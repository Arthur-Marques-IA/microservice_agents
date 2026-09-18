"""Cliente HTTP fino da API do agent-service — uma função por endpoint.

Compartilhado pelos comandos da CLI e por um futuro TUI. Devolve os dicts
da resposta; erros viram `ApiError` (HTTP 4xx/5xx) ou `ServiceUnavailable`
(serviço fora do ar).
"""

import json
from collections.abc import Iterator
from typing import Any

import httpx


class ApiError(Exception):
    def __init__(self, status: int, detail: Any):
        self.status = status
        self.detail = detail
        super().__init__(f"HTTP {status}: {detail}")


class ServiceUnavailable(Exception):
    pass


class Client:
    def __init__(self, base_url: str, timeout: float = 120.0, transport: httpx.BaseTransport | None = None):
        self.base_url = base_url.rstrip("/")
        self._http = httpx.Client(base_url=self.base_url, timeout=timeout, transport=transport)

    def _request(self, method: str, path: str, **kwargs: Any) -> Any:
        # Uma nova tentativa para falhas de transporte transitórias (port-forward do
        # Docker). POST só repete se nem chegou a conectar, para não duplicar criação.
        for attempt in (1, 2):
            try:
                response = self._http.request(method, path, **kwargs)
                break
            except httpx.TransportError as exc:
                retryable = method in ("GET", "PUT", "DELETE") or isinstance(exc, httpx.ConnectError)
                if attempt == 2 or not retryable:
                    raise ServiceUnavailable(f"não consegui falar com {self.base_url} ({type(exc).__name__})") from exc
        if response.status_code >= 400:
            raise ApiError(response.status_code, _detail(response))
        if response.status_code == 204 or not response.content:
            return None
        return response.json()

    # -- saúde / config ----------------------------------------------------

    def health(self) -> dict[str, Any]:
        return self._request("GET", "/health")

    def observability_config(self) -> dict[str, Any]:
        return self._request("GET", "/observability/config")

    def python_tools_config(self) -> dict[str, Any]:
        return self._request("GET", "/tools/python-config")

    # -- agentes -------------------------------------------------------------

    def list_agents(self) -> list[dict[str, Any]]:
        return self._request("GET", "/agents")

    def get_agent(self, agent_type: str) -> dict[str, Any]:
        return self._request("GET", f"/agents/{agent_type}")

    def create_agent(self, body: dict[str, Any]) -> dict[str, Any]:
        return self._request("POST", "/agents", json=body)

    def update_agent(self, agent_type: str, changes: dict[str, Any]) -> dict[str, Any]:
        """PUT parcial: só as chaves enviadas mudam (a API usa `exclude_unset`)."""
        return self._request("PUT", f"/agents/{agent_type}", json=changes)

    def delete_agent(self, agent_type: str) -> None:
        self._request("DELETE", f"/agents/{agent_type}")

    def agent_versions(self, agent_type: str) -> list[dict[str, Any]]:
        return self._request("GET", f"/agents/{agent_type}/versions")

    def integration(self, agent_type: str) -> dict[str, Any]:
        """Contrato pronto pra quem vai chamar o agente de outro módulo."""
        return self._request(
            "GET", f"/agents/{agent_type}/integration", params={"base_url": self.base_url}
        )

    def send_feedback(self, agent_type: str, session_id: str, feedback: str) -> dict[str, Any]:
        return self._request(
            "POST", f"/agents/{agent_type}/feedback", json={"session_id": session_id, "feedback": feedback}
        )

    def get_feedback(self, agent_type: str) -> dict[str, Any]:
        return self._request("GET", f"/agents/{agent_type}/feedback")

    # -- chat ----------------------------------------------------------------

    def chat_stream(self, body: dict[str, Any]) -> Iterator[tuple[str, dict[str, Any]]]:
        """Consome o SSE de `POST /chat/stream`, rendendo `(evento, dados)`:
        `run`, `message`, `usage`, `error` e `done`."""
        try:
            with self._http.stream("POST", "/chat/stream", json=body, timeout=httpx.Timeout(10.0, read=None)) as response:
                if response.status_code >= 400:
                    response.read()
                    raise ApiError(response.status_code, _detail(response))
                yield from _parse_sse(response.iter_lines())
        except httpx.TransportError as exc:
            raise ServiceUnavailable(f"não consegui falar com {self.base_url} ({type(exc).__name__})") from exc

    def analyze(self, body: dict[str, Any]) -> dict[str, Any]:
        return self._request("POST", "/analyze", json=body)

    # -- tools ---------------------------------------------------------------

    def list_tools(self) -> list[dict[str, Any]]:
        return self._request("GET", "/tools")

    def get_tool(self, tool_name: str) -> dict[str, Any]:
        return self._request("GET", f"/tools/{tool_name}")

    def tool_catalog(self) -> list[dict[str, Any]]:
        return self._request("GET", "/tools/catalog")

    def invoke_tool(self, tool_name: str, arguments: dict[str, Any], function_name: str | None) -> dict[str, Any]:
        return self._request(
            "POST", f"/tools/{tool_name}/invoke", json={"arguments": arguments, "function_name": function_name}
        )

    # -- provedores e credenciais de modelo ----------------------------------

    def list_providers(self) -> list[dict[str, Any]]:
        return self._request("GET", "/model-providers")

    def list_credentials(self) -> list[dict[str, Any]]:
        return self._request("GET", "/model-credentials")

    def create_credential(self, body: dict[str, Any]) -> dict[str, Any]:
        return self._request("POST", "/model-credentials", json=body)

    def update_credential(self, credential_id: str, body: dict[str, Any]) -> dict[str, Any]:
        return self._request("PUT", f"/model-credentials/{credential_id}", json=body)

    def delete_credential(self, credential_id: str) -> None:
        self._request("DELETE", f"/model-credentials/{credential_id}")

    def test_credential(self, credential_id: str) -> dict[str, Any]:
        """Testa a chave salva (sem gastar tokens) e grava o resultado."""
        return self._request("POST", f"/model-credentials/{credential_id}/test", json={})

    # -- collections (bases de conhecimento) ---------------------------------

    def list_collections(self) -> list[dict[str, Any]]:
        return self._request("GET", "/collections")

    def create_collection(self, body: dict[str, Any]) -> dict[str, Any]:
        return self._request("POST", "/collections", json=body)

    def delete_collection(self, name: str) -> None:
        self._request("DELETE", f"/collections/{name}")

    def add_document(self, name: str, body: dict[str, Any]) -> dict[str, Any]:
        return self._request("POST", f"/collections/{name}/documents", json=body)

    def search_collection(self, name: str, query: str, limit: int) -> list[dict[str, Any]]:
        return self._request("GET", f"/collections/{name}/search", params={"query": query, "limit": limit})

    # -- observabilidade -----------------------------------------------------

    def list_runs(self, **params: Any) -> dict[str, Any]:
        return self._request("GET", "/observability/runs", params={k: v for k, v in params.items() if v is not None})

    def run_trace(self, run_id: str) -> dict[str, Any]:
        return self._request("GET", f"/observability/runs/{run_id}/trace")

    def score(self, body: dict[str, Any]) -> dict[str, Any]:
        return self._request("POST", "/observability/scores", json=body)


def _detail(response: httpx.Response) -> Any:
    try:
        payload = response.json()
    except ValueError:
        return response.text or response.reason_phrase
    return payload.get("detail", payload) if isinstance(payload, dict) else payload


def _parse_sse(lines: Iterator[str]) -> Iterator[tuple[str, dict[str, Any]]]:
    event, data = "message", []
    for line in lines:
        if not line:
            if data:
                yield event, _loads("\n".join(data))
            event, data = "message", []
        elif line.startswith("event:"):
            event = line[6:].strip()
        elif line.startswith("data:"):
            data.append(line[5:].lstrip())
    if data:
        yield event, _loads("\n".join(data))


def _loads(raw: str) -> dict[str, Any]:
    try:
        value = json.loads(raw)
    except ValueError:
        return {"raw": raw}
    return value if isinstance(value, dict) else {"value": value}
