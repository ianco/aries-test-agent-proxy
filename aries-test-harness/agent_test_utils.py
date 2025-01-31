import datetime
import time
from typing import Optional


def create_non_revoke_interval(timeframe):
    # timeframe containes two variables, the To and from of the non-revoked to and from parameters in the send presentation request message
    # The to and from timeframe variables are always relative to now.
    # The to and from time is represented as a total number of seconds from Unix Epoch
    # Deconstruct the timeframe and add it to the context to be used in the request later.
    # putting timefrom here where the revoke happens just in case it is needed. It may not and could be removed from here and added to the request step.
    #
    # Timeframe examples:
    # -86400:+86400
    # now:now
    # -86400:0
    # :now (openended from)
    # now: (openended to)

    timeframe_list = timeframe.split(":")
    from_reference = timeframe_list[0]
    to_reference = timeframe_list[1]

    if (from_reference == "now") or (from_reference == ""):
        if from_reference == "now":
            from_interval = int(time.time())
        if from_reference == "":
            from_interval = None
        # from_interval = from_reference
    else:
        from_interval = int(from_reference) + int(time.time())

    if (to_reference == "now") or (to_reference == ""):
        if to_reference == "now":
            to_reference = int(time.time())
        to_interval = to_reference
    else:
        to_interval = int(to_reference) + int(time.time())

    return {"non_revoked": {"from": from_interval, "to": to_interval}}


def get_relative_timestamp_to_epoch(timestamp):
    # timestamps are always relative to now. + or - is represented in seconds from Unix Epoch.
    # Valid timestsamps are
    #  now
    #  +###### ie +86400
    #  -###### ie -86400

    if timestamp == "now":
        epoch_time = int(time.time())
    else:
        epoch_time = int(timestamp) + int(time.time())

    return epoch_time


def format_cred_proposal_by_aip_version(
    context, aip_version, cred_data, connection_id: Optional[str] = None, filters=None, did_for_id=None
):
    if aip_version == "AIP20":
        filters = amend_filters_with_runtime_data(context, filters, did_for_id)
        credential_proposal = {
            "credential_preview": {
                "@type": "https://didcomm.org/issue-credential/2.0/credential-preview",
                "attributes": cred_data,
            },
            "filter": filters,
        }

        if connection_id:
            credential_proposal["connection_id"] = connection_id

    return credential_proposal

def get_schema_name(context):
    if context.anoncreds:
        return context.schema["schema"]["name"]
    else:
        return context.schema["schema_name"]


def amend_filters_with_runtime_data(context, filters, did_for_id=None):
    schema_name = get_schema_name(context)
    # This method will need comdification as new types of filters are used. Intially "indy" is used.
    if "indy" in filters:
        if (
            "schema_issuer_did" in filters["indy"]
            and filters["indy"]["schema_issuer_did"] == "replace_me"
        ):
            filters["indy"]["schema_issuer_did"] = context.issuer_did_dict[schema_name]
        if (
            "issuer_did" in filters["indy"]
            and filters["indy"]["issuer_did"] == "replace_me"
        ):
            filters["indy"]["issuer_did"] = context.issuer_did_dict[schema_name]
        if (
            "cred_def_id" in filters["indy"]
            and filters["indy"]["cred_def_id"] == "replace_me"
        ):
            filters["indy"]["cred_def_id"] = context.issuer_credential_definition_dict[schema_name]["id"]
        if (
            "schema_id" in filters["indy"]
            and filters["indy"]["schema_id"] == "replace_me"
        ):
            filters["indy"]["schema_id"] = context.issuer_schema_dict[schema_name]["id"]

    if "anoncreds" in filters:
        if (
            "schema_issuer_did" in filters["anoncreds"]
            and filters["anoncreds"]["schema_issuer_did"] == "replace_me"
        ):
            filters["anoncreds"]["schema_issuer_did"] = context.issuer_did_dict[schema_name]
        if (
            "issuer_did" in filters["anoncreds"]
            and filters["anoncreds"]["issuer_did"] == "replace_me"
        ):
            filters["anoncreds"]["issuer_did"] = context.issuer_did_dict[schema_name]
        if (
            "cred_def_id" in filters["anoncreds"]
            and filters["anoncreds"]["cred_def_id"] == "replace_me"
        ):
            filters["anoncreds"]["cred_def_id"] = context.issuer_credential_definition_dict[schema_name]["id"]
        if (
            "schema_id" in filters["anoncreds"]
            and filters["anoncreds"]["schema_id"] == "replace_me"
        ):
            filters["anoncreds"]["schema_id"] = context.issuer_schema_dict[schema_name]["id"]

    if "json-ld" in filters:
        json_ld = filters.get("json-ld")
        credential = json_ld.get("credential")
        options = json_ld.get("options")

        issuer = context.issuer_did_dict[schema_name]

        if "issuer" in credential:
            # "issuer": "replace_me"
            if credential.get("issuer") == "replace_me":
                credential["issuer"] = issuer
            # "issuer": { "id": "replace_me" }
            elif credential.get("issuer", {}).get("id") == "replace_me":
                credential["issuer"]["id"] = issuer
        if options.get("proofType") == "replace_me":
            options["proofType"] = context.proof_type
        if "issuanceDate" in credential:
            created_datetime = (
                str(
                    datetime.datetime.now()
                    .replace(microsecond=0)
                    .isoformat(timespec="seconds")
                )
                + "Z"
            )
            credential["issuanceDate"] = created_datetime
        # Check if "credentialSubject" is in json_ld and then check if "id" is not already in "credentialSubject"
        if did_for_id and "credentialSubject" in json_ld["credential"] and "id" not in json_ld["credential"]["credentialSubject"]:
            json_ld["credential"]["credentialSubject"]["id"] = did_for_id

    return filters


def amend_presentation_definition_with_runtime_data(context, presentation_definition):
    # presentation definition is outer object with presentation definition and options
    pd = presentation_definition.get("presentation_definition", {})
    format = pd.get("format", {})
    ldp_vp_proof_type = format.get("ldp_vp", {}).get("proof_type", [])

    # Only ldp_vp with a single proof type replaced is supported ATM
    if "replace_me" in ldp_vp_proof_type:
        index = ldp_vp_proof_type.index("replace_me")
        ldp_vp_proof_type[index] = context.proof_type

        presentation_definition["presentation_definition"]["format"]["ldp_vp"][
            "proof_type"
        ] = ldp_vp_proof_type

    return presentation_definition
