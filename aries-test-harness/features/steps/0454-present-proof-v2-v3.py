from typing import Any, Dict
from behave import *
import json
from agent_backchannel_client import agent_backchannel_POST, expected_agent_state
from agent_test_utils import (
    get_relative_timestamp_to_epoch,
    amend_presentation_definition_with_runtime_data,
)
from distutils.util import strtobool

def prepare_proof_request(context: Any, request_for_proof: str) -> Dict[str, Any]:
    try:
        request_for_proof_json_file = open(
            "features/data/" + request_for_proof + ".json"
        )
        request_for_proof_json = json.load(request_for_proof_json_file)
        context.request_for_proof = request_for_proof_json["presentation_request"]

    except FileNotFoundError:
        print(f"FileNotFoundError: features/data/{request_for_proof}.json")

    data = None

    # check for a schema template already loaded in the context. If it is, it was loaded from an external Schema, so use it.
    if context.request_for_proof:
        data = context.request_for_proof

        if context.current_cred_format == "indy" or context.current_cred_format == "anoncreds":
            if context.non_revoked_timeframe:
                data["non_revoked"] = context.non_revoked_timeframe["non_revoked"]

        elif context.current_cred_format == "json-ld":
            data = amend_presentation_definition_with_runtime_data(context, data)
        else:
            raise Exception(f"Unknown cred format {context.current_cred_format}")

    presentation_request = {
        "presentation_request": {
            "format": context.current_cred_format,
            "comment": "This is a comment for the request for presentation.",
            "data": data,
        }
    }

    return presentation_request


@given(
    '"{prover}" has an issued credential with formats from {issuer} with {credential_data}'
)
def step_impl(context, prover, issuer, credential_data):
    # assign the credential data to the context for use in the credential offer or proposal.
    if credential_data != None:
        for schema in context.schema_dict:
            try:
                credential_data_json_file = open(
                    "features/data/cred_data_" + schema.lower() + ".json"
                )
                credential_data_json = json.load(credential_data_json_file)
                context.credential_data_dict[schema] = credential_data_json[
                    credential_data
                ]["attributes"]

            except FileNotFoundError:
                print(
                    FileNotFoundError
                    + ": features/data/cred_data_"
                    + schema.lower()
                    + ".json"
                )

    # Check if a connection between the players has already been established in this test.
    should_create_connection = (
        prover not in context.connection_id_dict
        or issuer not in context.connection_id_dict[prover]
    )

    # Set the cred format from the feature tags.
    # TODO Check of the Prefix CredFormat exists, throw and error if not. It is mandatory
    if "CredFormat_Indy" in context.tags:
        context.current_cred_format = "indy"
    elif "CredFormat_Anoncreds" in context.tags:
        context.current_cred_format = "anoncreds"
    elif "CredFormat_JSON-LD" in context.tags:
        context.current_cred_format = "json-ld"

    # make sure the issuer has the credential definition
    # If there is a schema_dict then we are working with multiple credential types, loop as many times as
    # there are schemas and add the schema to context as the issue cred tests expect.
    if len(context.schema_dict.items()) == 0:
        # Schema not defined in feature file. use @SchemaName as a feature tag that points to a corresponding file
        raise Exception(
            "Schema not tagged in Feature File Scenario. Use @SchemaName as a feature tag that points to a corresponding file."
        )

    for schema in context.schema_dict:
        context.support_revocation = context.support_revocation_dict[schema]
        context.schema = context.schema_dict[schema]
        context.execute_steps(
            f"""
            Given "{issuer}" is ready to issue a "{context.current_cred_format}" credential
        """
        )

    # setup the holder and issuer for the issue cred scenario below. The data table in the tests does not setup a holder.
    # The prover is also the holder.
    context.holder_url = context.config.userdata.get(prover)
    context.holder_name = prover
    assert context.holder_url is not None and len(context.holder_url) > 0
    # The issuer was not in the data table, it was in the gherkin scenario outline examples, so get it and assign it.
    context.issuer_url = context.config.userdata.get(issuer)
    context.issuer_name = issuer
    assert context.issuer_url is not None and len(context.issuer_url) > 0

    use_didcomm_v2 = "DIDComm-V2" in context.tags


    # issue the credential to prover
    # If there is a schema_dict then we are working with mulitple credential types, loop as many times as
    # there are schemas and add the schema to context as the issue cred tests expect.
    if "CredProposalStart" in context.tags:
        context_steps_start = f"""
            When "{prover}" proposes a "{context.current_cred_format}" credential to "{issuer}" with {credential_data}
            """
    else:
        context_steps_start = ""

    if should_create_connection:
        if use_didcomm_v2:
            context_steps_start = (
                f"""
                Given "{issuer}" creates a didcomm v2 invitation
                And "{prover}" accepts the didcomm v2 invitation from "{issuer}"
                """ +
                context_steps_start +
                f"""
                When "{issuer}" has received a didcomm v2 message from "{prover}" and created a connection
                """
            )
        else:
            context.execute_steps(
                f"""
                Given "{issuer}" and "{prover}" have an existing connection
            """
            )


    for schema in context.schema_dict:
        context.credential_data = context.credential_data_dict[schema]
        context.schema = context.schema_dict[schema]
        context_steps = (
            context_steps_start
            + f"""
            When "{issuer}" offers the "{context.current_cred_format}" credential
            And "{prover}" requests the "{context.current_cred_format}" credential
            And  "{issuer}" issues the "{context.current_cred_format}" credential
            And "{prover}" acknowledges the "{context.current_cred_format}" credential issue
            Then "{prover}" has the "{context.current_cred_format}" credential issued
        """
        )
        context.execute_steps(context_steps)


@when(
    '"{prover}" sends a presentation proposal to "{verifier}"'
)
def step_impl(context, verifier: str, prover: str):
    presentation_proposal = {
        "presentation_proposal": {
            "comment": "This is a comment for the proposed presentation.",
            "connection_id": context.connection_id_dict[prover][verifier]
        }
    }

    if "PresentProofV3" in context.tags:
        proof_endpoint = "proof-v3"
    else:
        proof_endpoint = "proof-v2"

    # send presentation proposal
    (resp_status, resp_text) = agent_backchannel_POST(
        context.prover_url + "/agent/command/",
        proof_endpoint,
        operation="send-proposal",
        data=presentation_proposal,
    )

    assert resp_status == 200, f"resp_status {resp_status} is not 200; {resp_text}"
    resp_json = json.loads(resp_text)

    context.presentation_thread_id = resp_json["thread_id"]


@when(
    '"{verifier}" sends a {request_for_proof} presentation with formats to "{prover}"'
)
def step_impl(context, verifier, request_for_proof, prover):
    presentation_request = prepare_proof_request(context, request_for_proof)

    use_v3 = "PresentProofV3" in context.tags

    if use_v3:
        if context.presentation_thread_id:
            # send presentation request in response to proposal
            (resp_status, resp_text) = agent_backchannel_POST(
                context.verifier_url + "/agent/command/",
                "proof-v3",
                operation="send-request",
                id=context.presentation_thread_id,
                data=presentation_request,
            )

            assert resp_status == 200, f"resp_status {resp_status} is not 200; {resp_text}"
        else:
            presentation_request[
                "connection_id"
            ] = context.connection_id_dict[verifier][prover]

            # send presentation request
            (resp_status, resp_text) = agent_backchannel_POST(
                context.verifier_url + "/agent/command/",
                "proof-v3",
                operation="send-request",
                data=presentation_request,
            )
    else:
        presentation_request["presentation_request"][
            "connection_id"
        ] = context.connection_id_dict[verifier][prover]

        # send presentation request
        (resp_status, resp_text) = agent_backchannel_POST(
            context.verifier_url + "/agent/command/",
            "proof-v2",
            operation="send-request",
            data=presentation_request,
        )

    assert resp_status == 200, f"resp_status {resp_status} is not 200; {resp_text}"
    resp_json = json.loads(resp_text)

    if not context.presentation_thread_id:
        # save off anything that is returned in the response to use later?
        context.presentation_thread_id = resp_json["thread_id"]

@when(
    '"{verifier}" creates a "{request_for_proof}" proof request'
)
def step_impl(context, verifier: str, request_for_proof: str):
    presentation_request = prepare_proof_request(context, request_for_proof)

    # send presentation request
    (resp_status, resp_text) = agent_backchannel_POST(
        context.verifier_url + "/agent/command/",
        "proof-v2",
        operation="create-request",
        data=presentation_request,
    )

    assert resp_status == 200, f"resp_status {resp_status} is not 200; {resp_text}"
    resp_json = json.loads(resp_text)

    assert "record" in resp_json
    context.presentation_thread_id = resp_json["record"]["thread_id"]
    context.proof_request = resp_json["message"]    

@when('"{prover}" makes the {presentation} of the proof with formats')
def step_impl(context, prover, presentation):
    # Open the presentation json file
    try:
        presentation_json_file = open("features/data/" + presentation + ".json")
        presentation_json = json.load(presentation_json_file)
        context.presentation = presentation_json["presentation"]

    except FileNotFoundError:
        print(FileNotFoundError + ": features/data/" + presentation + ".json")

    prover_url = context.prover_url

    if context.presentation:
        presentation = context.presentation

        if context.current_cred_format == "indy" or context.current_cred_format == "anoncreds":
            # Find the cred ids and add the actual cred id into the presentation
            try:
                for requested_attribute in presentation[
                    "requested_attributes"
                ].values():
                    cred_type_name = requested_attribute["cred_type_name"]
                    requested_attribute["cred_id"] = context.credential_id_dict[
                        cred_type_name
                    ][-1]

                    # Update timestamp in requested attribute
                    if "timestamp" in requested_attribute:
                        relative_timestamp = requested_attribute["timestamp"]
                        requested_attribute[
                            "timestamp"
                        ] = get_relative_timestamp_to_epoch(relative_timestamp)

                    # Remove the cred_type_name from this part of the presentation since it won't be needed in the actual request.
                    requested_attribute.pop("cred_type_name")
            except KeyError:
                pass

            try:
                for requested_predicate in presentation[
                    "requested_predicates"
                ].values():
                    # Get the schema name from the loaded presentation for each requested predicates
                    cred_type_name = requested_predicate["cred_type_name"]
                    requested_predicate["cred_id"] = context.credential_id_dict[
                        cred_type_name
                    ][-1]

                    # Update timestamp in requested attribute
                    if "timestamp" in requested_predicate:
                        relative_timestamp = requested_predicate["timestamp"]
                        requested_predicate[
                            "timestamp"
                        ] = get_relative_timestamp_to_epoch(relative_timestamp)

                    # Remove the cred_type_name from this part of the presentation since it won't be needed in the actual request.
                    requested_predicate.pop("cred_type_name")
            except KeyError:
                pass

        elif context.current_cred_format == "json-ld":
            # All good
            cred_type_name = presentation.get("cred_type_name")
            record_ids = presentation.get("record_ids", {})

            new_record_ids = {}
            for (input_descriptor_id, record_ids) in record_ids.items():
                new_record_ids[input_descriptor_id] = [
                    context.credential_id_dict[cred_type_name][-1]
                    for cred_type_name in record_ids
                ]

            presentation["record_ids"] = new_record_ids
        else:
            raise Exception(f"Unknown format {context.current_cred_format}")

        presentation["format"] = context.current_cred_format

    use_v3 = "PresentProofV3" in context.tags

    if use_v3:
        proof_endpoint = "proof-v3"
    else:
        proof_endpoint = "proof-v2"

    (resp_status, resp_text) = agent_backchannel_POST(
        prover_url + "/agent/command/",
        proof_endpoint,
        operation="send-presentation",
        id=context.presentation_thread_id,
        data=presentation,
    )
    assert resp_status == 200, f"resp_status {resp_status} is not 200; {resp_text}"


@when('"{verifier}" acknowledges the proof with formats')
def step_impl(context, verifier):
    verifier_url = context.verifier_url

    use_v3 = "PresentProofV3" in context.tags

    if use_v3:
        proof_endpoint = "proof-v3"
    else:
        proof_endpoint = "proof-v2"

    (resp_status, resp_text) = agent_backchannel_POST(
        verifier_url + "/agent/command/",
        proof_endpoint,
        operation="verify-presentation",
        id=context.presentation_thread_id,
    )
    assert resp_status == 200, f"resp_status {resp_status} is not 200; {resp_text}"
    resp_json = json.loads(resp_text)
    assert resp_json["state"] == "done"

    # Add the verified property returned to the credential verification dictionary to check in subsequent steps. Key by presentation thread id
    context.credential_verification_dict[
        context.presentation_thread_id
    ] = strtobool(resp_json["verified"])


@then('"{prover}" has the proof with formats verified')
def step_impl(context, prover):
    use_v3 = "PresentProofV3" in context.tags

    if use_v3:
        proof_endpoint = "proof-v3"
    else:
        proof_endpoint = "proof-v2"

    # check the state of the presentation from the prover's perspective
    assert expected_agent_state(
        context.prover_url, proof_endpoint, context.presentation_thread_id, "done"
    )

    # Check the status of the verification in the verify-presentation call. Should be True
    if context.presentation_thread_id in context.credential_verification_dict:
        assert (
            context.credential_verification_dict[context.presentation_thread_id] == True
        )
