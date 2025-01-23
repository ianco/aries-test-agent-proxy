import asyncio
import functools
import json
import logging
import os
import signal
import subprocess
import sys
import tempfile
import yaml
from timeit import default_timer
from typing import Any, Dict, List, Mapping, Optional, Tuple, Union
from time import gmtime, strftime

from acapy.routes.agent_routes import routes as agent_routes
from acapy.routes.mediation_routes import get_mediation_record_by_connection_id
from acapy.routes.mediation_routes import routes as mediation_routes
from aiohttp import (ClientError, ClientRequest, ClientSession, ClientTimeout,
                     web)
from python.agent_backchannel import (RUN_MODE, START_TIMEOUT,
                                      AgentBackchannel, AgentPorts,
                                      BackchannelCommand, default_genesis_txns)
from python.storage import (get_resource, pop_resource, pop_resource_latest,
                            push_resource)
from python.utils import flatten, log_msg, output_reader, prompt_loop, str2bool
from typing_extensions import Literal

# from helpers.jsonmapper.json_mapper import JsonMapper

LOGGER = logging.getLogger(__name__)

MAX_TIMEOUT = 5

AGENT_NAME = os.getenv("AGENT_NAME", "Agent")

# AIP level is 10 or 20
AIP_CONFIG = int(os.getenv("AIP_CONFIG", "10"))

# backchannel-specific args
EXTRA_ARGS = os.getenv("EXTRA_ARGS")

# pipe output to console
PIPE_AGENT_OUTPUT = False
PIPE_OUTPUT_ARG = "PIPE_AGENT_OUTPUT"
PIPE_AGENT_OUTPUT = str2bool(os.getenv("PIPE_AGENT_OUTPUT", "False"))

# other configs ...
DEFAULT_BIN_PATH = "../venv/bin"
DEFAULT_PYTHON_PATH = ".."

if RUN_MODE == "docker":
    DEFAULT_BIN_PATH = "./bin"
    DEFAULT_PYTHON_PATH = "."
elif RUN_MODE == "pwd":
    DEFAULT_BIN_PATH = "./bin"
    DEFAULT_PYTHON_PATH = "."


def current_time():
    # just return GMT time for now
    return strftime("%Y-%m-%d %H:%M:%S", gmtime())


class AcaPyAgentBackchannel(AgentBackchannel):
    def __init__(
        self,
        ident: str,
        agent_ports: AgentPorts,
        genesis_data: str = None,
        params: dict = {},
        extra_args: dict = {},
    ):
        super().__init__(ident, agent_ports, genesis_data, params, extra_args)

        self.output_handler_futures = []

        # get aca-py version if available
        self.acapy_version = None
        try:
            with open("./acapy-version.txt", "r") as file:
                self.acapy_version = file.readline()
        except Exception:
            # ignore errors
            pass

        # set the acapy AIP version, defaulting to AIP10
        self.aip_version = "AIP10"

        # set the auto response/request flags
        self.auto_accept_requests = False
        self.auto_respond_messages = False
        self.auto_respond_credential_proposal = False
        self.auto_respond_credential_offer = False
        self.auto_respond_credential_request = False
        self.auto_respond_presentation_proposal = False
        self.auto_respond_presentation_request = False

        # Aca-py : RFC
        self.connectionStateTranslationDict = {
            "invitation": "invited",
            "request": "requested",
            "response": "responded",
            "active": "complete",
        }

        # Aca-py : RFC
        self.issueCredentialStateTranslationDict = {
            "proposal_sent": "proposal-sent",
            "proposal_received": "proposal-received",
            "offer_sent": "offer-sent",
            "offer_received": "offer-received",
            "request_sent": "request-sent",
            "request_received": "request-received",
            "credential_issued": "credential-issued",
            "credential_received": "credential-received",
            "credential_acked": "done",
            "deleted": "done",
        }

        # AATH API : Acapy Admin API
        self.issueCredentialv2OperationTranslationDict = {
            "send-proposal": "send-proposal",
            "send-offer": "send-offer",
            "create-offer": "create-offer",
            "send-request": "send-request",
            "issue": "issue",
            "store": "store",
        }

        # AATH API : Acapy Admin API
        self.proofv2OperationTranslationDict = {
            "send-presentation": "send-presentation",
            "send-request": "send-request",
            "create-request": "create-request",
            "verify-presentation": "verify-presentation",
            "send-proposal": "send-proposal",
        }

        # AATH API : Acapy Admin API
        self.TopicTranslationDict = {
            "issue-credential": "/issue-credential/",
            "issue-credential-v2": "/issue-credential-2.0/",
            "proof-v2": "/present-proof-2.0/",
        }

        self.credFormatFilterTranslationDict = {"indy": "indy", "json-ld": "ld_proof"}

        self.proofTypeKeyTypeTranslationDict = {
            "Ed25519Signature2018": "ed25519",
            "BbsBlsSignature2020": "bls12381g2",
        }

        # Aca-py : RFC
        self.presentProofStateTranslationDict = {
            "request_sent": "request-sent",
            "request_received": "request-received",
            "proposal_sent": "proposal-sent",
            "proposal_received": "proposal-received",
            "presentation_sent": "presentation-sent",
            "presentation_received": "presentation-received",
            "reject_sent": "reject-sent",
            "verified": "done",
            "presentation_acked": "done",
        }

        # Aca-py : RFC
        self.didExchangeResponderStateTranslationDict = {
            "initial": "invitation-sent",
            "invitation": "invitation-sent",
            "request": "request-received",
            "response": "response-sent",
            "?": "abandoned",
            "active": "completed",
            "completed": "completed",
        }

        # Aca-py : RFC
        self.didExchangeRequesterStateTranslationDict = {
            "initial": "invitation-sent",
            "invitation": "invitation-received",
            "request": "request-sent",
            "response": "response-received",
            "?": "abandoned",
            "active": "completed",
        }

    def get_acapy_version_as_float(self):
        # construct some number to compare to with > or < instead of listing out the version number
        # if it starts with zero strip it off
        # if it ends in alpha or RC (or "-<anything>"), change it to .1 or 1
        # strip all dots
        # Does that work if I'm testing 0.5.5.1 hot fix? Just strip off the .1 since there won't be a major change here.
        #
        # Update Nov 1, 2023: Acapy Versioning will no longer have a - in the rc version so 0.11.0-rc1 will come in as 0.11.0rc1, so we need to handle that.

        if not self.acapy_version or 0 == len(self.acapy_version):
            return 0.0

        comparibleVersion = self.acapy_version
        if comparibleVersion.startswith("0"):
            comparibleVersion = comparibleVersion[1:]
        if "." in comparibleVersion:
            comparibleVersion = comparibleVersion.replace(".", "")
        if "rc" in comparibleVersion:
            # This means its not an official release and came from Master/Main
            # replace with a .1 so that the number is higher than an official release
            comparibleVersion = comparibleVersion.split("rc")[0] + ".1"
        elif "-" in comparibleVersion:
            # This means its not an official release and came from Master/Main from an verson of the acapy repo before poetry.
            # replace with a .1 so that the number is higher than an official release
            comparibleVersion = comparibleVersion.split("-")[0] + ".1"

        return float(comparibleVersion)

    def get_agent_args(self):
        result = [
            ("--label", self.label),
            # "--auto-ping-connection",
            # "--auto-accept-invites",
            # "--auto-accept-requests",
            # "--auto-respond-messages",
            # "--auto-respond-credential-proposal",
            # "--auto-respond-credential-offer",
            # "--auto-respond-credential-request",
            # "--auto-respond-presentation-proposal",
            # "--auto-respond-presentation-request",
            ("--admin", "0.0.0.0", str(self.agent_ports["admin"])),
            "--admin-insecure-mode",
            "--public-invites",
            ("--wallet-type", self.wallet_type),
            ("--wallet-name", self.wallet_name),
            ("--wallet-key", self.wallet_key),
            "--monitor-revocation-notification",
            "--requests-through-public-did",
            "--notify-revocation",
            "--open-mediation",
            "--enable-undelivered-queue",
            "--preserve-exchange-records", # For AATH purposes, exchange records must be retained -- not typical in production
        ]

        # Backchannel needs to handle operations that may be called in the protocol by the tests
        # but if auto respond or auto accept request in on then the handlers will just return success
        if "--auto-accept-requests" in result:
            self.auto_accept_requests = True
        if "--auto-respond-messages" in result:
            self.auto_respond_messages = True
        if "--auto-respond-credential-proposal" in result:
            self.auto_respond_credential_proposal = True
        if "--auto-respond-credential-offer" in result:
            self.auto_respond_credential_offer = True
        if "--auto-respond-credential-request" in result:
            self.auto_respond_credential_request = True
        if "--auto-respond-presentation-proposal" in result:
            self.auto_respond_presentation_proposal = True
        if "--auto-respond-presentation-request" in result:
            self.auto_respond_presentation_request = True

        if self.get_acapy_version_as_float() > 56:
            result.append(("--auto-provision", "--recreate-wallet"))

        if self.genesis_data:
            result.append(("--genesis-transactions", self.genesis_data))
        if self.seed:
            result.append(("--seed", self.seed))
        if self.storage_type:
            result.append(("--storage-type", self.storage_type))
        if self.postgres:
            result.extend(
                [
                    ("--wallet-storage-type", "postgres_storage"),
                    ("--wallet-storage-config", json.dumps(self.postgres_config)),
                    ("--wallet-storage-creds", json.dumps(self.postgres_creds)),
                ]
            )
        if self.webhook_url:
            result.append(("--webhook-url", self.webhook_url))

        # This code for Tails Server is included here because aca-py does not support the env var directly yet.
        # when it does (and there is talk of supporting YAML) then this code can be removed.
        if os.getenv("TAILS_SERVER_URL") is not None:
            # if the env var is set for tails server then use that.
            result.append(("--tails-server-base-url", os.getenv("TAILS_SERVER_URL")))
        else:
            # if the tails server env is not set use the gov.bc TEST tails server.
            result.append(
                (
                    "--tails-server-base-url",
                    "https://tails-server-test.pathfinder.gov.bc.ca",
                )
            )

        if AIP_CONFIG >= 20 or os.getenv("EMIT_NEW_DIDCOMM_PREFIX") is not None:
            # if the env var is set for tails server then use that.
            result.append(("--emit-new-didcomm-prefix"))

        if AIP_CONFIG >= 20 or os.getenv("EMIT_NEW_DIDCOMM_MIME_TYPE") is not None:
            # if the env var is set for tails server then use that.
            result.append(("--emit-new-didcomm-mime-type"))

        result.append(("--universal-resolver"))

        # result.append(("--plugin", "redis_events.v1_0.redis_queue.events"))
        result.append(("--plugin-config", "/data-mount/plugin-config.yml"))
        
        # This code for log level is included here because aca-py does not support the env var directly yet.
        # when it does (and there is talk of supporting YAML) then this code can be removed.
        if os.getenv("LOG_LEVEL") is not None:
            result.append(("--log-level", os.getenv("LOG_LEVEL")))

        # aca-py supports a config.yaml file to pass in arguments. This env var point to such a file.
        if os.getenv("AGENT_CONFIG_FILE") is not None:
            # if the env var is set then use that.
            print(os.getenv("AGENT_CONFIG_FILE"))

            # Itterate over all of the items in the AGENT_CONFIG_FILE yaml, and if they already exist in the result list, then remove them.
            # Since commandline args take pressidence over config file args so this is to prevent the expectations of config file passed 
            # being overridded by the default args that the AATH ACA-Py Backchannel may setup.
            with open(os.getenv("AGENT_CONFIG_FILE"), 'r') as stream:
                try:
                    data = yaml.safe_load(stream)
                    for key, value in data.items():
                        item = "--" + key
                        # Check if item is in any tuple in result
                        if any(item in tup for tup in result if isinstance(tup, tuple)):
                            # Remove tuples containing the item
                            result = [tup for tup in result if item not in tup]
                except yaml.YAMLError as exc:
                    print(exc)
                
            result.append(("--arg-file", os.getenv("AGENT_CONFIG_FILE")))

        # result.append(("--trace", "--trace-target", "log", "--trace-tag", "acapy.events", "--trace-label", "acapy",))

        # if self.extra_args:
        #    result.extend(self.extra_args)

        return result

    def get_host_args(
        self,
        inbound_transports: List[Literal["ws", "http"]],
        outbound_transports: List[Literal["ws", "http"]],
    ) -> List[str]:
        args: List[str] = []

        for transport in inbound_transports:
            port = str(self.agent_ports[transport])
            endpoint = self.get_agent_endpoint(transport)

            args += [
                "--endpoint",
                endpoint,
                "--inbound-transport",
                transport,
                "0.0.0.0",
                port,
            ]

        for transport in outbound_transports:
            args += ["--outbound-transport", transport]

        return args

    async def listen_webhooks(self, webhook_port: int):
        self.webhook_port = webhook_port
        if RUN_MODE == "pwd":
            self.webhook_url = f"http://localhost:{str(webhook_port)}/webhooks"
        else:
            self.webhook_url = (
                f"http://{self.external_host}:{str(webhook_port)}/webhooks"
            )
        app = web.Application()
        app.add_routes([web.post("/webhooks/topic/{topic}/", self._receive_webhook)])
        runner = web.AppRunner(app)
        await runner.setup()
        self.webhook_site = web.TCPSite(runner, "0.0.0.0", webhook_port)
        await self.webhook_site.start()
        print("Listening to web_hooks on port", webhook_port)

    async def _receive_webhook(self, request: ClientRequest):
        topic = request.match_info["topic"]
        payload = await request.json()
        await self.handle_webhook(topic, payload)
        # TODO web hooks don't require a response???
        return web.Response(text="")

    async def handle_webhook(self, topic: str, payload):
        if topic != "webhook":  # would recurse
            # Some topics use dashes instead of underscores
            handler_topic = topic.replace("-", "_")
            handler = f"handle_{handler_topic}"

            method = getattr(self, handler, None)
            # put a log message here
            log_msg("Passing webhook payload to handler " + handler)
            if method:
                await method(payload)
            else:
                log_msg(
                    f"Error: agent {self.ident} "
                    f"has no method {handler} "
                    f"to handle webhook on topic {topic}"
                )
        else:
            log_msg(
                "in webhook, topic is: " + topic + " payload is: " + json.dumps(payload, indent=4)
            )

    async def handle_connections(self, message: Mapping[str, Any]):
        if "request_id" in message:
            # This is a did-exchange message based on a Public DID non-invitation
            request_id = message["request_id"]
            push_resource(request_id, "didexchange-msg", message)
        elif message["connection_protocol"] == "didexchange/1.0" or message["connection_protocol"] == "didexchange/1.1":
            # This is an did-exchange message based on a Non-Public DID invitation
            invitation_id = message["invitation_msg_id"]
            push_resource(invitation_id, "didexchange-msg", message)
        elif message["connection_protocol"] == "connections/1.0":
            connection_id = message["connection_id"]
            push_resource(connection_id, "connection-msg", message)
        else:
            raise Exception(
                f"Unknown message type in Connections Webhook: {json.dumps(message)}"
            )
        log_msg("Received a Connection Webhook message: " + json.dumps(message, indent=4))

    async def handle_revocation_notification(self, message: Mapping[str, Any]):
        log_msg(
            "Received a Revocation Notification Webhook message: " + json.dumps(message, indent=4)
        )

        thread_id = message["thread_id"]

        # thread_id = indy::{rev_reg_id}::{cred_rev_id}
        push_resource(thread_id, "revocation-notification-msg", message)

    async def handle_issue_credential(self, message: Mapping[str, Any]):
        log_msg("Received Issue Credential Webhook message: " + json.dumps(message, indent=4))
        thread_id = message["thread_id"]
        if "state" in message and message["state"] == "deleted":
            # ignore "deleted" state
            return
        push_resource(thread_id, "credential-msg", message)
        if "revocation_id" in message:  # also push as a revocation message
            push_resource(thread_id, "revocation-registry-msg", message)
            log_msg("Issue Credential Webhook message contains revocation info")

    async def handle_issue_credential_v2_0(self, message: Mapping[str, Any]):
        log_msg("Received Issue Credential v2 Webhook message: " + json.dumps(message, indent=4))
        thread_id = message["thread_id"]
        if "state" in message and message["state"] == "deleted":
            # ignore "deleted" state
            return
        push_resource(thread_id, "credential-msg", message)
        if "revocation_id" in message:  # also push as a revocation message
            push_resource(thread_id, "revocation-registry-msg", message)
            log_msg("Issue Credential Webhook message contains revocation info")

    async def handle_present_proof_v2_0(self, message: Mapping[str, Any]):
        log_msg("Received a Present Proof v2 Webhook message: " + json.dumps(message, indent=4))
        thread_id = message["thread_id"]
        if "state" in message and message["state"] == "deleted":
            # ignore "deleted" state
            return
        push_resource(thread_id, "presentation-msg", message)

    async def handle_present_proof(self, message: Mapping[str, Any]):
        log_msg("Received a Present Proof Webhook message: " + json.dumps(message, indent=4))
        thread_id = message["thread_id"]
        if "state" in message and message["state"] == "deleted":
            # ignore "deleted" state
            return
        push_resource(thread_id, "presentation-msg", message)

    async def handle_revocation_registry(self, message: Mapping[str, Any]):
        # No thread id in the webhook for revocation registry messages
        cred_def_id = message["cred_def_id"]
        push_resource(cred_def_id, "revocation-registry-msg", message)
        log_msg("Received Revocation Registry Webhook message: " + json.dumps(message, indent=4))

    # TODO Handle handle_issuer_cred_rev (this must be newer than the revocation tests?)
    # TODO Handle handle_issue_credential_v2_0_indy

    # handle_oob_invitation may not be needed anymore. We are seeing handle_out_of_band error messages in the logs, so maybe at some point it was changed.
    async def handle_oob_invitation(self, message: Mapping[str, Any]):
        # No thread id in the webhook for revocation registry messages
        invitation_id = message["invitation_id"]
        push_resource(invitation_id, "oob-inviation-msg", message)
        log_msg(
            "Received Out of Band Invitation Webhook message: " + json.dumps(message, indent=4)
        )

    async def handle_out_of_band(self, message: Mapping[str, Any]):
        log_msg(
            "Received Out of Band Webhook message: " + json.dumps(message, indent=4)
        )
        #invitation_id = message["invitation_msg_id"]
        invitation_id = message["invi_msg_id"]
        push_resource(invitation_id, "out-of-band-msg", message)

    async def handle_problem_report(self, message: Mapping[str, Any]):
        thread_id = message["thread_id"]
        push_resource(thread_id, "problem-report-msg", message)
        log_msg("Received Problem Report Webhook message: " + json.dumps(message, indent=4))

    async def swap_thread_id_for_exchange_id(
        self,
        thread_id: str,
        data_type: str,
        id_txt: str,
        wait_time: Optional[int] = 20,
        sleep_time: Optional[int] = 1,
    ) -> str:
        timeout = 0
        ex_id = None
        webcall_returned = None
        while webcall_returned is None and timeout <= wait_time:
            msg = get_resource(thread_id, data_type)
            try:
                ex_id = msg[0][id_txt]
                webcall_returned = True
            except TypeError:
                await asyncio.sleep(sleep_time)
                timeout += sleep_time
        if timeout >= wait_time:
            raise TimeoutError(
                "Timeout waiting for web callback to retrieve the thread id based on the exchange id"
            )
        return ex_id

    async def expected_agent_state(
        self,
        path: str,
        status_txt: Union[str, List[str]],
        wait_time: float = 2.0,
        sleep_time: float = 0.5,
    ):
        await asyncio.sleep(sleep_time)
        state = "None"
        if type(status_txt) != list:
            status_txt = [status_txt]
        for i in range(int(wait_time / sleep_time)):
            (resp_status, resp_text) = await self.make_admin_request("GET", path)
            if resp_status == 200:
                resp_json = json.loads(resp_text)
                state = resp_json["state"]
                if state in status_txt:
                    return True
            await asyncio.sleep(sleep_time)
        print(
            "Expected state",
            status_txt,
            "but received",
            state,
            ", with a response status of",
            resp_status,
        )
        return False

    async def make_admin_request(
        self,
        method: str,
        path: str,
        data: Optional[Any] = None,
        params: Optional[Mapping[str, Any]] = None,
    ) -> Tuple[int, str]:
        params = {k: v for (k, v) in (params or {}).items() if v is not None}
        async with self.client_session.request(
            method, self.admin_url + path, json=data, params=params
        ) as resp:
            resp_status = resp.status
            resp_text = await resp.text()
            return (resp_status, resp_text)

    async def admin_GET(
        self, path: str, params: Optional[Mapping[str, Any]] = None
    ) -> Tuple[int, str]:
        try:
            return await self.make_admin_request("GET", path, None, params)
        except ClientError as e:
            self.log(f"Error during GET {path}: {str(e)}")
            raise

    async def admin_DELETE(
        self, path: str, params: Optional[Mapping[str, Any]] = None
    ) -> Tuple[int, str]:
        try:
            return await self.make_admin_request("DELETE", path, None, params)
        except ClientError as e:
            self.log(f"Error during DELETE {path}: {str(e)}")
            raise

    async def admin_POST(
        self,
        path: str,
        data: Optional[Any] = None,
        params: Optional[Mapping[str, Any]] = None,
    ) -> Tuple[int, str]:
        try:
            return await self.make_admin_request("POST", path, data, params)
        except ClientError as e:
            self.log(f"Error during POST {path}: {str(e)}")
            raise

    async def make_agent_POST_request(
        self, command: BackchannelCommand
    ) -> Tuple[int, str]:
        data = command.data

        if command.topic == "connection":
            # If mediator_connection_id is included we should use that as the mediator for this connection
            mediation_id = None
            if (
                data
                and "mediator_connection_id" in data
                and data["mediator_connection_id"] != None
            ):
                mediation_record = await get_mediation_record_by_connection_id(
                    self, data["mediator_connection_id"]
                )
                mediation_id = mediation_record["mediation_id"]

            operation = command.operation
            if operation == "create-invitation":
                agent_operation = f"/connections/{operation}"

                post_data = {}

                if mediation_id:
                    post_data["mediation_id"] = mediation_id

                (resp_status, resp_text) = await self.admin_POST(
                    agent_operation, data=post_data
                )

                # extract invitation from the agent's response
                invitation_resp = json.loads(resp_text)
                resp_text = json.dumps(invitation_resp)

                if resp_status == 200:
                    resp_text = self.agent_state_translation(command.topic, resp_text)
                return (resp_status, resp_text)

            elif operation == "receive-invitation":
                agent_operation = "/connections/" + operation

                if mediation_id:
                    agent_operation += f"?mediation_id={mediation_id}"

                (resp_status, resp_text) = await self.admin_POST(
                    agent_operation, data=data
                )
                if resp_status == 200:
                    resp_text = self.agent_state_translation(command.topic, resp_text)
                return (resp_status, resp_text)

            elif (
                operation == "accept-invitation"
                or operation == "accept-request"
                or operation == "remove"
                or operation == "start-introduction"
                or operation == "send-ping"
            ):
                connection_id = command.record_id

                # wait for the connection to be in "requested" status
                if operation == "accept-request":
                    if not self.auto_accept_requests:
                        if not await self.expected_agent_state(
                            f"/connections/{connection_id}", "request", wait_time=60.0
                        ):
                            raise Exception("Expected state request but not received")

                agent_operation = f"/connections/{connection_id}/{operation}"
                log_msg("POST Request: ", agent_operation, json.dumps(command.data, indent=4))

                if self.auto_accept_requests and operation == "accept-request":
                    resp_status = 200
                    resp_text = "Aca-py agent in auto accept request mode. accept-request operation not called."
                else:
                    # As of adding the Auto Accept and Auto Respond support, it seems a sleep is required here,
                    # or sometimes the agent isn't in the correct state to accept the operation. Not sure why...
                    await asyncio.sleep(1)
                    (resp_status, resp_text) = await self.admin_POST(
                        agent_operation, command.data
                    )
                    if resp_status == 200:
                        resp_text = self.agent_state_translation(
                            command.topic, resp_text
                        )

                log_msg(resp_status, json.dumps(resp_text, indent=4))
                return (resp_status, resp_text)

        elif command.topic == "schema":
            # POST operation is to create a new schema
            if command.anoncreds:
                schema_name = data['schema'].get("name")
                schema_version = data['schema'].get("version")
                schema_get_endpoint = '/anoncreds/schemas'
                schema_post_endpoint = '/anoncreds/schema'
            else:
                schema_name = data.get("schema_name")
                schema_version = data.get("schema_version")
                schema_get_endpoint = '/schemas/created'
                schema_post_endpoint = '/schemas'

            # Check if schema id already exists
            log_msg(schema_post_endpoint, data)

            (resp_status, resp_text) = await self.admin_GET(
                schema_get_endpoint,
                params={"schema_version": schema_version, "schema_name": schema_name},
            )
            resp_json = json.loads(resp_text)
            if len(resp_json["schema_ids"]) > 0:
                schema_id = resp_json["schema_ids"][0]
                return (200, json.dumps({"schema_id": schema_id}))

            (resp_status, resp_text) = await self.admin_POST(
                schema_post_endpoint, data
            )

            log_msg(resp_status, json.dumps(resp_text, indent=4))
            resp_text = self.move_field_to_top_level(resp_text, "schema_id")
            return (resp_status, resp_text)

        elif command.topic == "credential-definition":
            # POST operation is to create a new cred def
            if command.anoncreds:
                schema_id = data['credential_definition'].get("schemaId")
                tag = data['credential_definition'].get("tag")
                cred_defs_get_endpoint = '/anoncreds/credential-definitions'
                cred_defs_post_endpoint = '/anoncreds/credential-definition'
            else:
                tag = data.get("tag")
                schema_id = data.get("schema_id")
                cred_defs_get_endpoint = '/credential-definitions/created'
                cred_defs_post_endpoint = '/credential-definitions'

            agent_operation = "/credential-definitions"
            log_msg(agent_operation, json.dumps(command.data, indent=4))

            # Check if credential definition id already exists
            (resp_status, resp_text) = await self.admin_GET(
                cred_defs_get_endpoint,
                params={
                    "schema_id": schema_id,
                },
            )
            resp_json = json.loads(resp_text)
            if len(resp_json["credential_definition_ids"]) > 0:
                # need to check the 'tag' value
                for cred_def_id in resp_json["credential_definition_ids"]:
                    cred_def_id_parts = cred_def_id.split(":")
                    if tag == cred_def_id_parts[4]:
                        return (
                            200,
                            json.dumps({"credential_definition_id": cred_def_id}),
                        )

            (resp_status, resp_text) = await self.admin_POST(
                cred_defs_post_endpoint, data
            )

            log_msg(resp_status, json.dumps(resp_text, indent=4))
            resp_text = self.move_field_to_top_level(
                resp_text, "credential_definition_id"
            )
            return (resp_status, resp_text)

        elif command.topic == "issue-credential":
            operation = command.operation
            data = command.data

            acapy_topic = "/issue-credential/"

            if (
                self.auto_respond_credential_proposal
                and operation == "send-offer"
                and command.record_id
            ):
                resp_status = 200
                resp_text = '{"message": "Aca-py agent in auto respond mode for proposal. send-offer operation not called."}'
                return (resp_status, resp_text)
            elif self.auto_respond_credential_offer and operation == "send-request":
                resp_status = 200
                resp_text = '{"message": "Aca-py agent in auto respond mode for offer. send-request operation not called."}'
                return (resp_status, resp_text)
            elif self.auto_respond_credential_request and operation == "issue":
                resp_status = 200
                resp_text = '{"message": "Aca-py agent in auto respond mode for request. issue operation not called."}'
                return (resp_status, resp_text)
            else:
                if command.record_id is None:
                    agent_operation = acapy_topic + operation
                else:
                    if (
                        operation == "send-offer"
                        or operation == "send-request"
                        or operation == "issue"
                        or operation == "store"
                    ):

                        # swap thread id for cred ex id from the webhook
                        cred_ex_id = await self.swap_thread_id_for_exchange_id(
                            command.record_id,
                            "credential-msg",
                            "credential_exchange_id",
                        )
                        agent_operation = (
                            f"{acapy_topic}records/{cred_ex_id}/{operation}"
                        )

                        # wait for the issue cred to be in "request-received" status
                        if (
                            operation == "issue"
                            and not self.auto_respond_credential_request
                        ):
                            if not await self.expected_agent_state(
                                f"{acapy_topic}records/{cred_ex_id}",
                                "request_received",
                                wait_time=60.0,
                            ):
                                raise Exception(
                                    "Expected state request-received but not received"
                                )

                    # Make Special provisions for revoke since it is passing multiple query params not just one id.
                    elif operation == "revoke":
                        cred_rev_id = command.record_id
                        rev_reg_id = data["rev_registry_id"]
                        publish = data["publish_immediately"]
                        notify_connection_id = data.get("notify_connection_id")
                        agent_operation = (
                            f"{acapy_topic}{operation}"
                            f"?cred_rev_id={cred_rev_id}"
                            f"&rev_reg_id={rev_reg_id}"
                            f"&publish={str(publish).lower()}"
                        )

                        # If notify connection id is present, notify the holder
                        if notify_connection_id:
                            agent_operation += (
                                "&notify=true&connection_id={notify_connection_id}"
                            )
                        data = None
                    else:
                        agent_operation = acapy_topic + operation

                log_msg(agent_operation, json.dumps(data, indent=4))

                # As of adding the Auto Accept and Auto Respond support and not taking time to check interim states
                # it seems a sleep is required here,
                # or sometimes the agent isn't in the correct state to accept the operation. Not sure why...
                await asyncio.sleep(1)
                (resp_status, resp_text) = await self.admin_POST(agent_operation, data)

                log_msg(resp_status, json.dumps(resp_text, indent=4))
                if resp_status == 200 and self.aip_version != "AIP20":
                    resp_text = self.agent_state_translation(command.topic, resp_text)

                if operation == "create-offer":
                    resp_json = json.loads(resp_text)
                    resp_text = json.dumps(
                        {
                            "record": resp_json,
                            "message": resp_json["credential_offer_dict"],
                        }
                    )
                return (resp_status, resp_text)

        # Handle issue credential v2 POST operations
        elif command.topic == "issue-credential-v2":
            (resp_status, resp_text) = await self.handle_issue_credential_v2_POST(
                command
            )
            return (resp_status, resp_text)

        # Handle proof v2 POST operations
        elif command.topic == "proof-v2":
            (resp_status, resp_text) = await self.handle_proof_v2_POST(command)
            return (resp_status, resp_text)

        elif command.topic == "revocation":
            # set the acapyversion to master since work to set it is not complete. Remove when master report proper version
            # self.acapy_version = "0.5.5-RC"
            operation = command.operation
            (
                agent_operation,
                admin_data,
            ) = await self.get_agent_operation_acapy_version_based(command)

            log_msg(agent_operation, json.dumps(admin_data, indent=4))

            if admin_data is None:
                (resp_status, resp_text) = await self.admin_POST(agent_operation)
            else:
                (resp_status, resp_text) = await self.admin_POST(
                    agent_operation, admin_data
                )

            log_msg(resp_status, json.dumps(resp_text, indent=4))
            if resp_status == 200:
                resp_text = self.agent_state_translation(command.topic, resp_text)
            return (resp_status, resp_text)

        elif command.topic == "proof":
            operation = command.operation
            record_id = command.record_id
            data = command.data

            if (
                self.auto_respond_presentation_proposal
                and operation == "send-request"
                and record_id
            ):
                resp_status = 200
                resp_text = '{"message": "Aca-py agent in auto respond mode for presentation proposal. send-request operation not called."}'
                log_msg(
                    "Aca-py agent in auto respond mode for presentation proposal. send-request operation not called."
                )
                return (resp_status, resp_text)
            elif (
                self.auto_respond_presentation_request
                and operation == "send-presentation"
            ):
                resp_status = 200
                resp_text = '{"message": "Aca-py agent in auto respond mode for presentation request. send-presentation operation not called."}'
                log_msg(
                    "Aca-py agent in auto respond mode for presentation request. send-presentation operation not called."
                )
                return (resp_status, resp_text)
            else:
                if record_id is None:
                    agent_operation = f"/present-proof/{operation}"
                else:
                    if (
                        operation == "send-presentation"
                        or operation == "send-request"
                        or operation == "verify-presentation"
                        or operation == "remove"
                    ):

                        # swap thread id for pres ex id from the webhook
                        pres_ex_id = await self.swap_thread_id_for_exchange_id(
                            record_id,
                            "presentation-msg",
                            "presentation_exchange_id",
                        )
                        agent_operation = (
                            f"/present-proof/records/{pres_ex_id}/{operation}"
                        )

                        # wait for the proof to be in "presentation-received" status
                        if (
                            operation == "verify-presentation"
                            and not self.auto_respond_presentation_request
                        ):
                            if not await self.expected_agent_state(
                                f"/present-proof/records/{pres_ex_id}",
                                "presentation_received",
                                wait_time=60.0,
                            ):
                                raise Exception(
                                    "Expected state presentation-received but not received"
                                )

                    else:
                        agent_operation = f"/present-proof/{operation}"

                log_msg(agent_operation, json.dumps(data, indent=4))

                if data is not None:
                    # Format the message data that came from the test, to what the Aca-py admin api expects.
                    data = self.map_test_json_to_admin_api_json(
                        command.topic, operation, data
                    )

                # As of adding the Auto Accept and Auto Respond support and not taking time to check interim states
                # it seems a sleep is required here,
                # or sometimes the agent isn't in the correct state to accept the operation. Not sure why...
                await asyncio.sleep(1)
                (resp_status, resp_text) = await self.admin_POST(agent_operation, data)

                log_msg(resp_status, json.dumps(resp_text, indent=4))
                if resp_status == 200:
                    resp_text = self.agent_state_translation(command.topic, resp_text)

                if operation == "create-request":
                    resp_json = json.loads(resp_text)
                    if resp_status == 200:
                        resp_text = json.dumps(
                            {
                                "record": resp_json,
                                "message": resp_json["presentation_request_dict"],
                            }
                        )
                return (resp_status, resp_text)

        # Handle out of band POST operations
        elif command.topic == "out-of-band":
            (resp_status, resp_text) = await self.handle_out_of_band_POST(command)
            return (resp_status, resp_text)

        # Handle did exchange POST operations
        elif command.topic == "did-exchange":
            (resp_status, resp_text) = await self.handle_did_exchange_POST(command)
            return (resp_status, resp_text)

        return (501, "501: Not Implemented\n\n")

    async def handle_out_of_band_POST(self, command: BackchannelCommand):
        operation = command.operation
        data = command.data

        agent_operation = "/out-of-band/"
        log_msg(
            f"Data passed to backchannel by test for operation: {agent_operation}", json.dumps(data, indent=4)
        )

        # If mediator_connection_id is included we should use that as the mediator for this connection
        mediation_id = None
        if "mediator_connection_id" in data and data["mediator_connection_id"] != None:
            mediation_record = await get_mediation_record_by_connection_id(
                self, data["mediator_connection_id"]
            )
            mediation_id = mediation_record["mediation_id"]

        if operation == "send-invitation-message":
            # http://localhost:8022/out-of-band/create-invitation?auto_accept=false&multi_use=false
            # TODO Check the data for auto_accept and multi_use. If it exists use those values then pop them out, otherwise false.
            auto_accept = "false"
            multi_use = "false"
            agent_operation = (
                agent_operation + "create-invitation" + "?multi_use=" + multi_use
            )

            attachments = data.get("attachments", [])
            handshake_protocols = data.get("handshake_protocols", None)
            formatted_attachments = []
            use_did_method = data.get("use_did_method", None)
            use_did = data.get("use_did", None)

            for attachment in attachments:
                message_type = attachment["@type"]
                thread_id = attachment.get("~thread", {}).get("thid") or attachment.get(
                    "@id"
                )
                if message_type.endswith("/issue-credential/1.0/offer-credential"):
                    (_, resp_text) = await self.admin_GET(
                        "/issue-credential/records", params={"thread_id": thread_id}
                    )
                    resp_json = json.loads(resp_text)
                    record_id = resp_json["results"][0]["credential_exchange_id"]
                    record_type = "credential-offer"
                elif message_type.endswith("/issue-credential/2.0/offer-credential"):
                    (_, resp_text) = await self.admin_GET(
                        "/issue-credential-2.0/records", params={"thread_id": thread_id}
                    )
                    resp_json = json.loads(resp_text)
                    record_id = resp_json["results"][0]["cred_ex_record"]["cred_ex_id"]
                    record_type = "credential-offer"
                elif message_type.endswith("present-proof/1.0/request-presentation"):
                    (_, resp_text) = await self.admin_GET(
                        "/present-proof/records", params={"thread_id": thread_id}
                    )
                    resp_json = json.loads(resp_text)
                    record_id = resp_json["results"][0]["presentation_exchange_id"]
                    record_type = "present-proof"
                elif message_type.endswith("present-proof/2.0/request-presentation"):
                    (_, resp_text) = await self.admin_GET(
                        "/present-proof-2.0/records", params={"thread_id": thread_id}
                    )
                    resp_json = json.loads(resp_text)
                    record_id = resp_json["results"][0]["pres_ex_id"]
                    record_type = "present-proof"
                else:
                    return (500, f"Unsupported message type '{message_type}'")

                formatted_attachments.append({"id": record_id, "type": record_type})

            # Add handshake protocols to message body
            data = {
                "use_public_did": data.get("use_public_did", False),
                "attachments": formatted_attachments,
            }

            # If no handshake_protocols is provided and no formatted attachments we use didexchange handshake protocol
            # by default. This is a legacy need because at first it was always assumed we use handshake_protocols with didexchange
            if handshake_protocols == None and not formatted_attachments:
                data["handshake_protocols"] = [
                    "did:sov:BzCbsNYhMrjHiqZDTUASHg;spec/didexchange/1.0"
                ]
            else:
                data["handshake_protocols"] = handshake_protocols or []

            if use_did_method:
                data["use_did_method"] = use_did_method

            if use_did:
                data["use_did"] = use_did

            # If mediator_connection_id is included we should use that as the mediator for this connection
            if mediation_id:
                data["mediation_id"] = mediation_id

        elif operation == "receive-invitation":
            # TODO check for Alias and Auto_accept in data to add to the call (works without for now)
            if "use_existing_connection" in data:
                use_existing_connection = str(data["use_existing_connection"]).lower()
                data.pop("use_existing_connection")
            else:
                use_existing_connection = "false"
            auto_accept = "false"
            agent_operation = (
                agent_operation
                + "receive-invitation"
                + "?use_existing_connection="
                + use_existing_connection
            )

            if mediation_id:
                agent_operation += f"&mediation_id={mediation_id}"

        log_msg(
            f"Data translated by backchannel to send to agent for operation: {agent_operation}",
            json.dumps(data, indent=4)
        )

        (resp_status, resp_text) = await self.admin_POST(agent_operation, data)

        # TODO: this now returns an oob record. If connection_id is present fetch the
        # connection and return that. Otherwise return state "invitation-received"
        log_msg(resp_status, json.dumps(resp_text, indent=4))
        if resp_status == 200 and operation == "receive-invitation":
            # AATH expects DIDExchange state instead of actual OOB state... :(
            resp_json = json.loads(resp_text)
            connection_id = resp_json.get("connection_id")
            state = resp_json.get("state")

            # If connection exists return the actual connection
            if connection_id:
                (resp_status, resp_text) = await self.admin_GET(
                    f"/connections/{connection_id}"
                )
                resp_text = self.agent_state_translation(command.topic, resp_text)
            elif state == "prepare-response":
                resp_json["state"] = "invitation-received"
                resp_text = json.dumps(resp_json)
        elif resp_status == 200:
            resp_text = self.agent_state_translation(command.topic, resp_text)
        return (resp_status, resp_text)

    async def handle_did_exchange_POST(self, command: BackchannelCommand):
        operation = command.operation
        data = command.data
        record_id = command.record_id

        agent_operation = "/didexchange/"
        if operation == "send-request":
            agent_operation = f"{agent_operation}{record_id}/accept-invitation"

        elif operation == "receive-invitation":
            agent_operation = agent_operation + operation

        elif operation == "send-response":
            if self.auto_accept_requests:
                resp_status = 200
                resp_text = "Aca-py agent in auto accept request mode. accept-request operation not called."
                return (resp_status, resp_text)
            else:
                agent_operation = f"{agent_operation}{record_id}/accept-request"
                await asyncio.sleep(1)

        elif operation == "create-request-resolvable-did":
            their_public_did = data["their_public_did"]
            agent_operation = (
                f"{agent_operation}create-request?their_public_did={their_public_did}"
            )
            data = None

        elif operation == "receive-request-resolvable-did":
            # as of PR 1182 in aries-cloudagent-python receive-request is no longer needed.
            # this is done automatically by the responder.
            # The test expects a connection_id returned so, return the last webhook message
            # agent_operation = agent_operation + "receive-request"

            (wh_status, wh_text) = await self.make_agent_GET_request_response(
                command, message_name="didexchange-msg"
            )
            return (wh_status, wh_text)

        # If data is not none and contains use_did_method, add it to the agent operation
        if data and "use_did_method" in data:
            agent_operation += f"?use_did_method={data['use_did_method']}"
            data.pop("use_did_method")

        (resp_status, resp_text) = await self.admin_POST(agent_operation, data)
        if resp_status == 200:
            resp_text = self.agent_state_translation(command.topic, resp_text)
        return (resp_status, resp_text)

    async def handle_issue_credential_v2_POST(self, command: BackchannelCommand):
        operation = command.operation
        topic = command.topic
        record_id = command.record_id
        data = command.data

        if (
            self.auto_respond_credential_proposal
            and operation == "send-offer"
            and record_id
        ):
            resp_status = 200
            resp_text = '{"message": "Aca-py agent in auto respond mode for proposal. send-offer operation not called."}'
            return (resp_status, resp_text)
        elif self.auto_respond_credential_offer and operation == "send-request":
            resp_status = 200
            resp_text = '{"message": "Aca-py agent in auto respond mode for offer. send-request operation not called."}'
            return (resp_status, resp_text)
        elif self.auto_respond_credential_request and operation == "issue":
            resp_status = 200
            resp_text = '{"message": "Aca-py agent in auto respond mode for request. issue operation not called."}'
            return (resp_status, resp_text)
        else:
            if operation == "prepare-json-ld":
                key_type = self.proofTypeKeyTypeTranslationDict[data["proof_type"]]
                did_method = data["did_method"]

                params = {"method": did_method, "key_type": key_type}

                # If did method is sov, we want to only look for public did
                if did_method == "sov":
                    params["posture"] = "public"

                # Retrieve matching dids
                resp_status, resp_text = await self.admin_GET(
                    "/wallet/did",
                    params=params,
                )

                did = None
                if resp_status == 200:
                    resp_json = json.loads(resp_text)

                    # If there is a matching did use it
                    if len(resp_json["results"]) > 0:
                        # Get first matching did
                        did = resp_json["results"][0]["did"]

                # If there was no matching did create a new one
                # Can't do this for did:sov like this.
                if not did and did_method != "sov":
                    (resp_status, resp_text) = await self.admin_POST(
                        "/wallet/did/create",
                        {
                            "method": did_method,
                            "options": {"key_type": key_type},
                        },
                    )
                    if resp_status == 200:
                        resp_json = json.loads(resp_text)
                        did = resp_json["result"]["did"]

                if did:
                    # prepend did:method to did if not already
                    # ACA-Py doesn't include did:sov prefix for sov dids
                    if not did.startswith(f"did:{did_method}"):
                        did = f"did:{did_method}:{did}"

                    resp_text = json.dumps({"did": did})

                    log_msg(resp_status, json.dumps(resp_text, indent=4))
                    return (resp_status, resp_text)
                else:
                    return (500, "Unable to create did")

            if record_id is None:
                agent_operation = (
                    self.TopicTranslationDict[topic]
                    + self.issueCredentialv2OperationTranslationDict[operation]
                )
            else:
                # swap thread id for cred ex id from the webhook
                cred_ex_id = await self.swap_thread_id_for_exchange_id(
                    record_id, "credential-msg", "cred_ex_id"
                )
                agent_operation = f"{self.TopicTranslationDict[topic]}records/{cred_ex_id}/{self.issueCredentialv2OperationTranslationDict[operation]}"

            # Map AATH filter keys to ACA-Py filter keys
            # e.g. data.filters.json-ld becomes data.filters.ld_proof
            if data and "filter" in data:
                data["filter"] = dict(
                    (self.credFormatFilterTranslationDict[name], val)
                    for name, val in data["filter"].items()
                )

            log_msg(agent_operation, json.dumps(data, indent=4))
            await asyncio.sleep(1)
            (resp_status, resp_text) = await self.admin_POST(agent_operation, data)

            if operation == "store":
                resp_json = json.loads(resp_text)

                if resp_json["ld_proof"]:
                    resp_json["json-ld"] = resp_json.pop("ld_proof")

                # Return less ACA-Py specific credential identifier key
                for key in resp_json:
                    if resp_json[key] and resp_json[key].get("cred_id_stored"):
                        resp_json[key]["credential_id"] = resp_json[key].get(
                            "cred_id_stored"
                        )

                resp_text = json.dumps(resp_json)

            log_msg(resp_status, json.dumps(resp_text, indent=4))
            resp_text = self.move_field_to_top_level(resp_text, "state")

            if operation == "create-offer":
                resp_json = json.loads(resp_text)
                resp_text = json.dumps(
                    {"record": resp_json, "message": resp_json["cred_offer"]}
                )
            return (resp_status, resp_text)

    async def handle_proof_v2_POST(self, command: BackchannelCommand):
        operation = command.operation
        topic = command.topic
        record_id = command.record_id
        data = command.data

        if (
            self.auto_respond_presentation_proposal
            and operation == "send-request"
            and record_id
        ):
            resp_status = 200
            resp_text = '{"message": "Aca-py agent in auto respond mode for presentation proposal. send-request operation not called."}'
            log_msg(
                "Aca-py agent in auto respond mode for presentation proposal. send-request operation not called."
            )
            return (resp_status, resp_text)
        elif (
            self.auto_respond_presentation_request and operation == "send-presentation"
        ):
            resp_status = 200
            resp_text = '{"message": "Aca-py agent in auto respond mode for presentation request. send-presentation operation not called."}'
            log_msg(
                "Aca-py agent in auto respond mode for presentation request. send-presentation operation not called."
            )
            return (resp_status, resp_text)
        else:
            if record_id is None:
                agent_operation = (
                    self.TopicTranslationDict[topic]
                    + self.proofv2OperationTranslationDict[operation]
                )
            else:
                # swap thread id for cred ex id from the webhook
                pres_ex_id = await self.swap_thread_id_for_exchange_id(
                    record_id, "presentation-msg", "pres_ex_id"
                )
                agent_operation = (
                    self.TopicTranslationDict[topic]
                    + "records/"
                    + pres_ex_id
                    + "/"
                    + self.proofv2OperationTranslationDict[operation]
                )

            log_msg(
                f"Data passed to backchannel by test for operation: {agent_operation}",
                json.dumps(data, indent=4),
            )
            if data is not None:
                # Format the message data that came from the test, to what the Aca-py admin api expects.
                data = self.map_test_json_to_admin_api_json("proof-v2", operation, data)
            log_msg(
                f"Data translated by backchannel to send to agent for operation: {agent_operation}",
                json.dumps(data, indent=4),
            )
            await asyncio.sleep(1)
            (resp_status, resp_text) = await self.admin_POST(agent_operation, data)

            if operation == "create-request":
                resp_json = json.loads(resp_text)
                resp_text = json.dumps(
                    {"record": resp_json, "message": resp_json["pres_request"]}
                )

            log_msg(resp_status, json.dumps(resp_text, indent=4))
            resp_text = self.move_field_to_top_level(resp_text, "state")
            return (resp_status, resp_text)

    def move_field_to_top_level(self, resp_text: str, field_to_move: str):
        # Some responses have been changed to nest fields that were once at top level.
        # The Test harness expects the these fields to be at the root. Other agents have it at the root.
        # This could be removed if it is common across agents to nest these fields in `sent:` for instance.
        resp_json = json.loads(resp_text)
        if field_to_move in resp_json:
            # If it is already a top level field, forget about it.
            return resp_text
        else:
            # Find the field and put a copy as a top level
            for key in resp_json:
                if field_to_move in resp_json[key]:
                    field_value = resp_json[key][field_to_move]
                    resp_json[field_to_move] = field_value
                    return json.dumps(resp_json)

        return resp_text

    async def make_agent_GET_request(
        self, command: BackchannelCommand
    ) -> Tuple[int, str]:
        record_id = command.record_id

        if command.topic == "status":
            status = 200 if self.ACTIVE else 418
            status_msg = "Active" if self.ACTIVE else "Inactive"
            return (status, json.dumps({"status": status_msg}))

        if command.topic == "version":
            if self.acapy_version is not None:
                status = 200
                status_msg = self.acapy_version
            else:
                status = 404
                status_msg = "not found"
            return (status, status_msg)

        elif command.topic == "connection":
            if record_id:
                connection_id = record_id
                agent_operation = f"/connections/{connection_id}"
            else:
                agent_operation = "/connections"

            log_msg("GET Request agent operation: ", agent_operation)

            (resp_status, resp_text) = await self.admin_GET(agent_operation)
            if resp_status != 200:
                return (resp_status, resp_text)

            log_msg("GET Request response details: ", resp_status, json.dumps(resp_text, indent=4))

            resp_json = json.loads(resp_text)
            if record_id:
                connection_info = {
                    "connection_id": resp_json["connection_id"],
                    "state": resp_json["state"],
                    "connection": resp_json,
                }
                resp_text = json.dumps(connection_info)
            else:
                resp_json = resp_json["results"]
                connection_infos = []
                for connection in resp_json:
                    connection_info = {
                        "connection_id": connection["connection_id"],
                        "state": connection["state"],
                        "connection": connection,
                    }
                    connection_infos.append(connection_info)
                resp_text = json.dumps(connection_infos)
            # translate the state from that the agent gave to what the tests expect
            resp_text = self.agent_state_translation(command.topic, resp_text)
            return (resp_status, resp_text)

        elif command.topic == "did":
            agent_operation = "/wallet/did/public"

            (resp_status, resp_text) = await self.admin_GET(agent_operation)
            if resp_status != 200:
                return (resp_status, resp_text)

            resp_json = json.loads(resp_text)
            did = resp_json["result"]

            resp_text = json.dumps(did)
            return (resp_status, resp_text)

        elif command.topic == "active-connection" and record_id:
            agent_operation = f"/connections?their_did={record_id}"

            (resp_status, resp_text) = await self.admin_GET(agent_operation)
            if resp_status != 200:
                return (resp_status, resp_text)

            # find the first active connection
            resp_json = json.loads(resp_text)
            for connection in resp_json["results"]:
                if connection["state"] == "active":
                    resp_text = json.dumps(connection)
                    return (resp_status, resp_text)

            return (400, f"Active connection not found for their_did {record_id}")

        elif command.topic == "schema":
            schema_id = record_id
            if command.anoncreds:
                agent_operation = f"/anoncreds/schema/{schema_id}"
            else:
                agent_operation = f"/schemas/{schema_id}"

            (resp_status, resp_text) = await self.admin_GET(agent_operation)
            if resp_status != 200:
                return (resp_status, resp_text)

            resp_json = json.loads(resp_text)
            schema = resp_json["schema"]

            # If anoncreds, add the id to the schema to use existing framework
            if command.anoncreds:
                schema["id"] = resp_json["schema_id"]

            resp_text = json.dumps(schema)
            return (resp_status, resp_text)

        elif command.topic == "credential-definition":
            cred_def_id = record_id

            if command.anoncreds:
                agent_operation = f"/anoncreds/credential-definition/{cred_def_id}"
            else:
                agent_operation = f"/credential-definitions/{cred_def_id}"

            (resp_status, resp_text) = await self.admin_GET(agent_operation)
            if resp_status != 200:
                return (resp_status, resp_text)

            resp_json = json.loads(resp_text)
            credential_definition = resp_json["credential_definition"]

            # If anoncreds, add the id to the credential definition to use existing framework
            if command.anoncreds:
                credential_definition["id"] = resp_json["credential_definition_id"]

            resp_text = json.dumps(credential_definition)
            return (resp_status, resp_text)

        elif command.topic == "issue-credential":
            # swap thread id for cred ex id from the webhook
            cred_ex_id = await self.swap_thread_id_for_exchange_id(
                record_id, "credential-msg", "credential_exchange_id"
            )
            agent_operation = (
                self.TopicTranslationDict[command.topic] + "records/" + cred_ex_id
            )

            (resp_status, resp_text) = await self.admin_GET(agent_operation)
            if resp_status == 200:
                resp_text = self.agent_state_translation(command.topic, resp_text)
            return (resp_status, resp_text)

        elif command.topic == "issue-credential-v2":
            # swap thread id for cred ex id from the webhook
            cred_ex_id = await self.swap_thread_id_for_exchange_id(
                record_id, "credential-msg", "cred_ex_id"
            )
            agent_operation = (
                self.TopicTranslationDict[command.topic] + "records/" + cred_ex_id
            )

            (resp_status, resp_text) = await self.admin_GET(agent_operation)
            resp_text = self.move_field_to_top_level(resp_text, "state")
            return (resp_status, resp_text)

        elif command.topic == "credential":
            operation = command.operation
            if operation == "revoked":
                agent_operation = f"/credential/{operation}/{record_id}"
                (resp_status, resp_text) = await self.admin_GET(agent_operation)
                return (resp_status, resp_text)
            else:
                # NOTE: We don't know what type of credential to fetch, so we first try an indy credential.
                # Maybe it would be nice if the test harness passed the credential format that belonged to the
                # credential
                # First try indy credential
                agent_operation = f"/credential/{record_id}"
                (resp_status, resp_text) = await self.admin_GET(agent_operation)

                # If not found try w3c credential
                if resp_status == 404:
                    agent_operation = f"/credential/w3c/{record_id}"
                    (resp_status, resp_text) = await self.admin_GET(agent_operation)

                    if resp_status == 200:
                        resp_json = json.loads(resp_text)
                        return (
                            resp_status,
                            json.dumps(
                                {
                                    "credential_id": resp_json["record_id"],
                                    "credential": resp_json["cred_value"],
                                }
                            ),
                        )

                return (resp_status, resp_text)

        elif command.topic == "proof":
            # swap thread id for pres ex id from the webhook
            pres_ex_id = await self.swap_thread_id_for_exchange_id(
                record_id, "presentation-msg", "presentation_exchange_id"
            )
            agent_operation = f"/present-proof/records/{pres_ex_id}"

            (resp_status, resp_text) = await self.admin_GET(agent_operation)
            if resp_status == 200:
                resp_text = self.agent_state_translation(command.topic, resp_text)
            return (resp_status, resp_text)

        elif command.topic == "proof-v2":
            # swap thread id for pres ex id from the webhook
            pres_ex_id = await self.swap_thread_id_for_exchange_id(
                record_id, "presentation-msg", "pres_ex_id"
            )
            agent_operation = (
                self.TopicTranslationDict[command.topic] + "records/" + pres_ex_id
            )

            (resp_status, resp_text) = await self.admin_GET(agent_operation)
            return (resp_status, resp_text)

        elif command.topic == "revocation":
            operation = command.operation
            (
                agent_operation,
                admin_data,
            ) = await self.get_agent_operation_acapy_version_based(command)

            (resp_status, resp_text) = await self.admin_GET(agent_operation)
            return (resp_status, resp_text)

        elif command.topic == "did-exchange":

            connection_id = record_id
            agent_operation = f"/connections/{connection_id}"

            (resp_status, resp_text) = await self.admin_GET(agent_operation)
            if resp_status == 200:
                resp_text = self.agent_state_translation(command.topic, resp_text)
            return (resp_status, resp_text)

        return (501, "501: Not Implemented\n\n")

    async def make_agent_DELETE_request(
        self, command: BackchannelCommand
    ) -> Tuple[int, str]:
        record_id = command.record_id

        if command.topic == "credential" and record_id:
            agent_operation = f"/credential/{record_id}"
            log_msg(agent_operation)

            (resp_status, resp_text) = await self.admin_DELETE(agent_operation)
            if resp_status == 200:
                resp_text = self.agent_state_translation(command.topic, resp_text)
            return (resp_status, resp_text)

        return (501, "501: Not Implemented\n\n")

    async def make_agent_GET_request_response(
        self, command: BackchannelCommand, message_name: Optional[str] = None
    ) -> Tuple[int, str]:
        topic = command.topic
        record_id = command.record_id

        if topic == "connection" and record_id:
            connection_msg = pop_resource(record_id, "connection-msg")
            i = 0
            while connection_msg is None and i < MAX_TIMEOUT:
                await asyncio.sleep(1)
                connection_msg = pop_resource(record_id, "connection-msg")
                i = i + 1

            resp_status = 200
            if connection_msg:
                resp_text = json.dumps(connection_msg)
            else:
                resp_text = "{}"

            return (resp_status, resp_text)

        if topic == "did-exchange" and record_id:
            didexchange_msg = pop_resource(record_id, "didexchange-msg")
            i = 0
            while didexchange_msg is None and i < MAX_TIMEOUT:
                await asyncio.sleep(1)
                didexchange_msg = pop_resource(record_id, "didexchange-msg")
                i = i + 1

            resp_status = 200
            if didexchange_msg:
                resp_text = json.dumps(didexchange_msg)
                resp_text = self.agent_state_translation(topic, resp_text)
            else:
                resp_text = "{}"

            return (resp_status, resp_text)

        # Poping webhook messages wihtout an id is unusual. This code may be removed when issue 944 is fixed
        # see https://app.zenhub.com/workspaces/von---verifiable-organization-network-5adf53987ccbaa70597dbec0/issues/hyperledger/aries-cloudagent-python/944
        if topic == "did-exchange" and record_id is None:
            await asyncio.sleep(1)
            if message_name is not None:
                didexchange_msg = pop_resource_latest(message_name)
            else:
                didexchange_msg = pop_resource_latest("connection-msg")
            i = 0
            while didexchange_msg is None and i < MAX_TIMEOUT:
                await asyncio.sleep(1)
                didexchange_msg = pop_resource_latest("connection-msg")
                i = i + 1

            resp_status = 200
            if didexchange_msg:
                resp_text = json.dumps(didexchange_msg)
                resp_text = self.agent_state_translation(topic, resp_text)
            else:
                resp_text = "{}"

            return (resp_status, resp_text)

        elif topic == "issue-credential" and record_id:
            credential_msg = pop_resource(record_id, "credential-msg")
            i = 0
            while credential_msg is None and i < MAX_TIMEOUT:
                await asyncio.sleep(1)
                credential_msg = pop_resource(record_id, "credential-msg")
                i = i + 1

            resp_status = 200
            if credential_msg:
                resp_text = json.dumps(credential_msg)
            else:
                resp_text = "{}"

            return (resp_status, resp_text)

        elif topic == "credential" and record_id:
            credential_msg = pop_resource(record_id, "credential-msg")
            i = 0
            while credential_msg is None and i < MAX_TIMEOUT:
                await asyncio.sleep(1)
                credential_msg = pop_resource(record_id, "credential-msg")
                i = i + 1

            resp_status = 200
            if credential_msg:
                resp_text = json.dumps(credential_msg)
            else:
                resp_text = "{}"

            return (resp_status, resp_text)

        elif topic == "proof" and record_id:
            presentation_msg = pop_resource(record_id, "presentation-msg")
            i = 0
            while presentation_msg is None and i < MAX_TIMEOUT:
                await asyncio.sleep(1)
                presentation_msg = pop_resource(record_id, "presentation-msg")
                i = i + 1

            resp_status = 200
            if presentation_msg:
                resp_text = json.dumps(presentation_msg)
                if resp_status == 200:
                    resp_text = self.agent_state_translation(topic, resp_text)
            else:
                resp_text = "{}"

            return (resp_status, resp_text)

        elif topic == "revocation-registry" and record_id:
            revocation_msg = pop_resource(record_id, "revocation-registry-msg")
            i = 0
            while revocation_msg is None and i < MAX_TIMEOUT:
                await asyncio.sleep(1)
                revocation_msg = pop_resource(record_id, "revocation-registry-msg")
                i = i + 1

            resp_status = 200
            if revocation_msg:
                resp_text = json.dumps(revocation_msg)
            else:
                resp_text = "{}"

            return (resp_status, resp_text)

        elif topic == "revocation-notification" and record_id:
            revocation_notification = pop_resource(
                record_id, "revocation-notification-msg"
            )
            i = 0
            while revocation_notification is None and i < MAX_TIMEOUT:
                await asyncio.sleep(1)
                revocation_notification = pop_resource(
                    record_id, "revocation-notification-msg"
                )
                i = i + 1

            # Not sure why the status is 200 even if not found? That's quite confusing
            resp_status = 200
            if revocation_notification:
                resp_text = json.dumps(revocation_notification)
            else:
                resp_text = "{}"

            return (resp_status, resp_text)

        return (501, "501: Not Implemented\n\n")

    def _process(
        self, args: List[str], env: Dict[str, str], loop: asyncio.AbstractEventLoop
    ):
        if PIPE_AGENT_OUTPUT:
            # pipe output directly to console
            proc = subprocess.Popen(args, env=env, encoding="utf-8", preexec_fn=os.setsid)
            stdout = loop.run_in_executor(
                None,
                output_reader,
                proc.stdout,
                functools.partial(self.handle_output, source="stdout"),
            )
            stderr = loop.run_in_executor(
                None,
                output_reader,
                proc.stderr,
                functools.partial(self.handle_output, source="stderr"),
            )
            self.output_handler_futures = [stdout, stderr]
        else:
            # setup temp file for agent output
            tempfile1 = tempfile.NamedTemporaryFile(
                mode='w+', encoding="utf-8", buffering=-1,
                delete_on_close=False, delete=False,
                dir="/agent_logs", prefix=self.ident+"-stdout",
            )
            tempfile2 = tempfile.NamedTemporaryFile(
                mode='w+', encoding="utf-8", buffering=-1,
                delete_on_close=False, delete=False,
                dir="/agent_logs", prefix=self.ident+"-stderr",
            )
            proc = subprocess.Popen(
                args,
                env=env,
                stdout=tempfile1,
                stderr=tempfile2,
                encoding="utf-8",
                preexec_fn=os.setsid,
            )
        return proc

    def get_process_args(self, bin_path: Optional[str] = None) -> List[str]:
        # TODO aca-py needs to be in the path so no need to give it a cmd_path
        cmd_path = "aca-py"
        if bin_path is None:
            bin_path = DEFAULT_BIN_PATH
        if bin_path:
            cmd_path = os.path.join(bin_path, cmd_path)
        print("Location of ACA-Py: " + cmd_path)
        if self.get_acapy_version_as_float() > 56:
            return list(flatten(([cmd_path, "start"], self.get_agent_args())))
        else:
            return list(
                flatten((["python3", cmd_path, "start"], self.get_agent_args()))
            )

    async def detect_process(self):
        async def fetch_swagger(url: str, timeout: float):
            text = None
            start = default_timer()
            # add a short delay on startup in case the agent takes some time to initialize
            await asyncio.sleep(0.5)
            async with ClientSession(timeout=ClientTimeout(total=3.0)) as session:
                while default_timer() - start < timeout:
                    try:
                        async with session.get(url) as resp:
                            # a bit of debugging for startup issues
                            c_time = current_time()
                            print(f">>> {c_time}: {url} -> {resp.status}")
                            if resp.status == 200:
                                text = await resp.text()
                                break
                    except (ClientError, asyncio.TimeoutError):
                        pass
                    await asyncio.sleep(0.5)
            return text

        status_url = self.admin_url + "/status"
        status_text = await fetch_swagger(status_url, START_TIMEOUT)
        c_time = current_time()
        if not status_text:
            print(f">>> {c_time}: Error starting agent on admin url", self.admin_url)
            raise Exception(
                "Timed out waiting for agent process to start. "
                + f"Admin URL: {status_url}"
            )
        else:
            print(f">>> {c_time}: Agent running with admin url", self.admin_url)

        ok = False
        try:
            status = json.loads(status_text)
            ok = isinstance(status, dict) and "version" in status
            if ok:
                self.acapy_version = status["version"]
                print(
                    "ACA-py Backchannel running with ACA-py version:",
                    self.acapy_version,
                )
        except json.JSONDecodeError:
            pass
        if not ok:
            raise Exception(
                f"Unexpected response from agent process. Admin URL: {status_url}"
            )

    async def start_process_with_extra_args(
        self, *, args: List[str] = [], bin_path: Optional[str] = None, wait: bool = True
    ):
        my_env = os.environ.copy()
        my_env["PYTHONPATH"] = DEFAULT_PYTHON_PATH

        agent_args = self.get_process_args(bin_path)
        # If args contains items that are in agent_args, remove them from agent_args
        # This is to avoid duplicate arguments, and respects the ones that were passed in.
        # Remove all items in args that do not have a '--' prefix to help with removing duplicates
        args_names_only = [arg for arg in args if arg.startswith('--')]
        for arg in args_names_only:
            if arg in agent_args:
                index = agent_args.index(arg)
                # remove the key
                del agent_args[index]
                # remove all items after the key until the next key that starts with '--'
                while index < len(agent_args) and not agent_args[index].startswith('--'):
                    del agent_args[index]
        agent_args = agent_args + args

        # start agent sub-process
        self.log("Starting agent sub-process ...")
        self.log("agent starting with params: ")
        self.log(agent_args)
        self.log("and environment:")
        self.log(my_env)
        loop = asyncio.get_event_loop()
        self.proc = await loop.run_in_executor(
            None, self._process, agent_args, my_env, loop
        )
        if wait:
            await asyncio.sleep(1.0)
            await self.detect_process()

    async def start_process(
        self, python_path: str = None, bin_path: str = None, wait: bool = True
    ):
        my_env = os.environ.copy()
        python_path = DEFAULT_PYTHON_PATH if python_path is None else python_path
        if python_path:
            my_env["PYTHONPATH"] = python_path

        # By default start agent with http inbound / outbound transport
        agent_args = self.get_process_args(bin_path) + self.get_host_args(
            inbound_transports=["http"], outbound_transports=["http"]
        )

        # start agent sub-process
        c_time = current_time()
        self.log(f"{c_time}: Starting agent sub-process ...")
        self.log("agent starting with params: ")
        self.log(agent_args)
        loop = asyncio.get_event_loop()
        self.proc = await loop.run_in_executor(
            None, self._process, agent_args, my_env, loop
        )
        if wait:
            await asyncio.sleep(1.0)
            await self.detect_process()

    def _terminate(self):
        if self.proc and self.proc.poll() is None:
            # proc.terminate by itself won't kill the servers, this does
            os.killpg(os.getpgid(self.proc.pid), signal.SIGTERM)
            self.proc.terminate()
            try:
                self.proc.wait(timeout=0.5)
                self.log(f"Exited with return code {self.proc.returncode}")
            except subprocess.TimeoutExpired:
                msg = "Process did not terminate in time"
                self.log(msg)
                raise Exception(msg)

    async def kill_agent(self, loop: Optional[asyncio.AbstractEventLoop] = None):
        if loop is None:
            loop = asyncio.get_event_loop()

        if self.proc:
            await loop.run_in_executor(None, self._terminate)

        for fut in self.output_handler_futures:
            fut.cancel()

        self.output_handler_futures = []

    async def terminate(self):
        await self.kill_agent()

        await self.client_session.close()
        if self.webhook_site:
            await self.webhook_site.stop()

    def map_test_json_to_admin_api_json(
        self, topic: str, operation: str, data: Mapping
    ):
        # If the translation of the json get complicated in the future we might want to consider a switch to JsonMapper or equivalent.
        # json_mapper = JsonMapper()
        # map_specification = {
        #     'name': ['person_name']
        # }
        # JsonMapper(test_json).map(map_specification)

        if topic == "proof":

            if operation == "send-request" or operation == "create-request":
                request_type = "proof_request"

                request_data = (
                    data.get("presentation_request", {})
                    .get(request_type, {})
                    .get("data", {})
                )

                requested_attributes = request_data.get("requested_attributes", {})
                requested_predicates = request_data.get("requested_predicates", {})
                proof_request_name = request_data.get("name", "test proof")
                proof_request_version = request_data.get("version", "1.0")
                non_revoked = request_data.get("non_revoked", None)
                connection_id = data.get("connection_id")

                admin_data = {
                    "comment": data["presentation_request"]["comment"],
                    "trace": False,
                    request_type: {
                        "name": proof_request_name,
                        "version": proof_request_version,
                        "requested_attributes": requested_attributes,
                        "requested_predicates": requested_predicates,
                    },
                }

                if connection_id:
                    admin_data["connection_id"] = connection_id
                if non_revoked is not None:
                    admin_data[request_type]["non_revoked"] = non_revoked

            # Make special provisions for proposal. The names are changed in this operation. Should be consistent imo.
            # this whole condition can be removed for V2.0 of the protocol. It will look like more of a send-request in 2.0.
            elif operation == "send-proposal":

                request_type = "presentation_proposal"

                proposal_data = data.get("presentation_proposal", {})

                attributes = proposal_data.get("attributes", [])
                predicates = proposal_data.get("predicates", [])
                connection_id = data.get("connection_id")

                admin_data = {
                    "comment": data["presentation_proposal"]["comment"],
                    "trace": False,
                    request_type: {
                        "attributes": attributes,
                        "predicates": predicates,
                    },
                }

                if connection_id:
                    admin_data["connection_id"] = connection_id

            elif operation == "send-presentation":

                requested_attributes = data.get("requested_attributes", {})
                requested_predicates = data.get("requested_predicates", {})
                self_attested_attributes = data.get("self_attested_attributes", {})

                admin_data = {
                    "comment": data["comment"],
                    "requested_attributes": requested_attributes,
                    "requested_predicates": requested_predicates,
                    "self_attested_attributes": self_attested_attributes,
                }

            else:
                admin_data = data

            return admin_data

        if topic == "proof-v2":

            if operation == "send-request" or operation == "create-request":
                request_type = "presentation_request"

                presentation_request_orig = data.get("presentation_request", {})
                pres_request_data = presentation_request_orig.get("data", {})
                cred_format = presentation_request_orig.get("format")

                if cred_format is None:
                    raise Exception("Credential format not specified for presentation")
                elif cred_format == "indy":
                    requested_attributes = pres_request_data.get(
                        "requested_attributes", {}
                    )
                    requested_predicates = pres_request_data.get(
                        "requested_predicates", {}
                    )
                    proof_request_name = pres_request_data.get("name", "test proof")
                    proof_request_version = pres_request_data.get("version", "1.0")
                    non_revoked = pres_request_data.get("non_revoked")

                    presentation_request = {
                        cred_format: {
                            "name": proof_request_name,
                            "version": proof_request_version,
                            "requested_attributes": requested_attributes,
                            "requested_predicates": requested_predicates,
                        }
                    }

                    if non_revoked is not None:
                        presentation_request[cred_format]["non_revoked"] = non_revoked

                elif cred_format == "json-ld":
                    # We use DIF format for JSON-LD credentials
                    presentation_request = {"dif": pres_request_data}
                else:
                    raise Exception(f"Unknown credential format: {cred_format}")

                admin_data = {
                    "comment": presentation_request_orig["comment"],
                    "trace": False,
                    request_type: presentation_request,
                }

                connection_id = presentation_request_orig.get("connection_id")
                if connection_id:
                    admin_data["connection_id"] = connection_id

            elif operation == "send-presentation":

                cred_format = data.get("format")

                if cred_format is None:
                    raise Exception("Credential format not specified for presentation")
                elif cred_format == "indy":
                    requested_attributes = data.get("requested_attributes", {})
                    requested_predicates = data.get("requested_predicates", {})
                    self_attested_attributes = data.get("self_attested_attributes", {})

                    presentation_data = {
                        cred_format: {
                            "requested_attributes": requested_attributes,
                            "requested_predicates": requested_predicates,
                            "self_attested_attributes": self_attested_attributes,
                        }
                    }
                elif cred_format == "json-ld":
                    presentation = data.copy()
                    presentation.pop("format")

                    presentation_data = {"dif": presentation}

                else:
                    raise Exception(f"Unknown credential format: {cred_format}")

                admin_data = {
                    **presentation_data,
                    "comment": data.get("comment", "some comment"),
                }

            else:
                admin_data = data

            return admin_data

    def agent_state_translation(self, topic: str, data: str):
        # This method is used to translate the agent states passes back in the responses of operations into the states the
        # test harness expects. The test harness expects states to be as they are written in the Protocol's RFC.
        # the following is what the tests/rfc expect vs what aca-py communicates
        # Connection Protocol:
        # Tests/RFC         |   Aca-py
        # invited           |   invitation
        # requested         |   request
        # responded         |   response
        # complete          |   active
        #
        # Issue Credential Protocol:
        # Tests/RFC         |   Aca-py
        # proposal-sent     |   proposal_sent
        # proposal-received |   proposal_received
        # offer-sent        |   offer_sent
        # offer_received    |   offer_received
        # request-sent      |   request_sent
        # request-received  |   request_received
        # credential-issued |   issued
        # credential-received | credential_received
        # done              |   credential_acked
        #
        # Present Proof Protocol:
        # Tests/RFC         |   Aca-py

        def replace_state_values(data: str, *, old_state: str, new_state: str):
            return data.replace(f'"state": "{old_state}"', f'"state": "{new_state}"')

        resp_json = json.loads(data)
        # Check to see if state is in the json
        if "state" in resp_json:
            agent_state = resp_json["state"]

            # Check the their_role property in the data and set the calling method to swap states to the correct role for DID Exchange
            if "their_role" in data:
                if "invitee" in data:
                    de_state_trans_method = (
                        self.didExchangeResponderStateTranslationDict
                    )
                elif "inviter" in data:
                    de_state_trans_method = (
                        self.didExchangeRequesterStateTranslationDict
                    )
            else:
                # make the trans method any one, since it doesn't matter. It's probably Out of Band.
                de_state_trans_method = self.didExchangeResponderStateTranslationDict

            if topic == "connection":
                # if the response contains didexchange/1.0, swap out the connection states for the did exchange states
                # if "didexchange/1.0" in resp_json["connection_protocol"]:
                if "didexchange/1.0" in data or "didexchange/1.1" in data:
                    data = replace_state_values(
                        data,
                        old_state=agent_state,
                        new_state=de_state_trans_method[agent_state],
                    )
                else:
                    data = data.replace(
                        agent_state, self.connectionStateTranslationDict[agent_state]
                    )
            elif topic == "issue-credential":
                data = data.replace(
                    agent_state, self.issueCredentialStateTranslationDict[agent_state]
                )
            elif topic == "proof":
                data = replace_state_values(
                    data,
                    old_state=agent_state,
                    new_state=self.presentProofStateTranslationDict[agent_state],
                )
            elif topic == "out-of-band" or topic == "did-exchange":
                data = replace_state_values(
                    data,
                    old_state=agent_state,
                    new_state=de_state_trans_method[agent_state],
                )
        return data

    async def get_agent_operation_acapy_version_based(
        self, command: BackchannelCommand
    ) -> Tuple[str, Optional[Mapping[str, Any]]]:
        # Admin api calls may change with acapy releases. For example revocation related calls change
        # between 0.5.4 and 0.5.5. To be able to handle this the backchannel is made aware of the acapy version
        # and constructs the calls based off that version

        # construct some number to compare to with > or < instead of listing out the version number
        comparibleVersion = self.get_acapy_version_as_float()

        topic = command.topic
        operation = command.operation
        data = command.data

        if topic == "revocation":
            if operation == "revoke":
                if comparibleVersion > 54:
                    agent_operation = f"/revocation/{operation}"
                    if "cred_ex_id" in data:
                        admin_data = {
                            "cred_ex_id": data["cred_ex_id"],
                        }
                    else:
                        admin_data = {
                            "cred_rev_id": data["cred_rev_id"],
                            "rev_reg_id": data["rev_registry_id"],
                            "publish": str(data["publish_immediately"]).lower(),
                        }

                    # Revocation Notification
                    notify_connection_id = data.get("notify_connection_id")
                    if notify_connection_id:
                        admin_data["notify"] = True
                        admin_data["connection_id"] = notify_connection_id
                    data = admin_data
                else:
                    agent_operation = "/issue-credential/" + operation

                    if (
                        data is not None
                    ):  # Data should be included with 0.5.4 or lower acapy. Then it takes them as inline parameters.
                        cred_rev_id = data["cred_rev_id"]
                        rev_reg_id = data["rev_registry_id"]
                        publish = data["publish_immediately"]
                        agent_operation = (
                            agent_operation
                            + "?cred_rev_id="
                            + cred_rev_id
                            + "&rev_reg_id="
                            + rev_reg_id
                            + "&publish="
                            + rev_reg_id
                            + str(publish).lower()
                        )
                        data = None
            elif operation == "credential-record":
                agent_operation = f"/revocation/{operation}"
                if "cred_ex_id" in data:
                    cred_ex_id = data["cred_ex_id"]
                    agent_operation = f"{agent_operation}?cred_ex_id={cred_ex_id}"
                else:
                    cred_rev_id = data["cred_rev_id"]
                    rev_reg_id = data["rev_registry_id"]
                    agent_operation = (
                        agent_operation
                        + "?cred_rev_id="
                        + cred_rev_id
                        + "&rev_reg_id="
                        + rev_reg_id
                    )
                    data = None

        return agent_operation, data


async def main(start_port: int, show_timing: bool = False, interactive: bool = True):

    c_time = current_time()
    print(f"{c_time}: starting backchannel process")

    # check for extra args
    extra_args = {}
    if EXTRA_ARGS:
        print("Got extra args:", EXTRA_ARGS)
        extra_args = json.loads(EXTRA_ARGS)

    genesis = await default_genesis_txns()
    if not genesis:
        print("Error retrieving ledger genesis transactions")
        sys.exit(1)

    agent = None

    agent_ports = AgentPorts(
        http=start_port + 1,
        admin=start_port + 2,
        # webhook listens on +3
        ws=start_port + 4,
    )

    try:
        agent = AcaPyAgentBackchannel(
            "aca-py." + AGENT_NAME,
            agent_ports=agent_ports,
            genesis_data=genesis,
            extra_args=extra_args,
        )

        # add mediation routes
        agent.app.add_routes(mediation_routes)
        agent.app.add_routes(agent_routes)

        # start backchannel (common across all types of agents)
        await agent.listen_backchannel(start_port)

        # start aca-py agent sub-process and listen for web hooks
        await agent.listen_webhooks(start_port + 3)

        # Check if "read-only-ledger" is true in the config file. If true, skip registering DID.
        if "read-only-ledger" not in agent.get_agent_args() or "read-only-ledger" not in extra_args:
            # Check if there is an AGENT_CONFIG_FILE and if "read-only-ledger" is present in the file.
            agent_config_file = os.getenv("AGENT_CONFIG_FILE")
            if agent_config_file is not None:
                with open(agent_config_file) as  agent_config_file:
                    #print the content of the opened text file
                    agent_config_text_file = agent_config_file.read()
                    print(agent_config_text_file)
                    if "read-only-ledger" not in agent_config_text_file:
                        await agent.register_did()
            else:
                await agent.register_did()

        await agent.start_process()
        agent.activate()

        # now wait ...
        if interactive:
            async for option in prompt_loop("(X) Exit? [X] "):
                if option is None or option in "xX":
                    break
        else:
            print("Press Ctrl-C to exit ...")
            remaining_tasks = asyncio.all_tasks()
            await asyncio.gather(*remaining_tasks)

    finally:
        terminated = True
        try:
            if agent:
                await agent.terminate()
        except Exception:
            LOGGER.exception("Error terminating agent:")
            terminated = False

    await asyncio.sleep(0.1)

    if not terminated:
        os._exit(1)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Runs a Faber demo agent.")
    parser.add_argument(
        "-p",
        "--port",
        type=int,
        default=8020,
        metavar=("<port>"),
        help="Choose the starting port number to listen on",
    )
    parser.add_argument(
        "-i",
        "--interactive",
        type=str2bool,
        default=True,
        metavar=("<interactive>"),
        help="Start agent interactively",
    )
    args = parser.parse_args()

    try:
        asyncio.new_event_loop().run_until_complete(
            main(start_port=args.port, interactive=args.interactive)
        )
    except KeyboardInterrupt:
        os._exit(1)
