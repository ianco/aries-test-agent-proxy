@RFC0453 @AIP20
Feature: RFC 0453 Aries Agent Issue Credential v2

  @T001-RFC0453 @RFC0592 @critical @AcceptanceTest @Schema_DriversLicense_v2
  Scenario Outline: Issue a Indy credential with the Holder beginning with a proposal
    Given "2" agents
      | name | role   |
      | Acme | issuer |
      | Bob  | holder |
    Given "Acme" has a public did
    And "Acme" is ready to issue a credential
    And "Acme" and "Bob" have an existing connection
    When "Bob" proposes a "<credential_type>" credential to "Acme" with <credential_data>
    And "Acme" offers the "<credential_type>" credential
    And "Bob" requests the "<credential_type>" credential
    And "Acme" issues the "<credential_type>" credential
    And "Bob" acknowledges the "<credential_type>" credential issue
    Then "Bob" has the "<credential_type>" credential issued

    @RFC0160 @CredFormat_Indy
    Examples:
      | credential_type | credential_data   |
      | indy            | Data_DL_MaxValues |

    @RFC0160 @Anoncreds
    Examples:
      | credential_type | credential_data   |
      | anoncreds       | Data_DL_MaxValues |

    @DIDExchangeConnection @CredFormat_Indy
    Examples:
      | credential_type | credential_data   |
      | indy            | Data_DL_MaxValues |

    @DIDExchangeConnection @Anoncreds
    Examples:
      | credential_type | credential_data   |
      | anoncreds       | Data_DL_MaxValues |

  @T001.1-RFC0453 @RFC0593 @critical @AcceptanceTest @DIDExchangeConnection @CredFormat_JSON-LD @Schema_DriversLicense_v2
  Scenario Outline: Issue a JSON-LD credential with the Holder beginning with a proposal
    Given "2" agents
      | name | role   |
      | Acme | issuer |
      | Bob  | holder |
    And "Acme" is ready to issue a "json-ld" credential
    And "Acme" and "Bob" have an existing connection
    When "Bob" proposes a "json-ld" credential to "Acme" with <credential_data>
    And "Acme" offers the "json-ld" credential
    And "Bob" requests the "json-ld" credential
    And "Acme" issues the "json-ld" credential
    And "Bob" acknowledges the "json-ld" credential issue
    Then "Bob" has the "json-ld" credential issued

    @ProofType_Ed25519Signature2018 @DidMethod_sov
    Examples:
      | credential_data   |
      | Data_DL_MaxValues |

    @ProofType_Ed25519Signature2018 @DidMethod_key
    Examples:
      | credential_data   |
      | Data_DL_MaxValues |

    @ProofType_BbsBlsSignature2020 @DidMethod_key
    Examples:
      | credential_data   |
      | Data_DL_MaxValues |

    @ProofType_Ed25519Signature2018 @DidMethod_orb
    Examples:
      | credential_data   |
      | Data_DL_MaxValues |

    @ProofType_BbsBlsSignature2020 @DidMethod_orb
    Examples:
      | credential_data   |
      | Data_DL_MaxValues |

  @T002-RFC0453 @normal @wip @AcceptanceTest @DIDExchangeConnection @Schema_DriversLicense_v2
  Scenario Outline: Issue a credential with the Holder beginning with a proposal with negotiation
    Given "2" agents
      | name | role   |
      | Acme | issuer |
      | Bob  | holder |
    Given "Acme" has a public did
    And "Acme" is ready to issue a credential
    And "Acme" and "Bob" have an existing connection
    And "Bob" proposes a "<credential_format>" credential to "Acme" with <credential_data>
    And "Acme" offers the "<credential_format>" credential
    When "Bob" negotiates the offer with another proposal of the "<credential_format>" credential to "Acme" with <updated_credential_data>
    And "Acme" offers the "<credential_format>" credential
    And "Bob" requests the "<credential_format>" credential
    And "Acme" issues the "<credential_format>" credential
    And "Bob" acknowledges the "<credential_format>" credential issue
    Then "Bob" has the "<credential_format>" credential issued

    @CredFormat_Indy
    Examples:
      | credential_format | credential_data   | updated_credential_data  |
      | indy              | Data_DL_MaxValues | Data_DL_NormalizedValues |

    @Anoncreds
    Examples:
      | credential_format | credential_data   | updated_credential_data  |
      | anoncreds         | Data_DL_MaxValues | Data_DL_NormalizedValues |

  # @T003-RFC0453 @critical @wip @AcceptanceTest
  # Scenario: Issue a credential with the Issuer beginning with an offer
  #   Given "2" agents
  #     | name | role   |
  #     | Acme | issuer |
  #     | Bob  | holder |
  #   And "Acme" and "Bob" have an existing connection
  #   When "Acme" offers a credential
  #   And "Bob" requests the credential
  #   And "Acme" issues the credential
  #   And "Bob" acknowledges the credential issue
  #   Then "Bob" has the credential issued

  # @T004-RFC0453 @normal @wip @AcceptanceTest
  # Scenario: Issue a credential with the Issuer beginning with an offer with negotiation
  #   Given "2" agents
  #     | name | role   |
  #     | Acme | issuer |
  #     | Bob  | holder |
  #   And "Acme" and "Bob" have an existing connection
  #   And "Acme" offers a credential
  #   When "Bob" negotiates the offer with a proposal of the credential to "Acme"
  #   And "Acme" Offers the credential
  #   And "Bob" requests the credential
  #   And "Acme" issues the credential
  #   And "Bob" acknowledges the credential issue
  #   Then "Bob" has the credential issued

  # @T005-RFC0453 @minor @wip @AcceptanceTest
  # Scenario: Issue a credential with negotiation beginning from a credential request
  #   Given "2" agents
  #     | name | role   |
  #     | Acme | issuer |
  #     | Bob  | holder |
  #   And "Acme" and "Bob" have an existing connection
  #   When "Bob" requests the credential
  #   And "Acme" offers a credential
  #   When "Bob" negotiates the offer with a proposal of the credential to "Acme"
  #   And "Acme" offers a credential
  #   And "Acme" issues the credential
  #   And "Bob" acknowledges the credential issue
  #   Then "Bob" has the credential issued

  # @T006-RFC0453 @critical @wip @AcceptanceTest
  # Scenario: Issue a credential with the Holder beginning with a request and is accepted
  #   Given "2" agents
  #     | name | role   |
  #     | Acme | issuer |
  #     | Bob  | holder |
  #   And "Acme" and "Bob" have an existing connection
  #   When "Bob" requests the credential
  #   And "Acme" issues the credential
  #   And "Bob" acknowledges the credential issue
  #   Then "Bob" has the credential issued
