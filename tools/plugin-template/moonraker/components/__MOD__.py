# __NAME__: Moonraker part. GET /server/__MOD__/hello returns the
# greeting.
#
# This file may be distributed under the terms of the GNU GPLv3 license.
from ..common import RequestType


class __CLASS__Api:
    def __init__(self, config):
        self.server = config.get_server()
        self.greeting = config.get("greeting", "Hello")
        self.server.register_endpoint(
            "/server/__MOD__/hello", RequestType.GET, self._handle_hello)

    async def _handle_hello(self, web_request):
        return {"message": self.greeting}


def load_component(config):
    return __CLASS__Api(config)
