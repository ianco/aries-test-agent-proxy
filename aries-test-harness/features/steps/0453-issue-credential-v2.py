import json
from time import sleep

from agent_backchannel_client import agent_backchannel_GET, agent_backchannel_POST
from agent_test_utils import format_cred_proposal_by_aip_version, get_schema_name
from behave import given, then, when

CRED_FORMAT_INDY = "indy"
CRED_FORMAT_JSON_LD = "json-ld"
CRED_FORMAT_ANONCREDS = "anoncreds"


def setup_schemas_for_issuance(context, credential_data):
    # Prepare schemas for usage
    for schema in context.schema_dict:
        try:
            credential_data_json_file = open(
                "features/data/cred_data_" + schema.lower() + ".json"
            )
            credential_data_json = json.load(credential_data_json_file)
            context.credential_data_dict[schema] = credential_data_json[
                credential_data
            ]["attributes"]

            context.credential_data = context.credential_data_dict[schema]
            context.schema = context.schema_dict[schema]
        except FileNotFoundError:
            print(
                FileNotFoundError
                + ": features/data/cred_data_"
                + schema.lower()
                + ".json"
            )

        if "AIP20" in context.tags or "DIDComm-V2" in context.tags:
            context.filters_dict[schema] = credential_data_json[credential_data][
                "filters"
            ]
            context.filters = context.filters_dict[schema]

@given('"{issuer}" is ready to issue a "{cred_format}" credential')
def step_impl(context, issuer: str, cred_format: str = CRED_FORMAT_INDY):
    if cred_format == CRED_FORMAT_INDY or cred_format == CRED_FORMAT_ANONCREDS:
        # Call legacy indy ready to issue credential step
        context.execute_steps(
            f"""
            Given "{issuer}" has a public did
            And "{issuer}" is ready to issue a credential
        """
        )
    elif cred_format == CRED_FORMAT_JSON_LD:
        issuer_url = context.config.userdata.get(issuer)

        data = {"did_method": context.did_method, "proof_type": context.proof_type}

        (resp_status, resp_text) = agent_backchannel_POST(
            issuer_url + "/agent/command/",
            "issue-credential-v2",
            operation="prepare-json-ld",
            data=data,
        )

        assert (
            resp_status == 200
        ), f"issue-credential-v2/prepare-json-ld: resp_status {resp_status} is not 200; {resp_text}"
        resp_json = json.loads(resp_text)

        # TODO: it would be nice to not depend on the schema name for the issuer did dict
        context.issuer_did_dict[get_schema_name(context)] = resp_json["did"]
    else:
        raise Exception(f"Unknown credential format {cred_format}")


@given(
    '"{holder}" proposes a "{cred_format}" credential to "{issuer}" with {credential_data}'
)
@when(
    '"{holder}" proposes a "{cred_format}" credential to "{issuer}" with {credential_data}'
)
def step_impl(context, holder, cred_format, issuer, credential_data):
    # Set up schemas / filters for issuance
    setup_schemas_for_issuance(context, credential_data)

    holder_url = context.config.userdata.get(holder)

    if "AIP20" in context.tags or "DIDComm-V2" in context.tags:
        # We only want to send data for the cred format being used
        assert (
            cred_format in context.filters
        ), f"credential data has no filter for cred format {cred_format}"
        filters = {cred_format: context.filters[cred_format]}

        # It the credential format is json-ls then get a holder did for the credentialSubject.id by calling the prepare-json-ld command.
        if cred_format == CRED_FORMAT_JSON_LD:
            holder_did_for_id = create_did_for_id(context, holder, cred_format)
        else:
            holder_did_for_id = None

        # This call may need to be formated by cred_format instead of version. Reassess when more types are used.
        credential_offer = format_cred_proposal_by_aip_version(
            context,
            "AIP20",
            context.credential_data,
            context.connection_id_dict[holder][issuer],
            filters,
            holder_did_for_id,
        )

    (resp_status, resp_text) = agent_backchannel_POST(
        holder_url + "/agent/command/",
        "issue-credential-v2",
        operation="send-proposal",
        data=credential_offer,
    )
    assert resp_status == 200, f"resp_status {resp_status} is not 200; {resp_text}"
    resp_json = json.loads(resp_text)

    # Get the thread ID from the response text.
    context.cred_thread_id = resp_json["thread_id"]


def create_did_for_id(context, agent: str, cred_format: str = CRED_FORMAT_INDY):
    if cred_format == CRED_FORMAT_JSON_LD:
        agent_url = context.config.userdata.get(agent)

        data = {"did_method": context.did_method, "proof_type": context.proof_type}

        (resp_status, resp_text) = agent_backchannel_POST(
            agent_url + "/agent/command/",
            "issue-credential-v2",
            operation="prepare-json-ld",
            data=data,
        )

        assert (
            resp_status == 200
        ), f"issue-credential-v2/prepare-json-ld: resp_status {resp_status} is not 200; {resp_text}"
        resp_json = json.loads(resp_text)

        return resp_json["did"]
    else:
        raise Exception(f"Unknown credential format {cred_format}")

@given('"{issuer}" offers the "{cred_format}" credential')
@when('"{issuer}" offers the "{cred_format}" credential')
def step_impl(context, issuer, cred_format):
    issuer_url = context.config.userdata.get(issuer)

    if context.cred_thread_id:
        # If context has the credential thread id then the proposal was done.
        (resp_status, resp_text) = agent_backchannel_POST(
            issuer_url + "/agent/command/",
            "issue-credential-v2",
            operation="send-offer",
            id=context.cred_thread_id,
        )
        assert resp_status == 200, f"resp_status {resp_status} is not 200; {resp_text}"
        resp_json = json.loads(resp_text)
    # if context does not have the credential thread id then the proposal was not the starting point for the protocol.
    else:
        cred_data = context.credential_data

        # We only want to send data for the cred format being used
        assert (
            cred_format in context.filters
        ), f"credential data has no filter for cred format {cred_format}"
        filters = {cred_format: context.filters[cred_format]}

        credential_offer = format_cred_proposal_by_aip_version(
            context,
            "AIP20",
            cred_data,
            context.connection_id_dict[issuer][context.holder_name],
            filters,
        )

        (resp_status, resp_text) = agent_backchannel_POST(
            issuer_url + "/agent/command/",
            "issue-credential-v2",
            operation="send-offer",
            data=credential_offer,
        )
        assert resp_status == 200, f"resp_status {resp_status} is not 200; {resp_text}"
        resp_json = json.loads(resp_text)
        context.cred_thread_id = resp_json["thread_id"]

@given('"{issuer}" creates a "{cred_format}" credential offer with {credential_data}')
@when('"{issuer}" creates a "{cred_format}" credential offer with {credential_data}')
@given('"{issuer}" creates an "{cred_format}" credential offer with {credential_data}')
@when('"{issuer}" creates an "{cred_format}" credential offer with {credential_data}')
def step_impl(context, issuer, cred_format, credential_data):
    # Set up schemas / filters for issuance
    setup_schemas_for_issuance(context, credential_data)

    issuer_url = context.config.userdata.get(issuer)


    cred_data = context.credential_data

    # We only want to send data for the cred format being used
    assert (
        cred_format in context.filters
    ), f"credential data has no filter for cred format {cred_format}"
    filters = {cred_format: context.filters[cred_format]}

    credential_offer = format_cred_proposal_by_aip_version(
        context,
        "AIP20",
        cred_data,
        None,
        filters,
    )

    (resp_status, resp_text) = agent_backchannel_POST(
        issuer_url + "/agent/command/",
        "issue-credential-v2",
        operation="create-offer",
        data=credential_offer,
    )
    assert resp_status == 200, f"resp_status {resp_status} is not 200; {resp_text}"
    resp_json = json.loads(resp_text)

    assert "record" in resp_json
    context.cred_thread_id = resp_json["record"]["thread_id"]
    context.credential_offer = resp_json["message"]


@when('"{holder}" requests the "{cred_format}" credential')
def step_impl(context, holder, cred_format):
    holder_url = context.holder_url

    # # If @indy then we can be sure we cannot start the protocol from this command. We can be sure that we have previously
    # # reveived the thread_id.
    # if "Indy" in context.tags:
    #     sleep(1)
    (resp_status, resp_text) = agent_backchannel_POST(
        holder_url + "/agent/command/",
        "issue-credential-v2",
        operation="send-request",
        id=context.cred_thread_id,
    )

    # # If we are starting from here in the protocol you won't have the cred_ex_id or the thread_id
    # else:
    #     (resp_status, resp_text) = agent_backchannel_POST(holder_url + "/agent/command/", "issue-credential-v2", operation="send-request", id=context.connection_id_dict[holder][context.issuer_name])

    assert resp_status == 200, f"resp_status {resp_status} is not 200; {resp_text}"


@when('"{issuer}" issues the "{cred_format}" credential')
def step_impl(context, issuer, cred_format):
    issuer_url = context.config.userdata.get(issuer)

    credential_issue = {"comment": "issuing credential"}

    (resp_status, resp_text) = agent_backchannel_POST(
        issuer_url + "/agent/command/",
        "issue-credential-v2",
        operation="issue",
        id=context.cred_thread_id,
        data=credential_issue,
    )
    assert resp_status == 200, f"resp_status {resp_status} is not 200; {resp_text}"


@when('"{holder}" acknowledges the "{cred_format}" credential issue')
def step_impl(context, holder, cred_format):
    holder_url = context.config.userdata.get(holder)

    sleep(1)
    (resp_status, resp_text) = agent_backchannel_POST(
        holder_url + "/agent/command/",
        "issue-credential-v2",
        operation="store",
        id=context.cred_thread_id,
    )
    assert resp_status == 200, f"resp_status {resp_status} is not 200; {resp_text}"
    resp_json = json.loads(resp_text)
    state = resp_json["state"]
    assert state == "done", f"state is '{state}', expected 'done'"

    credential_id = find_credential_id(resp_json)
    context.credential_id_dict[get_schema_name(context)].append(credential_id)

    # Verify issuer status
    # TODO This is returning none instead of Done. Should this be the case. Needs investigation.
    # assert expected_agent_state(context.issuer_url, "issue-credential-v2", context.cred_thread_id, "done")

    # if the credential supports revocation, get the Issuers webhook callback JSON from the store command
    # From that JSON save off the credential revocation identifier, and the revocation registry identifier.
    if context.support_revocation:
        (resp_status, resp_text) = agent_backchannel_GET(
            context.config.userdata.get(context.issuer_name) + "/agent/response/",
            "revocation-registry",
            id=context.cred_thread_id,
        )
        assert resp_status == 200, f"resp_status {resp_status} is not 200; {resp_text}"
        resp_json = json.loads(resp_text)
        context.cred_rev_id = resp_json["revocation_id"]
        context.rev_reg_id = resp_json["revoc_reg_id"]

def find_credential_id(data):
    if isinstance(data, dict):
        for key, value in data.items():
            if key == "credential_id":
                return value
            result = find_credential_id(value)
            if result is not None:
                return result
    elif isinstance(data, list):
        for item in data:
            result = find_credential_id(item)
            if result is not None:
                return result
    return None

@then('"{holder}" has the "{cred_format}" credential issued')
def step_impl(context, holder, cred_format):
    holder_url = context.config.userdata.get(holder)

    cred_id = context.credential_id_dict[get_schema_name(context)][-1]
    # get the credential from the holders wallet
    (resp_status, resp_text) = agent_backchannel_GET(
        holder_url + "/agent/command/",
        "credential",
        id=cred_id,
    )
    assert resp_status == 200, f"resp_status {resp_status} is not 200; {resp_text}"
    resp_json = json.loads(resp_text)

    if cred_format == CRED_FORMAT_INDY or cred_format == CRED_FORMAT_ANONCREDS:
        # assert resp_json["schema_id"] == context.issuer_schema_id_dict[context.schema["schema_name"]]
        # assert resp_json["cred_def_id"] == context.credential_definition_id_dict[context.schema["schema_name"]]
        assert (
            resp_json["referent"] == cred_id
        )
    elif cred_format == CRED_FORMAT_JSON_LD:
        # TODO: do not use schema name for credential_id_dict
        assert (
            resp_json["credential_id"] == cred_id
        )


@when(
    '"{holder}" negotiates the offer with another proposal of the "{cred_format}" credential to "{issuer}"'
)
def step_impl(context, holder, cred_format, issuer):
    context.execute_steps(
        f"""
        When "{holder}" proposes a "{cred_format}" credential to "{issuer}"
    """
    )
