# -----------------------------------------------------------
# Behave Step Definitions for the Connection Protocol 0160
# used to establish connections between Aries Agents.
# 0160 connection-protocol RFC:
# https://github.com/hyperledger/aries-rfcs/tree/9b0aaa39df7e8bd434126c4b33c097aae78d65bf/features/0160-connection-protocol#0160-connection-protocol
#
# Current AIP version level of test coverage: 1.0
#
# -----------------------------------------------------------

from time import sleep
from behave import given, when, then, step
import json
from agent_backchannel_client import (
    agent_backchannel_GET,
    agent_backchannel_POST,
    expected_agent_state,
    check_if_already_connected,
)


@given("{n} agents")
@given("we have {n} agents")
def step_impl(context, n):
    """Determine there are at least 2 agents running based on data in the Behave input file behave.ini."""

    for row in context.table:
        # Connection roles
        if row["role"] == "inviter":
            context.inviter_url = context.config.userdata.get(row["name"])
            context.inviter_name = row["name"]
            assert context.inviter_url is not None and 0 < len(context.inviter_url)
        elif row["role"] == "invitee":
            context.invitee_url = context.config.userdata.get(row["name"])
            context.invitee_name = row["name"]
            assert context.invitee_url is not None and 0 < len(context.invitee_url)
        elif row["role"] == "inviteinterceptor":
            context.inviteinterceptor_url = context.config.userdata.get(row["name"])
            context.inviteinterceptor_name = row["name"]
            assert context.inviteinterceptor_url is not None and 0 < len(
                context.inviteinterceptor_url
            )
        # This step is used across protocols, this adds roles for issue credential
        elif row["role"] == "issuer":
            context.issuer_url = context.config.userdata.get(row["name"])
            context.issuer_name = row["name"]
            assert context.issuer_url is not None and 0 < len(context.issuer_url)
            if "DIDExchangeConnection" in context.tags:
                context.responder_url = context.issuer_url
                context.responder_name = context.issuer_name
        elif row["role"] == "holder":
            context.holder_url = context.config.userdata.get(row["name"])
            context.holder_name = row["name"]
            assert context.holder_url is not None and 0 < len(context.holder_url)
            if "DIDExchangeConnection" in context.tags:
                context.requester_url = context.holder_url
                context.requester_name = context.holder_name
        # This step is used across protocols, this adds roles for present proof
        elif row["role"] == "verifier":
            context.verifier_url = context.config.userdata.get(row["name"])
            context.verifier_name = row["name"]
            assert context.verifier_url is not None and 0 < len(context.verifier_url)
            if "DIDExchangeConnection" in context.tags:
                context.responder_url = context.verifier_url
                context.responder_name = context.verifier_name
        elif row["role"] == "prover":
            context.prover_url = context.config.userdata.get(row["name"])
            context.prover_name = row["name"]
            assert context.prover_url is not None and 0 < len(context.prover_url)
            if "DIDExchangeConnection" in context.tags:
                context.requester_url = context.prover_url
                context.requester_name = context.prover_name
        # This step is used across protocols, this adds roles for DID Exchange
        elif row["role"] == "requester":
            context.requester_url = context.config.userdata.get(row["name"])
            context.requester_name = row["name"]
            assert context.requester_url is not None and 0 < len(context.requester_url)
        elif row["role"] == "responder":
            context.responder_url = context.config.userdata.get(row["name"])
            context.responder_name = row["name"]
            assert context.responder_url is not None and 0 < len(context.responder_url)
        elif row["role"] == "mediator":
            context.mediator_url = context.config.userdata.get(row["name"])
            context.mediator_name = row["name"]
            assert context.mediator_url is not None and 0 < len(context.mediator_url)
        elif row["role"] == "recipient":
            context.recipient_url = context.config.userdata.get(row["name"])
            context.recipient_name = row["name"]
            assert context.recipient_url is not None and 0 < len(context.recipient_url)
        elif row["role"] == "sender":
            context.sender_url = context.config.userdata.get(row["name"])
            context.sender_name = row["name"]
            assert context.sender_url is not None and 0 < len(context.sender_url)
        else:
            role = row["role"]
            print(
                f"Data table in step contains an unrecognized role '{role}', must be inviter, invitee, inviteinterceptor, issuer, holder, verifier, prover, requester, responder, mediator, recipient, and sender"
            )

    # Iterate over the context.table again and if start_parameters exist for one or more agents, call the start agent step definition.
    # You can find examples of usage of this in 0793-peer-did.feature
    for row in context.table:
        if row.get("start_parameters"):
            if row['start_parameters'] != 'use_running_agent':
                context.execute_steps(
                    f"""
                    Given "{row['name']}" is running with parameters "{row['start_parameters']}"
                """
                )
                # Add the name of the agent to a list of agent that are using start_parameters to context.
                # This is used in the after_scenario to reset the agent to the original parameters for preceeding tests.
                if not hasattr(context.feature, "agents_to_reset"):
                    context.feature.agents_to_reset = []
                # add the agent name to the list of agents to reset if it doesn't already exist
                if row['name'] not in context.feature.agents_to_reset:
                    context.feature.agents_to_reset.append(row['name'])
                

@when('"{inviter}" generates a connection invitation')
def step_impl(context, inviter):
    inviter_url = context.config.userdata.get(inviter)

    data = {}

    # If mediator is set for the current connection, set the mediator_connection_id
    mediator = context.mediator_dict.get(inviter)
    if mediator:
        data["mediator_connection_id"] = context.connection_id_dict[inviter][mediator]

    (resp_status, resp_text) = agent_backchannel_POST(
        inviter_url + "/agent/command/",
        "connection",
        operation="create-invitation",
        data=data,
    )
    assert resp_status == 200, f"resp_status {resp_status} is not 200; {resp_text}"

    resp_json = json.loads(resp_text)
    context.inviter_invitation = resp_json["invitation"]

    # check and see if the connection_id_dict exists
    # if it does, it was probably used to create another connection in a 3+ agent scenario
    # so that means we need to keep the connection ids around for use in the scenario
    # so we will not create a new dict which will reset the dict
    # Also, check that the connection_id actually exists in the response. Some aries frameworks do not have a connection_id
    # at this point. If it doesn't exist, it will be acquired in the receive invitation.
    if "connection_id" in resp_json:
        context.temp_connection_id_dict[inviter] = resp_json["connection_id"]

    # Check to see if the inviter_name exists in context. If not, antother suite is using it so set the inviter name and url
    if context.inviter_name != inviter:
        context.inviter_url = inviter_url
        context.inviter_name = inviter

    # if we have a connection_id at this point get connection and verify status
    # if "connection_id" in resp_json:
    #     assert expected_agent_state(inviter_url, "connection", context.temp_connection_id_dict[inviter], "invited")


@given('"{invitee}" receives the connection invitation')
@when('"{invitee}" receives the connection invitation')
def step_impl(context, invitee):
    invitee_url = context.config.userdata.get(invitee)

    data = context.inviter_invitation

    # If mediator is set for the current connection, set the mediator_connection_id
    mediator = context.mediator_dict.get(invitee)
    if mediator:
        data["mediator_connection_id"] = context.connection_id_dict[invitee][mediator]

    (resp_status, resp_text) = agent_backchannel_POST(
        invitee_url + "/agent/command/",
        "connection",
        operation="receive-invitation",
        data=data,
    )
    assert resp_status == 200, f"resp_status {resp_status} is not 200; {resp_text}"

    resp_json = json.loads(resp_text)

    context.connection_id_dict[invitee][context.inviter_name] = resp_json[
        "connection_id"
    ]

    # Also add the inviter into the main connection_id_dict. if the len is 0 that means its already been cleared and this may be Mallory.
    if len(context.temp_connection_id_dict) != 0:
        context.connection_id_dict[context.inviter_name][
            invitee
        ] = context.temp_connection_id_dict[context.inviter_name]
        # clear the temp connection id dict used in the initial step. We don't need it anymore.
        context.temp_connection_id_dict.clear()
    else:
        # This means the connection id was not retreived for the inviter in the create invitation step
        # Get the connection id for the inviter given the invitation_id
        (alt_resp_status, alt_resp_text) = agent_backchannel_GET(
            context.inviter_url + "/agent/response/",
            "connection",
            id=context.inviter_invitation["@id"],
        )
        assert (
            alt_resp_status == 200
        ), f"resp_status {alt_resp_status} is not 200; {alt_resp_text}"
        alt_resp_json = json.loads(alt_resp_text)
        context.connection_id_dict[context.inviter_name][invitee] = alt_resp_json[
            "connection_id"
        ]

    # Check to see if the invitee_name exists in context. If not, antother suite is using it so set the invitee name and url
    if not context.invitee_name:
        context.invitee_url = invitee_url
        context.invitee_name = invitee


@when('"{inviter}" sends a connection response to "{invitee}"')
@given('"{inviter}" sends a connection response to "{invitee}"')
@then('"{inviter}" sends a connection response to "{invitee}"')
def step_impl(context, inviter, invitee):
    inviter_url = context.config.userdata.get(inviter)
    inviter_connection_id = context.connection_id_dict[inviter][invitee]
    invitee_url = context.config.userdata.get(invitee)
    invitee_connection_id = context.connection_id_dict[invitee][inviter]

    # Acapy sometimes sends connection requets only after accept-request is called,
    # resulting in an error, hence the sleep
    sleep(1)
    (resp_status, resp_text) = agent_backchannel_POST(
        inviter_url + "/agent/command/",
        "connection",
        operation="accept-request",
        id=inviter_connection_id,
    )
    assert resp_status == 200, f"resp_status {resp_status} is not 200; {resp_text}"


@when('"{invitee}" receives the connection response')
@given('"{invitee}" receives the connection response')
def step_impl(context, invitee):
    invitee_url = context.config.userdata.get(invitee)
    invitee_connection_id = context.connection_id_dict[invitee][context.inviter_name]

    # invitee already received the connection response in the accept-request call so get connection and verify status=responded.
    # assert expected_agent_state(invitee_url, "connection", invitee_connection_id, "responded")


@given('"{invitee}" sends a connection request to "{inviter}"')
@when('"{invitee}" sends a connection request to "{inviter}"')
def step_impl(context, invitee, inviter):
    invitee_url = context.config.userdata.get(invitee)
    invitee_connection_id = context.connection_id_dict[invitee][inviter]
    inviter_url = context.config.userdata.get(inviter)
    inviter_connection_id = context.connection_id_dict[inviter][invitee]

    (resp_status, resp_text) = agent_backchannel_POST(
        invitee_url + "/agent/command/",
        "connection",
        operation="accept-invitation",
        id=invitee_connection_id,
    )
    assert resp_status == 200, f"resp_status {resp_status} is not 200; {resp_text}"

    # resp_json = json.loads(resp_text)
    # assert resp_json["state"] == "requested"


@when('"{inviter}" receives the connection request')
@given('"{inviter}" receives the connection request')
def step_impl(context, inviter):
    pass
    # inviter_url = context.config.userdata.get(inviter)
    # inviter_connection_id = context.connection_id_dict[inviter][context.invitee_name]

    # inviter already received the connection request in the accept-invitation call so get connection and verify status=requested.
    # Some agents (Aca-py) when auto respond is on, it won't send responded by the invitee on the accept-invitation,
    # it will set responded on inviter on the connection object.
    # if not expected_agent_state(inviter_url, "connection", inviter_connection_id, "requested", wait_time=60.0):
    #     if expected_agent_state(inviter_url, "connection", inviter_connection_id, "responded", wait_time=60.0):
    #         context.auto_response = True


@when('"{inviter}" accepts the connection response to "{invitee}"')
def step_impl(context, inviter, invitee):

    inviter_url = context.config.userdata.get(inviter)
    inviter_connection_id = context.connection_id_dict[inviter][invitee]
    invitee_url = context.config.userdata.get(invitee)
    invitee_connection_id = context.connection_id_dict[invitee][inviter]

    (resp_status, resp_text) = agent_backchannel_POST(
        inviter_url + "/agent/command/",
        "connection",
        operation="accept-request",
        id=inviter_connection_id,
    )
    assert resp_status == 200, f"resp_status {resp_status} is not 200; {resp_text}"


@when('"{invitee}" sends a response ping')
def step_impl(context, invitee):
    invitee_url = context.config.userdata.get(invitee)
    invitee_connection_id = context.connection_id_dict[invitee][context.inviter_name]

    data = {"comment": "Hello from " + invitee}
    (resp_status, resp_text) = agent_backchannel_POST(
        invitee_url + "/agent/command/",
        "connection",
        operation="send-ping",
        id=invitee_connection_id,
        data=data,
    )
    assert resp_status == 200, f"resp_status {resp_status} is not 200; {resp_text}"

    # get connection and verify status
    assert expected_agent_state(
        invitee_url, "connection", invitee_connection_id, "complete"
    )


@when('"{inviter}" receives the response ping')
def step_impl(context, inviter):
    # extra step to force status to 'active' for VCX
    inviter_url = context.config.userdata.get(inviter)
    inviter_connection_id = context.connection_id_dict[inviter][context.invitee_name]

    data = {"comment": "Hello from " + inviter}
    (resp_status, resp_text) = agent_backchannel_POST(
        inviter_url + "/agent/command/",
        "connection",
        operation="send-ping",
        id=inviter_connection_id,
        data=data,
    )
    assert resp_status == 200, f"resp_status {resp_status} is not 200; {resp_text}"

    # get connection and verify status
    assert expected_agent_state(
        inviter_url, "connection", inviter_connection_id, "complete"
    )


@then('"{inviter}" and "{invitee}" still have a completed connection')
@then('"{inviter}" and "{invitee}" have a connection')
def step_impl(context, inviter, invitee):
    inviter_url = context.config.userdata.get(inviter)
    inviter_connection_id = context.connection_id_dict[inviter][invitee]
    invitee_url = context.config.userdata.get(invitee)
    invitee_connection_id = context.connection_id_dict[invitee][inviter]

    # Check to see if this is a DID Exchange connection to set the state to check appropriately for that protocol.
    if context.responder_url:
        state_to_assert = "completed"
        topic = "did-exchange"
    else:
        state_to_assert = [
            "responded",
            "complete",
        ]
        topic = "connection"

    # get connection and verify status for inviter
    assert expected_agent_state(
        inviter_url, topic, inviter_connection_id, state_to_assert, wait_time=60.0
    )

    # get connection and verify status for invitee
    assert expected_agent_state(
        invitee_url, topic, invitee_connection_id, state_to_assert, wait_time=60.0
    )


@then('"{invitee}" is connected to "{inviter}"')
def step_impl(context, inviter, invitee):
    inviter_url = context.config.userdata.get(inviter)
    inviter_connection_id = context.connection_id_dict[inviter][invitee]
    invitee_url = context.config.userdata.get(invitee)
    invitee_connection_id = context.connection_id_dict[invitee][inviter]

    # get connection and verify status for inviter
    assert expected_agent_state(
        inviter_url, "connection", inviter_connection_id, "responded"
    )

    # get connection and verify status for invitee
    assert expected_agent_state(
        invitee_url, "connection", invitee_connection_id, "complete"
    )


@step('"{sender}" and "{receiver}" create a new connection')
def step_impl(context, sender, receiver):
    """Create a new connection, explicitly not using connection reuse"""
    if "DIDExchangeConnection" in context.tags:
        context.execute_steps(
            f"""
            When "{sender}" and "{receiver}" create a new didexchange connection
        """
        )

    else:
        context.execute_steps(
            f"""
           When "{sender}" generates a connection invitation
            And "{receiver}" receives the connection invitation
            And "{receiver}" sends a connection request to "{sender}"
            And "{sender}" receives the connection request
            And "{sender}" sends a connection response to "{receiver}"
            And "{receiver}" receives the connection response
            And "{receiver}" sends trustping to "{sender}"
           Then "{sender}" and "{receiver}" have a connection
        """
        )


@when('"{sender}" and "{receiver}" have an existing connection')
@given('"{sender}" and "{receiver}" have an existing connection')
def step_impl(context, sender, receiver):
    if "DIDExchangeConnection" in context.tags:
        context.use_existing_connection = True
        context.use_existing_connection_successful = False
        context.execute_steps(
            f"""
            When "{sender}" sends an explicit invitation with a public DID to "{receiver}"
            And "{receiver}" receives the invitation
        """
        )
        if not context.use_existing_connection_successful:
            context.execute_steps(
                f"""
                When "{receiver}" sends the request to "{sender}"
                And "{sender}" receives the request
                And "{sender}" sends a response to "{receiver}"
                And "{receiver}" receives the response
                And "{receiver}" sends complete to "{sender}"
                Then "{sender}" and "{receiver}" have a connection
            """
            )

    else:
        context.execute_steps(
            f"""
           When "{sender}" generates a connection invitation
            And "{receiver}" receives the connection invitation
            And "{receiver}" sends a connection request to "{sender}"
            And "{sender}" receives the connection request
            And "{sender}" sends a connection response to "{receiver}"
            And "{receiver}" receives the connection response
            And "{receiver}" sends trustping to "{sender}"
           Then "{sender}" and "{receiver}" have a connection
        """
        )


@when('"{sender}" sends a trust ping')
def step_impl(context, sender):
    sender_url = context.config.userdata.get(sender)
    sender_connection_id = context.connection_id_dict[sender][context.inviter_name]

    # get connection and verify status
    assert expected_agent_state(
        sender_url, "connection", sender_connection_id, "active"
    )

    data = {"comment": "Hello from " + sender}
    (resp_status, resp_text) = agent_backchannel_POST(
        sender_url + "/agent/command/",
        "connection",
        operation="send-ping",
        id=sender_connection_id,
        data=data,
    )
    assert resp_status == 200, f"resp_status {resp_status} is not 200; {resp_text}"

    # get connection and verify status
    assert expected_agent_state(
        sender_url, "connection", sender_connection_id, "complete"
    )


@then('"{receiver}" receives the trust ping')
def step_impl(context, receiver):
    # TODO
    pass


@given('"{invitee}" has sent a connection request to "{inviter}"')
def step_impl(context, invitee, inviter):
    context.execute_steps(
        f"""
        When "{inviter}" generates a connection invitation
         And "{invitee}" receives the connection invitation
         And "{invitee}" sends a connection request
    """
    )


@given(
    '"{inviter}" has accepted the connection request by sending a connection response'
)
def step_impl(context, inviter):
    context.execute_steps(f"""When "{inviter}" accepts the connection response""")


@given('"{invitee}" is in the state of complete')
def step_impl(context, invitee):
    invitee_url = context.config.userdata.get(invitee)
    invitee_connection_id = context.connection_id_dict[invitee][context.inviter_name]

    # get connection and verify status
    assert expected_agent_state(
        invitee_url, "connection", invitee_connection_id, "complete"
    )


@given('"{inviter}" is in the state of responded')
def step_impl(context, inviter):
    inviter_url = context.config.userdata.get(inviter)
    inviter_connection_id = context.connection_id_dict[inviter][context.invitee_name]

    # get connection and verify status
    assert expected_agent_state(
        inviter_url, "connection", inviter_connection_id, "responded"
    )


@when('"{sender}" sends acks to "{receiver}"')
def step_impl(context, sender, receiver):
    sender_url = context.config.userdata.get(sender)
    sender_connection_id = context.connection_id_dict[sender][context.inviter_name]

    data = {"comment": "acknowledgement from " + sender}
    # TODO acks not implemented yet, this will fail.
    (resp_status, resp_text) = agent_backchannel_POST(
        sender_url + "/agent/command/",
        "connection",
        operation="acks",
        id=sender_connection_id,
        data=data,
    )
    assert resp_status == 200, f"resp_status {resp_status} is not 200; {resp_text}"


@when('"{sender}" sends trustping to "{receiver}"')
def step_impl(context, sender, receiver):
    sender_url = context.config.userdata.get(sender)
    sender_connection_id = context.connection_id_dict[sender][receiver]

    data = {"comment": "acknowledgement from " + sender}
    sleep(5)
    (resp_status, resp_text) = agent_backchannel_POST(
        sender_url + "/agent/command/",
        "connection",
        operation="send-ping",
        id=sender_connection_id,
        data=data,
    )
    assert resp_status == 200, f"resp_status {resp_status} is not 200; {resp_text}"


@then('"{inviter}" is in the state of complete')
def step_impl(context, inviter):
    # get connection and verify status
    assert expected_agent_state(
        context.config.userdata.get(inviter),
        "connection",
        context.connection_id_dict[inviter][context.invitee_name],
        "complete",
    )


@given('"{inviter}" generated a single-use connection invitation')
def step_impl(context, inviter):
    context.execute_steps(
        f"""
        When "{inviter}" generates a connection invitation
    """
    )


@given('"{invitee}" received the connection invitation')
def step_impl(context, invitee):
    context.execute_steps(
        f"""
        When "{invitee}" receives the connection invitation
    """
    )


@given('"{invitee}" sent a connection request to "{inviter}"')
def step_impl(context, invitee, inviter):
    context.execute_steps(
        f"""
        When "{invitee}" sends a connection request to "{inviter}"
    """
    )


@given('"{inviter}" and "{invitee}" have a connection')
def step_impl(context, inviter, invitee):
    context.execute_steps(
        f"""
        When "{invitee}" sends trustping to "{inviter}"
        Then "{inviter}" and "{invitee}" have a connection
        """
    )


@when(
    '"{inviteinterceptor}" sends a connection request to "{inviter}" based on the connection invitation'
)
def step_impl(context, inviteinterceptor, inviter):
    context.execute_steps(
        f"""
        When "{inviteinterceptor}" receives the connection invitation
    """
    )
    inviteinterceptor_url = context.config.userdata.get(inviteinterceptor)
    inviteinterceptor_connection_id = context.connection_id_dict[inviteinterceptor][
        inviter
    ]

    # get connection and verify status before call
    assert expected_agent_state(
        inviteinterceptor_url, "connection", inviteinterceptor_connection_id, "invited"
    )

    (resp_status, resp_text) = agent_backchannel_POST(
        inviteinterceptor_url + "/agent/command/",
        "connection",
        operation="accept-invitation",
        id=inviteinterceptor_connection_id,
    )
    assert resp_status == 200, f"resp_status {resp_status} is not 200; {resp_text}"

    # get connection and verify status
    assert expected_agent_state(
        inviteinterceptor_url,
        "connection",
        inviteinterceptor_connection_id,
        "requested",
    )


@then('"{inviter}" sends a request_not_accepted error')
def step_impl(context, inviter):
    inviter_url = context.config.userdata.get(inviter)
    inviter_connection_id = context.connection_id_dict[inviter][context.invitee_name]

    # TODO It is expected that accept-request should send a request not accepted error, not a 500
    (resp_status, resp_text) = agent_backchannel_POST(
        inviter_url + "/agent/command/",
        "connection",
        operation="accept-request",
        id=inviter_connection_id,
    )
    # TODO once bug 418 has been fixed change this assert to the proper response code.
    # bug reference URL: https://app.zenhub.com/workspaces/von---verifiable-organization-network-5adf53987ccbaa70597dbec0/issues/hyperledger/aries-cloudagent-python/418
    assert resp_status == 406, f"resp_status {resp_status} is not 406; {resp_text}"
    # assert resp_status == 500

    # Invitee should still be active based on the inviter connection id.
    # assert connection_status(inviter_url, inviter_connection_id, ["complete"])


@given('"{inviter}" generated a multi-use connection invitation')
def step_impl(context, inviter):
    context.execute_steps(
        f"""
        When "{inviter}" generates a connection invitation
    """
    )


@when('"{sender}" and "{receiver}" complete the connection process')
def step_impl(context, sender, receiver):
    context.execute_steps(
        f"""
         When "{receiver}" receives the connection invitation
         And "{receiver}" sends a connection request to "{sender}"
         And "{sender}" receives the connection request
         And "{sender}" sends a connection response to "{receiver}"
         And "{receiver}" receives the connection response
         And "{receiver}" sends trustping to "{sender}"
    """
    )


@then('"{inviter}" and "{invitee}" are able to complete the connection')
def step_impl(context):
    raise NotImplementedError(
        'STEP: Then "Acme" and "Bob" are able to complete the connection'
    )


@then('"{receiver}" and "{sender}" have another connection')
def step_impl(context, receiver, sender):
    context.execute_steps(
        f"""
        Then "{sender}" and "{receiver}" have a connection
    """
    )


@given('"Bob" has Invalid DID Method')
def step_impl(context):
    raise NotImplementedError('STEP: Given "Bob" has Invalid DID Method')


@then('"Acme" sends an request not accepted error')
def step_impl(context):
    raise NotImplementedError('STEP: Then "Acme" sends an request not accepted error')


@then('the state of "Acme" is reset to Null')
def step_impl(context):
    raise NotImplementedError('STEP: Then the state of "Acme" is reset to Null')


@then('the state of "Bob" is reset to Null')
def step_impl(context):
    raise NotImplementedError('STEP: Then the state of "Bob" is reset to Null')


@given('"Bob" has unknown endpoint protocols')
def step_impl(context):
    raise NotImplementedError('STEP: Given "Bob" has unknown endpoint protocols')
