import json
import logging
import os
import random
import traceback
import debugpy
from dataclasses import dataclass
from typing import Any, Optional, Tuple

from aiohttp import ClientSession, web
from aiohttp.typedefs import Handler
from typing_extensions import Literal, TypedDict

from .utils import log_msg

LOGGER = logging.getLogger(__name__)

DEFAULT_POSTGRES = bool(os.getenv("POSTGRES"))
DEFAULT_INTERNAL_HOST = "127.0.0.1"
DEFAULT_EXTERNAL_HOST = "localhost"

START_TIMEOUT = float(os.getenv("START_TIMEOUT", 60.0))

RUN_MODE = os.getenv("RUNMODE")

GENESIS_URL = os.getenv("GENESIS_URL")
LEDGER_URL = os.getenv("LEDGER_URL")

if RUN_MODE == "docker":
    DEFAULT_INTERNAL_HOST = os.getenv("DOCKERHOST") or "host.docker.internal"
    DEFAULT_EXTERNAL_HOST = DEFAULT_INTERNAL_HOST
elif RUN_MODE == "pwd":
    DEFAULT_EXTERNAL_HOST = os.getenv("DOCKERHOST") or "host.docker.internal"


class AgentPorts(TypedDict):
    admin: int
    http: int
    ws: int


def get_ledger_url(ledger_url: str = None):
    return ledger_url or LEDGER_URL or f"http://{DEFAULT_EXTERNAL_HOST}:9000"


@dataclass
class BackchannelCommand:
    """Parsed backchannel command

    {method} https://<url>/agent/command/{topic}/{operation|record_id}
    body: {data}
    """

    topic: str
    method: str
    operation: Optional[str]
    record_id: Optional[str]
    data: Optional[Any]
    anoncreds: Optional[bool] = False


async def default_genesis_txns():
    genesis = None
    try:
        if GENESIS_URL:
            async with ClientSession() as session:
                print("From GENESIS_URL:", GENESIS_URL)
                async with session.get(GENESIS_URL) as resp:
                    genesis = await resp.text()
        elif RUN_MODE == "docker":
            async with ClientSession() as session:
                ledger_url = get_ledger_url()
                async with session.get(f"{ledger_url}/genesis") as resp:
                    genesis = await resp.text()
        else:
            print("With local file:", "../local-genesis.txt")
            with open("../local-genesis.txt", "r") as genesis_file:
                genesis = genesis_file.read()
    except Exception:
        LOGGER.exception("Error loading genesis transactions:")
    return genesis


class AgentBackchannel:
    """
    Base class for building Aries agent backchannel adapters for integration
    into the interoperability test suite.

    Extend this base class and implement hooks to communicate with a specific
    agent.
    """

    def __init__(
        self,
        ident: str,
        agent_ports: AgentPorts,
        genesis_data: str = None,
        params: dict = {},
        extra_args: dict = {},
    ):
        self.ACTIVE = False

        self.ident = ident
        self.agent_ports = agent_ports
        self.genesis_data = genesis_data
        self.params = params
        self.extra_args = extra_args
        rand_name = str(random.randint(100_000, 999_999))
        self.seed = ("my_seed_000000000000000000000000" + rand_name)[-32:]

        # Set the backchannel on each request so it can be used by the route methods
        @web.middleware
        async def backchannel_middleware(request: web.Request, handler: Handler):
            request["backchannel"] = self

            return await handler(request)

        app = web.Application(middlewares=[backchannel_middleware])
        self.app = app

        self.internal_host = DEFAULT_INTERNAL_HOST
        self.external_host = DEFAULT_EXTERNAL_HOST
        self.label = ident

        self.admin_url = f"http://{self.internal_host}:" + str(agent_ports["admin"])

        self.storage_type = "askar"  # deprecated - should be removed
        self.wallet_type = (
            extra_args.get("wallet-type") if extra_args.get("wallet-type") else "askar"
        )
        self.wallet_name = self.ident.lower().replace(" ", "") + rand_name
        self.wallet_key = self.ident + rand_name
        self.did = None
        self.postgres = False

        self.client_session: ClientSession = ClientSession()

    def activate(self, active: bool = True):
        self.ACTIVE = active

    def get_agent_endpoint(self, transport: Literal["http", "ws"]) -> str:
        port = str(self.agent_ports[transport])

        # may be set via ngrok. Not supported for WS
        agent_endpoint = os.getenv("AGENT_PUBLIC_ENDPOINT")
        if transport == "http" and agent_endpoint:
            return agent_endpoint
        elif RUN_MODE == "pwd":
            return f"{transport}://{self.external_host}".replace("{PORT}", port)

        return f"{transport}://{self.external_host}:{port}"

    async def listen_backchannel(self, backchannel_port: int):
        """
        Setup the routes to allow the test harness to send commands to and get replies
        from the Agent under test.

        Expected topics include:

            schema                 GET to return a list and POST to create/update
            credential-definition  GET to return a list and POST to create/update
            connection             GET to return a list or single; POST to create/update*
            issue-credential       GET to return a list or single; POST to create/update*
            credential             GET to return a list of single from wallet; POST to remove*
            proof                  GET to return a list or single; POST to create/update*

        GET with no parameters returns all
        GET with an "id" parameter will return a single record
        POST will submit a JSON payload
        POST* will contain an "operation" element within the payload to define the operation
        POST operations on existing records must contain an "id" element
        POST operations will contain a "data" element which is the payload to pass through to the agent

        E.g.:  POST to /agent/command/issue_credential/send-proposal { "data": {...} }
        E.g.:  POST to /agent/command/issue_credential/issue         { "id": "<cred exch id>", "data": {...} }
        """

        self.app.add_routes(
            [
                web.post("/agent/command/{topic}/", self._post_command_backchannel),
                web.post("/agent/command/{topic}", self._post_command_backchannel),
                web.post(
                    "/agent/command/{topic}/{operation}/",
                    self._post_command_backchannel,
                ),
                web.post(
                    "/agent/command/{topic}/{operation}", self._post_command_backchannel
                ),
                web.get("/agent/command/{topic}/", self._get_command_backchannel),
                web.get("/agent/command/{topic}", self._get_command_backchannel),
                web.get("/agent/command/{topic}/{id}/", self._get_command_backchannel),
                web.get("/agent/command/{topic}/{id}", self._get_command_backchannel),
                web.get(
                    "/agent/command/{topic}/{operation}/{id}/",
                    self._get_command_backchannel,
                ),
                web.get(
                    "/agent/command/{topic}/{operation}/{id}",
                    self._get_command_backchannel,
                ),
                web.delete(
                    "/agent/command/{topic}/{id}/", self._delete_command_backchannel
                ),
                web.delete(
                    "/agent/command/{topic}/{id}", self._delete_command_backchannel
                ),
                web.get("/agent/response/{topic}/", self._get_response_backchannel),
                web.get("/agent/response/{topic}", self._get_response_backchannel),
                web.get(
                    "/agent/response/{topic}/{id}/", self._get_response_backchannel
                ),
                web.get("/agent/response/{topic}/{id}", self._get_response_backchannel),
            ]
        )

        runner = web.AppRunner(self.app)
        await runner.setup()
        self.backchannel_site = web.TCPSite(runner, "0.0.0.0", backchannel_port)
        await self.backchannel_site.start()
        print("Listening to backchannel on port", backchannel_port)

    async def parse_request(self, request: web.Request) -> BackchannelCommand:
        record_id = request.match_info.get("id", None)
        operation = request.match_info.get("operation", None)
        topic = request.match_info.get("topic", None)
        anoncreds = request.query.get("anoncreds", False)
        
        if anoncreds == 'True':
            anoncreds = True
            
        method = request.method

        if not topic:
            raise Exception("Topic must be provided")

        data = None
        if method == "POST" and request.has_body:
            payload = await request.json()

            if "data" in payload:
                data = payload["data"]

            if "id" in payload:
                record_id = payload["id"]
            elif "cred_ex_id" in payload:
                record_id = payload["cred_ex_id"]

        return BackchannelCommand(
            record_id=record_id,
            operation=operation,
            topic=topic,
            method=method,
            data=data,
            anoncreds=anoncreds
        )

    def not_found_response(self, data: Any):
        resp_text = "404 not found: " + str(data)
        return web.Response(body=resp_text.encode("utf8"), status=404)

    def not_implemented_response(self, data: Any):
        resp_text = "501 not implemented: " + str(data)
        return web.Response(body=resp_text.encode("utf8"), status=501)

    async def _post_command_backchannel(self, request: web.Request):
        """
        Post a POST command to the agent.
        """
        command = None
        try:
            command = await self.parse_request(request)

            (resp_status, resp_text) = await self.make_agent_POST_request(command)

            if resp_status == 200:
                return web.Response(text=resp_text, status=resp_status)
            elif resp_status == 404:
                return self.not_found_response(json.dumps(command.__dict__))
            elif resp_status == 501:
                return self.not_implemented_response(json.dumps(command.__dict__))
            else:
                return web.Response(body=resp_text, status=resp_status)
        except NotImplementedError:
            return self.not_implemented_response(json.dumps(command.__dict__))
        except Exception as e:
            print("Exception:", e)
            traceback.print_exc()
            return web.Response(body=str(e), status=500)

    async def _get_command_backchannel(self, request: web.Request):
        """
        Post a GET command to the agent.
        """
        command = None
        try:
            command = await self.parse_request(request)

            (resp_status, resp_text) = await self.make_agent_GET_request(command)

            if resp_status == 200:
                return web.Response(text=resp_text, status=resp_status)
            elif resp_status == 404:
                return self.not_found_response(json.dumps(command.__dict__))
            elif resp_status == 501:
                return self.not_implemented_response(json.dumps(command.__dict__))
            else:
                return web.Response(body=resp_text, status=resp_status)
        except NotImplementedError:
            return self.not_implemented_response(json.dumps(command.__dict__))
        except Exception as e:
            print("Exception:", e)
            traceback.print_exc()
            return web.Response(body=str(e), status=500)

    async def _delete_command_backchannel(self, request: web.Request):
        """
        Post a DELETE command to the agent.
        """
        command = None
        try:
            command = await self.parse_request(request)

            (resp_status, resp_text) = await self.make_agent_DELETE_request(command)

            if resp_status == 200:
                return web.Response(text=resp_text, status=resp_status)
            elif resp_status == 404:
                return self.not_found_response(json.dumps(command.__dict__))
            elif resp_status == 501:
                return self.not_implemented_response(json.dumps(command.__dict__))
            else:
                return web.Response(body=resp_text, status=resp_status)
        except NotImplementedError:
            return self.not_implemented_response(json.dumps(command.__dict__))
        except Exception as e:
            print("Exception:", e)
            traceback.print_exc()
            return web.Response(body=str(e), status=500)

    async def _get_response_backchannel(self, request: web.Request):
        """
        Get a response from the (remote) agent.
        """
        command = None
        try:
            command = await self.parse_request(request)
            (resp_status, resp_text) = await self.make_agent_GET_request_response(
                command
            )

            if resp_status == 200:
                return web.Response(text=resp_text, status=resp_status)
            elif resp_status == 404:
                return self.not_found_response(json.dumps(command.__dict__))
            elif resp_status == 501:
                return self.not_implemented_response(json.dumps(command.__dict__))
            else:
                return web.Response(body=resp_text, status=resp_status)
        except NotImplementedError:
            return self.not_implemented_response(json.dumps(command.__dict__))
        except Exception as e:
            print("Exception:", e)
            traceback.print_exc()
            return web.Response(body=str(e), status=500)

    async def make_agent_POST_request(
        self, command: BackchannelCommand
    ) -> Tuple[int, str]:
        """
        Override with agent-specific behaviour
        """
        raise NotImplementedError

    async def make_agent_DELETE_request(
        self, command: BackchannelCommand
    ) -> Tuple[int, str]:
        """
        Override with agent-specific behaviour
        """
        raise NotImplementedError

    async def make_agent_GET_request(
        self, command: BackchannelCommand
    ) -> Tuple[int, str]:
        """
        Override with agent-specific behaviour
        """
        raise NotImplementedError

    async def make_agent_GET_request_response(
        self, command: BackchannelCommand
    ) -> Tuple[int, str]:
        """
        Override with agent-specific behaviour
        """
        raise NotImplementedError

    def log(self, msg: str):
        print(msg)

    def handle_output(self, *output, source: str = None, **kwargs):
        end = "" if source else "\n"
        if source == "stderr":
            color = "fg:ansired"
        elif not source:
            color = self.color or "fg:ansiblue"
        else:
            color = None
        log_msg(*output, color=color, prefix=self.prefix_str, end=end, **kwargs)

    async def register_did(self, ledger_url: str = None, alias: str = None):
        ledger_url = get_ledger_url(ledger_url)
        data = {"alias": alias or self.ident, "seed": self.seed, "role": "TRUST_ANCHOR"}
        async with self.client_session.post(
            ledger_url + "/register", json=data
        ) as resp:
            if resp.status != 200:
                raise Exception(f"Error registering DID, response code {resp.status}")
            nym_info = await resp.json()
            self.did = nym_info["did"]
        self.log(f"Got DID: {self.did}")
