from behave import *
import json
from agent_backchannel_client import agent_backchannel_GET, agent_backchannel_POST, connection_status

# This step is defined in another feature file
# Given "Alice" and "Bob" have an existing connection


SCHEMA_TEMPLATE = {
    "schema_name": "test_schema.",
    "schema_version": "1.0.0",
    "attributes": ["attr_1","attr_2","attr_3"],
}

CRED_DEF_TEMPLATE = {
  "support_revocation": False,
  "schema_id": "",
  "tag": "default"
}

@given('"{issuer}" has an existing schema and credential definition')
def step_impl(context, issuer):
    issuer_url = context.config.userdata.get(issuer)

    # pre-requisite is that the agent has a public DID and can issue
    # TODO fetch public DID and verify it exists

    if not "issuer_schema_id" in context:
        schema = SCHEMA_TEMPLATE.copy()
        schema["schema_name"] = schema["schema_name"] + issuer
        data = json.dumps(schema)
        (resp_status, resp_text) = agent_backchannel_POST(issuer_url + "/agent/command/", "schema", data=schema)
        assert resp_status == 200

        resp_json = json.loads(resp_text)
        context.issuer_schema_id = resp_json["schema_id"]

    # TODO fetch schema and verify it exists

    if not "credential_definition_id" in context:
        cred_def = CRED_DEF_TEMPLATE.copy()
        cred_def["schema_id"] = context.issuer_schema_id
        data = json.dumps(cred_def)
        (resp_status, resp_text) = agent_backchannel_POST(issuer_url + "/agent/command/", "credential-definition", data=cred_def)
        assert resp_status == 200

        resp_json = json.loads(resp_text)
        context.credential_definition_id = resp_json["credential_definition_id"]

    # TODO fetch cred def and verify it exists

@when('"{issuer}" initiates an automated credential issuance')
def step_impl(context, issuer):
    issuer_url = context.config.userdata.get(issuer)
    issuer_schema_id = context.issuer_schema_id
    issuer_credential_definition_id = context.credential_definition_id

    (resp_status, resp_text) = agent_backchannel_GET(issuer_url + "/agent/command/", "schema", id=issuer_schema_id)
    assert resp_status == 200

    resp_json = json.loads(resp_text)
    issuer_schema = resp_json["schema"]

    (resp_status, resp_text) = agent_backchannel_GET(issuer_url + "/agent/command/", "credential-definition", id=issuer_credential_definition_id)
    assert resp_status == 200

    resp_json = json.loads(resp_text)
    issuer_credential_definition = resp_json["schema"]

    pass

@when('"{issuer}" sends a credential offer')
def step_impl(context, issuer):
    pass

@when('"{receiver}" sends a credential request')
def step_impl(context, receiver):
    pass

@when('"{issuer}" issues a credential')
def step_impl(context, issuer):
    pass

@when('"{receiver}" receives and acknowledges the credential')
def step_impl(context, receiver):
    pass

@then('"{issuer}" has an acknowledged credential issue')
def step_impl(context, issuer):
    pass

@then('"{issuer}" has received a credential')
def step_impl(context, issuer):
    pass
