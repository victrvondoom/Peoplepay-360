"""ECHO runtime wrapper using its reviewed transport and the same SDK adapter."""
from peoplepay_sdk import ExtensionContext as SDKContext, ExtensionRequest as SDKRequest

from echo.extensions.contracts import ExtensionHealth, ManifestAdapter
from echo.extensions.transport import ServiceTransport
from extensions.civicmesh.adapter import CivicMeshProvider
from journey.sdk_bridge import to_echo_result


class _Client:
    def __init__(self, manifest):
        self.transport = ServiceTransport(manifest)

    async def request(self, method, path, *, json=None):
        return await self.transport.request(path, json, method=method)


class CivicMeshEchoAdapter(ManifestAdapter):
    def __init__(self, manifest):
        super().__init__(manifest)
        self.provider = CivicMeshProvider(_Client(manifest))

    async def health(self):
        health = await self.provider.health()
        return ExtensionHealth(extension_id="civicmesh", status=health.status, message=health.message)

    async def execute(self, request):
        sdk_request = SDKRequest(request_id=request.request_id, capability=request.capability,
            context=SDKContext(transaction_id=request.context.requirement_id, trace_id=request.context.requirement_id or request.request_id),
            input=request.input, constraints=request.constraints)
        return to_echo_result(await self.provider.execute(sdk_request))
