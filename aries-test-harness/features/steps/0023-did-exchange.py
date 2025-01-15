# -----------------------------------------------------------
# Behave Step Definitions for the DID Exchange Protocol 0023
# used to establish connections between Aries Agents based on DIDs.
# 0023 DID Exchange RFC:
# https://github.com/hyperledger/aries-rfcs/blob/master/features/0023-did-exchange/README.md
#
# Current AIP version level of test coverage: N/A
# Current DID Exchange version level of test coverage 1.0
#
# -----------------------------------------------------------

from behave import given, when, step
import json, time
from agent_backchannel_client import (
    agent_backchannel_GET,
    agent_backchannel_POST,
    expected_agent_state,
    setup_already_connected,
)

@step('"{sender}" and "{receiver}" create a new didexchange connection')
def step_impl(context, sender: str, receiver: str):
    # Almost all agents only allow mediation to be set-up once for a given connection
    # Reusing existing connections could mean mediation has already been set-up.
    context.use_existing_connection = False
    context.use_existing_connection_successful = False
    context.execute_steps(
        f"""
        When "{sender}" sends an explicit invitation to "{receiver}"
        And "{receiver}" receives the invitation
        When "{receiver}" sends the request to "{sender}"
        And "{sender}" receives the request
        And "{sender}" sends a response to "{receiver}"
        And "{receiver}" receives the response
        And "{receiver}" sends complete to "{sender}"
        Then "{sender}" and "{receiver}" have a connection
    """
    )

@when('"{responder}" sends an invitation to "{requester}" with {peer_did_method}')
@when('"{responder}" sends an explicit invitation to "{requester}"')
def step_impl(context, responder: str, requester: str, peer_did_method: str = None):
    responder_url = context.config.userdata.get(responder)

    # Have data values come in from the feature file context.table
    # if context.table exists, then use the value(s) from the table, otherwise use the default value
    if context.table:
        for row in context.table:
            # get the use_public_did value from the table
            if row["use_public_did"] == "True":
                data = {"use_public_did": True}
            else:
                data = {"use_public_did": False}
            # get handshake_protocols value from the table and add it to an array in the data
            if row["handshake_protocols"]:
                data["handshake_protocols"] = row["handshake_protocols"].split(", ")
                
            
    else:
        data = {"use_public_did": False}

    # if peer_did_method is set, then save it to the context for validation later in the tests
    if peer_did_method and peer_did_method != "unqualified":
        context.peer_did_method = peer_did_method
        # append use_did_method to the data
        data["use_did_method"] = peer_did_method

    # If mediator is set for the current connection, set the mediator_connection_id
    mediator = context.mediator_dict.get(responder)
    if mediator:
        data["mediator_connection_id"] = context.connection_id_dict[responder][mediator]

    (resp_status, resp_text) = agent_backchannel_POST(
        responder_url + "/agent/command/",
        "out-of-band",
        operation="send-invitation-message",
        data=data,
    )
    assert resp_status == 200, f"resp_status {resp_status} is not 200; {resp_text}"

    resp_json = json.loads(resp_text)
    assert resp_json["state"] == "invitation-sent"
    context.responder_invitation = resp_json["invitation"]
    # TODO drill into the handshake protocol in the invitation and remove anything else besides didexchange.

    if "connection_id" not in resp_json:
        # Get the responders's connection id from the above request's response webhook in the backchannel
        invitation_id = context.responder_invitation["@id"]
        (resp_status, resp_text) = agent_backchannel_GET(
            responder_url + "/agent/response/", "did-exchange", id=invitation_id
        )
        assert resp_status == 200, f"resp_status {resp_status} is not 200; {resp_text}"
        resp_json = json.loads(resp_text)

    # Some agents (afgo) do not have a webhook that give a connection id at this point in the protocol.
    # If it is not here, skip this and check for one later in the process and add it then.
    if "connection_id" in resp_text:
        context.connection_id_dict[responder][requester] = resp_json["connection_id"]

    # Check to see if the responder name is the same as this person. If not, it is a 3rd person acting as an issuer that needs a connection
    # TODO: it would be nicer to pass the names on every call to remove the need for global keeping of who's the requester / responder
    if context.responder_name != responder:
        context.responder_name = responder
        context.responder_url = responder_url
    if context.requester_name != requester:
        context.requester_name = requester
        context.requester_url = context.config.userdata.get(requester)


@given('"{requester}" has a resolvable DID')
def step_impl(context, requester: str):
    requester_url = context.config.userdata.get(requester)

    (resp_status, resp_text) = agent_backchannel_GET(
        requester_url + "/agent/command/", "did"
    )
    assert resp_status == 200, f"resp_status {resp_status} is not 200; {resp_text}"

    resp_json = json.loads(resp_text)
    context.requester_public_did = resp_json


@given('"{responder}" acquires the resolvable DID')
def step_impl(context, responder):
    # Get the responders public did.
    context.requester_did = context.requester_public_did["did"]


@when('"{requester}" sends the request to "{responder}" with the public DID')
def step_impl(context, requester: str, responder: str):
    requester_url = context.config.userdata.get(requester)

    requester_did = context.requester_did

    data = {"their_public_did": requester_did, "their_did": requester_did}

    (resp_status, resp_text) = agent_backchannel_POST(
        requester_url + "/agent/command/",
        "did-exchange",
        operation="create-request-resolvable-did",
        data=data,
    )
    assert resp_status == 200, f"resp_status {resp_status} is not 200; {resp_text}"

    resp_json = json.loads(resp_text)
    requester_did_doc = resp_json

    context.requester_public_did_doc = requester_did_doc

    if "connection_id" not in resp_json:
        # get the requesters connection id
        request_id = context.requester_public_did_doc["@id"]
        (resp_status, resp_text) = agent_backchannel_GET(
            requester_url + "/agent/response/", "did-exchange", id=request_id
        )
        assert resp_status == 200, f"resp_status {resp_status} is not 200; {resp_text}"
        resp_json = json.loads(resp_text)

    # Some agents (afgo) do not have a webhook that give a connection id at this point in the protocol.
    # If it is not here, skip this and check for one later in the process and add it then.
    if "connection_id" in resp_text:
        context.connection_id_dict[requester][responder] = resp_json["connection_id"]


@when('"{responder}" receives the request with their public DID')
def step_impl(context, responder: str):
    responder_url = context.config.userdata.get(responder)

    (resp_status, resp_text) = agent_backchannel_POST(
        responder_url + "/agent/command/",
        "did-exchange",
        operation="receive-request-resolvable-did",
        data=context.requester_public_did_doc,
    )
    assert resp_status == 200, f"resp_status {resp_status} is not 200; {resp_text}"

    resp_json = json.loads(resp_text)

    # If it is not here, skip this and check for one later in the process and add it then.
    if "connection_id" in resp_text:
        context.connection_id_dict[responder][context.requester_name] = resp_json[
            "connection_id"
        ]


@when('"{responder}" sends an explicit invitation with a public DID to "{requester}"')
def step_impl(context, responder: str, requester: str):
    responder_url = context.config.userdata.get(responder)

    data = {"use_public_did": True}

    (resp_status, resp_text) = agent_backchannel_POST(
        responder_url + "/agent/command/",
        "out-of-band",
        operation="send-invitation-message",
        data=data,
    )
    assert resp_status == 200, f"resp_status {resp_status} is not 200; {resp_text}"

    resp_json = json.loads(resp_text)
    assert resp_json["state"] == "invitation-sent"
    # assert "did:sov:BzCbsNYhMrjHiqZDTUASHg;spec/didexchange/v1.0" in resp_text
    context.responder_invitation = resp_json["invitation"]
    # TODO drill into the handshake protocol in the invitation and remove anything else besides didexchange.

    # Get the responders's connection id from the above request's response webhook in the backchannel
    # This really only needs to be done if the connection id is not in the response.
    # Agents like Credo-ts do not have a webhook response that gives the connection id at this point in the protocol.
    # Credo will have the connection_id in the response above.
    if "connection_id" not in resp_json:
        invitation_id = context.responder_invitation["@id"]
        (resp_status, resp_text) = agent_backchannel_GET(
            responder_url + "/agent/response/", "did-exchange", id=invitation_id
        )
        assert resp_status == 200, f"resp_status {resp_status} is not 200; {resp_text}"
        resp_json = json.loads(resp_text)

    if "connection_id" in resp_text:
        context.connection_id_dict[responder][requester] = resp_json["connection_id"]

    # Check to see if the responder name is the same as this person. If not, it is a 3rd person acting as an issuer that needs a connection
    # TODO: it would be nicer to pass the names on every call to remove the need for global keeping of who's the requester / responder
    if context.responder_name != responder:
        context.responder_name = responder
        context.responder_url = responder_url
    if context.requester_name != requester:
        context.requester_name = requester
        context.requester_url = context.config.userdata.get(requester)


@when('"{requester}" receives the invitation')
def step_impl(context, requester):
    requester_url: str = context.config.userdata.get(requester)

    # if feature is DID Exchange or MIME Types then set use existing connection to false
    if "0023" in context.feature.name or "0044" in context.feature.name:
        context.use_existing_connection = False

    data = context.responder_invitation
    data["use_existing_connection"] = context.use_existing_connection

    # If mediator is set for the current connection, set the mediator_connection_id
    mediator = context.mediator_dict.get(requester)
    if mediator:
        data["mediator_connection_id"] = context.connection_id_dict[requester][mediator]

    (resp_status, resp_text) = agent_backchannel_POST(
        requester_url + "/agent/command/",
        "out-of-band",
        operation="receive-invitation",
        data=data,
    )
    assert resp_status == 200, f"resp_status {resp_status} is not 200; {resp_text}"

    resp_json = json.loads(resp_text)

    if context.use_existing_connection and resp_json["state"] == "completed":
        context.use_existing_connection_successful = True
        setup_already_connected(context, resp_json, requester, context.responder_name)
    else:
        state = resp_json["state"]
        assert state == "invitation-received", f"state is {state}, expected invitation-received"

        if "connection_id" in resp_json:
            context.connection_id_dict[requester][context.responder_name] = resp_json[
                "connection_id"
            ]
        # Credo returns id instead of connection_id on out of band connections.
        elif "id" in resp_json:
            # context.connection_id_dict[requester][context.responder_name] = resp_json[
            #     "id"
            # ]
            context.connection_id_dict[requester][context.responder_name] = resp_json[
                "outOfBandId"
            ]
            # context.connection_id_dict[requester][context.responder_name] = resp_json[
            #     "threadId"
            # ]

@when('"{requester}" sends the request to "{responder}" with {requester_peer_did_method}')
@when('"{requester}" sends the request to "{responder}"')
def step_impl(context, requester, responder, requester_peer_did_method=None):
    requester_url: str = context.config.userdata.get(requester)
    requester_connection_id = context.connection_id_dict[requester][responder]

    # if peer_did_method is set, then add it to the data
    data = {}
    # passed in requester_peer_did_method takes presedence over the context.peer_did_method
    if requester_peer_did_method:
        if requester_peer_did_method != "unqualified":
            data["use_did_method"] = requester_peer_did_method
    else:
        if hasattr(context, 'peer_did_method') and context.peer_did_method != "unqualified":
            data["use_did_method"] = context.peer_did_method
        # if use_did is set, then add it to the data
        if hasattr(context, 'use_did') and context.use_did:
            data["use_did"] = context.use_did

    (resp_status, resp_text) = agent_backchannel_POST(
        requester_url + "/agent/command/",
        "did-exchange",
        operation="send-request",
        id=requester_connection_id,
        data=data,
    )
    assert resp_status == 200, f"resp_status {resp_status} is not 200; {resp_text}"

    # Check for peer did prefix in the request response
    if requester_peer_did_method:
        if requester_peer_did_method != "unqualified":
            resp_json = json.loads(resp_text)
            assert (
                resp_json["my_did"].startswith(requester_peer_did_method)
            ), f"my_did {resp_json['my_did']} does not start with {requester_peer_did_method}"
    else:
        if hasattr(context, 'peer_did_method') and context.peer_did_method != "unqualified":
            resp_json = json.loads(resp_text)
            assert (
                resp_json["my_did"].startswith(context.peer_did_method)
            ), f"my_did {resp_json['my_did']} does not start with {context.peer_did_method}"


@then('"{responder}" does not receive the request')
def step_impl(context, responder: str):
    responder_url = context.config.userdata.get(responder)

    # If the connection id dict is not populated for the responder to requester relationship, it means the agent in use doesn't
    # support giving the responders connection_id before the send-request
    # Make a call to the responder for the connection id and add it to the collection
    if context.requester_name not in context.connection_id_dict[responder]:
        # One way (maybe preferred) to get the connection id is to get it from the probable webhook that the controller gets because of the previous step
        invitation_id = context.responder_invitation["@id"]
        time.sleep(0.5)  # delay for webhook to execute
        (resp_status, resp_text) = agent_backchannel_GET(
            responder_url + "/agent/response/", "did-exchange", id=invitation_id
        )  # {}
        assert resp_status == 200, f"resp_status {resp_status} is not 200; {resp_text}"
        resp_json = json.loads(resp_text)

        if "connection_id" not in resp_text:
            # If we weren't able to find the connection_id it means the request
            # probably never arrived. We don't have to do a check
            return

        context.connection_id_dict[responder][context.requester_name] = resp_json[
            "connection_id"
        ]

    # Check the request never arrived
    assert expected_agent_state(responder_url, "did-exchange", context.connection_id_dict[responder][context.requester_name] , ["invitation-sent"])



@when('"{responder}" receives the request')
def step_impl(context, responder):
    responder_url = context.config.userdata.get(responder)

    # If the connection id dict is not populated for the responder to requester relationship, it means the agent in use doesn't
    # support giving the responders connection_id before the send-request
    # Make a call to the responder for the connection id and add it to the collection
    if context.requester_name not in context.connection_id_dict[responder]:
        # One way (maybe preferred) to get the connection id is to get it from the probable webhook that the controller gets because of the previous step
        invitation_id = context.responder_invitation["@id"]
        time.sleep(0.5)  # delay for webhook to execute
        (resp_status, resp_text) = agent_backchannel_GET(
            responder_url + "/agent/response/", "did-exchange", id=invitation_id
        )  # {}
        assert resp_status == 200, f"resp_status {resp_status} is not 200; {resp_text}"
        resp_json = json.loads(resp_text)

        # The second way to do this is to call the connection protocol for the connection id given the invitation_id or a thread id.
        # This method is disabled for now, will be enabled if afgo can't get the connection id for the webhook above.
        # (resp_status, resp_text) = agent_backchannel_GET(responder_url + "/agent/command/", connections, id=invitation_id)

        if "connection_id" in resp_text:
            context.connection_id_dict[responder][context.requester_name] = resp_json[
                "connection_id"
            ]
        else:
            assert False, f"Could not retreive responders connection_id"

            # It is probably the case that we are dealing with a Public DID invitation that does not have the webhook message keyed on
            # invitation_id. In this case, try to grab the latest unkeyed message off of the webhook queue.
            # see issue 944 for full details https://app.zenhub.com/workspaces/von---verifiable-organization-network-5adf53987ccbaa70597dbec0/issues/hyperledger/aries-cloudagent-python/944
            # (resp_status, resp_text) = agent_backchannel_GET(responder_url + "/agent/response/", "did-exchange")
            # assert resp_status == 200, f'resp_status {resp_status} is not 200; {resp_text}'
            # resp_json = json.loads(resp_text)
            # if "connection_id" in resp_text:
            #     context.connection_id_dict[responder][context.requester_name] = resp_json["connection_id"]
            # else:
            #     assert False, f'Could not retreive responders connection_id'

    # responder_connection_id = context.connection_id_dict[responder][context.requester_name]

    # responder already received the connection request in the send-request call so get connection and verify status.
    # assert expected_agent_state(responder_url, "did-exchange", responder_connection_id, "request-received")


@when('"{responder}" sends a response to "{requester}"')
def step_impl(context, responder: str, requester: str):
    responder_connection_id = context.connection_id_dict[responder][requester]
    responder_url = context.config.userdata.get(responder)

    data = {}

    # If mediator is set for the current connection, set the mediator_connection_id
    mediator = context.mediator_dict.get(responder)
    if mediator:
        data["mediator_connection_id"] = context.connection_id_dict[responder][mediator]

    (resp_status, resp_text) = agent_backchannel_POST(
        responder_url + "/agent/command/",
        "did-exchange",
        operation="send-response",
        id=responder_connection_id,
        data=data
    )
    assert resp_status == 200, f"resp_status {resp_status} is not 200; {resp_text}"

    # check for peer did prefix in the response
    if hasattr(context, 'peer_did_method') and context.peer_did_method != "unqualified":
        resp_json = json.loads(resp_text)
        assert (
            resp_json["my_did"].startswith("did:")
        ), f"my_did {resp_json['my_did']} for {responder} does not start with did:"
        assert (
            resp_json["their_did"].startswith("did:")
        ), f"their_did {resp_json['their_did']} for {requester} does not start with did:"
        


@when('"{responder}" sends a response to "{requester}" which produces a problem_report')
def step_impl(context, responder, requester):
    responder_connection_id = context.connection_id_dict[responder][requester]
    responder_url = context.config.userdata.get(responder)

    (resp_status, resp_text) = agent_backchannel_POST(
        responder_url + "/agent/command/",
        "did-exchange",
        operation="send-response",
        id=responder_connection_id,
    )
    assert resp_status == 400, f"resp_status {resp_status} is not 400; {resp_text}"


@when('"{requester}" receives the response')
def step_impl(context, requester):
    requester_connection_id = context.connection_id_dict[requester][
        context.responder_name
    ]

    requester_url: str = context.config.userdata.get(requester)

    # This should be response-received but is completed. Chat with SKlump on this issue.
    assert expected_agent_state(
        requester_url, "did-exchange", requester_connection_id, "completed"
    )


@when('"{requester}" sends complete to "{responder}"')
def step_impl(context, requester, responder):
    # this seems to be done in the response from send-response from the responder. Need to talk to SKlump about this
    pass
    # requester_url = context.config.userdata.get(requester)
    # requester_connection_id = context.connection_id_dict[requester][context.responder_name]

    # # get connection and verify status
    # assert expected_agent_state(requester_url, "connection", requester_connection_id, "response-received")

    # data = {"comment": "Hello from " + requester}
    # (resp_status, resp_text) = agent_backchannel_POST(requester_url + "/agent/command/", "did-exchange", operation="send-complete", id=requester_connection_id, data=data)
    # assert resp_status == 200, f'resp_status {resp_status} is not 200; {resp_text}'

    # # get connection and verify status
    # assert expected_agent_state(requester_url, "connection", requester_connection_id, "completed")
